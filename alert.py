from models import WeatherContext, DayForecast
from enum import Enum


class AlertLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    NONE = "NONE"


def compute_delta_score(forecast: list[DayForecast]) -> tuple[AlertLevel, str | None]:
    """
    Compare day 0 vs day 2 of the forecast to detect significant
    upcoming weather changes. Returns (AlertLevel, alert_message).
    """
    if len(forecast) < 3:
        return AlertLevel.NONE, None

    day0, day2 = forecast[0], forecast[2]

    temp_delta = abs(day2.temp_max - day0.temp_max)
    precip_delta = day2.precipitation_sum - day0.precipitation_sum
    uv_delta = day2.uv_max - day0.uv_max

    if temp_delta > 8 or precip_delta > 10:
        msg = (
            f"⚠️ Major weather shift in ~48 hours: "
            f"temperature may {'drop' if day2.temp_max < day0.temp_max else 'rise'} "
            f"by {temp_delta:.1f}°C"
        )
        if precip_delta > 10:
            msg += f" and heavy rain ({precip_delta:.0f}mm) is expected."
        return AlertLevel.HIGH, msg

    if uv_delta > 4:
        msg = (
            f"⚠️ UV index will jump significantly in ~48 hours "
            f"(from {day0.uv_max:.0f} → {day2.uv_max:.0f}). Prepare sun protection."
        )
        return AlertLevel.MEDIUM, msg

    return AlertLevel.NONE, None
