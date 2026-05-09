import httpx
from datetime import date
from models import WeatherContext, DayForecast
from wmo_codes import decode_wmo

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _get_season(month: int, latitude: float) -> str:
    """Determine season based on month and hemisphere."""
    northern = latitude >= 0
    if month in (12, 1, 2):
        return "Winter" if northern else "Summer"
    elif month in (3, 4, 5):
        return "Spring" if northern else "Autumn"
    elif month in (6, 7, 8):
        return "Summer" if northern else "Winter"
    else:
        return "Autumn" if northern else "Spring"


def _get_tip_category(
    temp: float, uv: float, precip: float, weather_code: int
) -> str:
    if weather_code >= 95:
        return "storm_warning"
    if precip > 2 or (61 <= weather_code <= 82):
        return "rain_advisory"
    if temp > 35 or uv > 7:
        return "heat_advisory"
    if temp < 5:
        return "cold_advisory"
    if 0 <= weather_code <= 2 and uv < 4:
        return "clear_day"
    return "general"


async def fetch_weather(city: str, lat: float, lon: float) -> WeatherContext:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": (
            "temperature_2m,relative_humidity_2m,wind_speed_10m,"
            "precipitation,weather_code,uv_index,apparent_temperature"
        ),
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "uv_index_max,wind_speed_10m_max,weather_code"
        ),
        "timezone": "auto",
        "forecast_days": 7,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    current = data["current"]
    daily = data["daily"]
    
    # Use the local date from the API response for seasonal accuracy
    local_time_str = current.get("time", "")
    try:
        # Expected format: "2024-05-02T12:00"
        today_month = int(local_time_str.split("-")[1])
    except (IndexError, ValueError):
        today_month = date.today().month

    temp = current["temperature_2m"]
    uv = current.get("uv_index", 0) or 0
    precip = current.get("precipitation", 0) or 0
    weather_code = current["weather_code"]

    forecast = []
    for i in range(7):
        forecast.append(
            DayForecast(
                date=daily["time"][i],
                temp_max=daily["temperature_2m_max"][i],
                temp_min=daily["temperature_2m_min"][i],
                precipitation_sum=daily["precipitation_sum"][i] or 0,
                uv_max=daily["uv_index_max"][i] or 0,
                wind_max=daily["wind_speed_10m_max"][i] or 0,
                description=decode_wmo(daily["weather_code"][i]),
            )
        )

    return WeatherContext(
        city=city,
        latitude=lat,
        longitude=lon,
        temperature_c=round(temp, 1),
        feels_like_c=round(current.get("apparent_temperature", temp), 1),
        humidity_pct=int(current.get("relative_humidity_2m", 0)),
        wind_kmh=round(current.get("wind_speed_10m", 0), 1),
        uv_index=round(uv, 1),
        precipitation_mm=round(precip, 1),
        weather_description=decode_wmo(weather_code),
        weather_code=weather_code,
        season=_get_season(today_month, lat),
        tip_category=_get_tip_category(temp, uv, precip, weather_code),
        forecast_7day=forecast,
    )
