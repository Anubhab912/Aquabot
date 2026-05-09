import os
import httpx
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from weather import fetch_weather
from ai_engine import generate_insights
from models import WeatherResponse

app = FastAPI(title="AquaBot", description="AI Weather + Satellite Insights", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "AquaBot"}


@app.get("/geocode")
async def geocode(city: str = Query(..., min_length=2)):
    """Resolve location name to lat/lon using Open-Meteo, with a fallback to Nominatim."""
    city = city.strip()
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Try Open-Meteo
        try:
            resp = await client.get(
                GEOCODE_URL,
                params={"name": city, "count": 100, "language": "en", "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results")
        except Exception:
            results = None

        if results:
            def get_score(r):
                s = 0
                name = (r.get("name") or "").lower()
                query = city.lower()
                if query == name:
                    s += 1000
                elif query in name or name in query:
                    s += 500
                pop = (r.get("population") or 0)
                s += min(pop / 10000, 50)
                return s

            import unicodedata
            def clean_name(text):
                if not text: return ""
                return "".join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))

            match = max(results, key=get_score)
            parts = [clean_name(match.get("name", city))]
            if match.get("admin1"): parts.append(clean_name(match["admin1"]))
            if match.get("country"): parts.append(clean_name(match["country"]))
            full_name = ", ".join(parts)
            
            return {
                "city": full_name,
                "country": clean_name(match.get("country", "")),
                "latitude": match["latitude"],
                "longitude": match["longitude"],
            }
            
        # 2. Fallback to Nominatim (OpenStreetMap) if no results
        try:
            nom_url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "AquaBot/1.0 (contact@aquabot.local)"}
            nom_resp = await client.get(
                nom_url,
                params={"q": city, "format": "json", "limit": 5},
                headers=headers
            )
            nom_resp.raise_for_status()
            nom_data = nom_resp.json()
            with open("scratch/nom_debug.txt", "a", encoding="utf-8") as f:
                f.write(f"City: {city}, Results: {nom_data}\n")
            print(f"[Geocode] Nominatim response for {city}: {nom_data}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Geocoding failed: {e}")

        if not nom_data:
            raise HTTPException(status_code=404, detail=f"Location '{city}' not found.")
            
        match = nom_data[0]
        # Nominatim returns full address in 'display_name'
        # e.g. "Khalore Panchayat Road, Bagnan, ..."
        # We can extract the first few parts to keep it concise
        parts = match.get("display_name", city).split(", ")
        short_name = ", ".join(parts[:3]) if len(parts) >= 3 else match.get("display_name", city)
        
        return {
            "city": short_name,
            "country": parts[-1] if len(parts) > 1 else "",
            "latitude": float(match["lat"]),
            "longitude": float(match["lon"]),
        }


@app.get("/weather", response_model=WeatherResponse)
async def get_weather(
    city: str = Query(..., description="City name"),
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """
    Main endpoint:
      1. Fetch weather from Open-Meteo
      2. Generate AI insights via HuggingFace
      3. Return merged response
    """
    try:
        ctx = await fetch_weather(city=city, lat=lat, lon=lon)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather fetch failed: {e}")

    try:
        insights = await generate_insights(ctx)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI insight generation failed: {e}")

    return WeatherResponse(context=ctx, insights=insights)
