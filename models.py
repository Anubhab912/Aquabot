from pydantic import BaseModel
from typing import Optional


class DayForecast(BaseModel):
    date: str
    temp_max: float
    temp_min: float
    precipitation_sum: float
    uv_max: float
    wind_max: float
    description: str


class WeatherContext(BaseModel):
    city: str
    latitude: float
    longitude: float
    temperature_c: float
    feels_like_c: float
    humidity_pct: int
    wind_kmh: float
    uv_index: float
    precipitation_mm: float
    weather_description: str
    weather_code: int
    season: str
    tip_category: str
    forecast_7day: list[DayForecast]


class AIInsights(BaseModel):
    summary: str
    farming_tips: list[str]
    health_tips: list[str]
    model_used: str
    alert: Optional[str] = None
    alert_level: Optional[str] = None   # "HIGH", "MEDIUM", or None


class WeatherResponse(BaseModel):
    context: WeatherContext
    insights: AIInsights
