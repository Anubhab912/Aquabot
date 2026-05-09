import os
import httpx
import json
import re
from models import WeatherContext, AIInsights
from alert import compute_delta_score, AlertLevel

HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")
HF_MODEL = "Qwen/Qwen2.5-32B-Instruct"
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"


def _build_prompt(ctx: WeatherContext, alert_msg: str | None) -> str:
    forecast_lines = "\n".join(
        f"  {d.date}: {d.description}, max {d.temp_max}°C / min {d.temp_min}°C, "
        f"rain {d.precipitation_sum}mm, UV {d.uv_max}"
        for d in ctx.forecast_7day[:4]
    )

    alert_section = (
        f"\nUpcoming alert: {alert_msg}\n"
        if alert_msg
        else ""
    )

    return f"""<|im_start|>system
You are AquaBot, a smart agricultural and health advisor.
Respond ONLY with a valid JSON object. No extra text, no markdown code blocks.
Structure:
{{
  "summary": "2-3 sentence plain-English weather summary",
  "farming_tips": ["specific tip 1", "specific tip 2", "specific tip 3"],
  "health_tips": ["specific tip 1", "specific tip 2", "specific tip 3"]
}}
Ensure the tips are DIRECTLY derived from the current metrics (e.g., if UV is high, mention sun protection).
<|im_end|>
<|im_start|>user
Current conditions for {ctx.city} ({ctx.season}):
- Temp: {ctx.temperature_c}°C (Feels like {ctx.feels_like_c}°C)
- Humidity: {ctx.humidity_pct}%
- Wind: {ctx.wind_kmh} km/h
- UV: {ctx.uv_index}
- Rain: {ctx.precipitation_mm} mm
- Condition: {ctx.weather_description}

4-Day Forecast:
{forecast_lines}
{alert_section}
<|im_end|>
<|im_start|>assistant
{{"""


def _fallback_insights(ctx: WeatherContext) -> AIInsights:
    """Returns rule-based tips when HuggingFace is unavailable."""
    farming = {
        "heat_advisory": [
            "Water crops early morning to reduce evaporation.",
            "Apply mulch around plant bases to retain soil moisture.",
            "Delay transplanting seedlings until cooler evening hours.",
        ],
        "rain_advisory": [
            "Ensure field drainage channels are clear before heavy rain.",
            "Avoid applying fertilizer before rain to prevent runoff.",
            "Check for fungal disease risk in humid conditions.",
        ],
        "cold_advisory": [
            "Cover frost-sensitive crops overnight.",
            "Delay sowing warm-season crops until temperatures rise.",
            "Monitor soil moisture as cold slows plant water uptake.",
        ],
        "storm_warning": [
            "Secure or stake tall plants against strong winds.",
            "Move potted plants indoors or to a sheltered spot.",
            "Postpone any field spraying operations.",
        ],
        "clear_day": [
            "Ideal day for plowing and soil preparation.",
            "Good conditions for applying foliar sprays.",
            "Check irrigation schedules — evaporation will be higher.",
        ],
        "general": [
            "Monitor weather forecasts before planning field operations.",
            "Ensure adequate soil moisture for your crops.",
            "Inspect plants for pests and disease regularly.",
        ],
    }
    health = {
        "heat_advisory": [
            "Drink at least 3L of water today.",
            "Avoid outdoor activity between 11am–4pm.",
            "Wear light, breathable clothing and a hat.",
        ],
        "rain_advisory": [
            "Carry an umbrella or waterproof jacket.",
            "Avoid standing in waterlogged areas.",
            "Watch out for slippery surfaces when walking.",
        ],
        "cold_advisory": [
            "Layer your clothing to trap body heat.",
            "Keep extremities (hands, feet, head) covered.",
            "Eat warm, calorie-dense meals to maintain body temperature.",
        ],
        "storm_warning": [
            "Stay indoors during lightning storms.",
            "Avoid tall trees and open fields.",
            "Keep emergency contacts and a charged phone nearby.",
        ],
        "clear_day": [
            "Apply SPF 30+ sunscreen if spending time outdoors.",
            "Great day for outdoor exercise — stay hydrated.",
            "UV levels are low — enjoy the sunshine safely.",
        ],
        "general": [
            "Stay hydrated throughout the day.",
            "Check local health advisories.",
            "Dress appropriately for current temperatures.",
        ],
    }
    cat = ctx.tip_category
    return AIInsights(
        summary=f"Currently {ctx.weather_description.lower()} in {ctx.city}. "
                f"Temperature is {ctx.temperature_c}°C with {ctx.humidity_pct}% humidity. "
                f"Conditions are typical for {ctx.season}.",
        farming_tips=farming.get(cat, farming["general"]),
        health_tips=health.get(cat, health["general"]),
        model_used="Rule-Based Engine",
    )


async def generate_insights(ctx: WeatherContext) -> AIInsights:
    alert_level, alert_msg = compute_delta_score(ctx.forecast_7day)

    if not HF_API_TOKEN:
        insights = _fallback_insights(ctx)
        if alert_msg:
            insights.alert = alert_msg
            insights.alert_level = alert_level.value
        return insights

    prompt = _build_prompt(ctx, alert_msg)
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 512,
            "temperature": 0.7,
            "return_full_text": False,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(HF_URL, headers=headers, json=payload)
            resp.raise_for_status()
            raw = resp.json()

        generated_text = raw[0]["generated_text"] if isinstance(raw, list) else raw.get("generated_text", "")

        # Extract JSON from the generated text
        json_match = re.search(r"\{.*\}", generated_text, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in AI response")

        parsed = json.loads(json_match.group())
        insights = AIInsights(
            summary=parsed.get("summary", ""),
            farming_tips=parsed.get("farming_tips", [])[:3],
            health_tips=parsed.get("health_tips", [])[:3],
            model_used=f"{HF_MODEL.split('/')[-1]}",
        )

    except Exception as e:
        # Graceful fallback with logging
        print(f"[AI Engine] Fallback triggered: {e}")
        insights = _fallback_insights(ctx)

    if alert_msg:
        insights.alert = alert_msg
        insights.alert_level = alert_level.value

    return insights
