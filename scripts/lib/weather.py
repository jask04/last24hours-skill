"""Official no-auth weather forecasts via api.weather.gov."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from . import evidence_quality as eq, http

NWS_BASE = "https://api.weather.gov"

CITY_ALIASES = {
    "nyc": ("New York, NY", 40.7128, -74.0060),
    "new york": ("New York, NY", 40.7128, -74.0060),
    "new york city": ("New York, NY", 40.7128, -74.0060),
    "la": ("Los Angeles, CA", 34.0522, -118.2437),
    "los angeles": ("Los Angeles, CA", 34.0522, -118.2437),
    "chicago": ("Chicago, IL", 41.8781, -87.6298),
    "miami": ("Miami, FL", 25.7617, -80.1918),
    "boston": ("Boston, MA", 42.3601, -71.0589),
    "dc": ("Washington, DC", 38.9072, -77.0369),
    "washington dc": ("Washington, DC", 38.9072, -77.0369),
    "seattle": ("Seattle, WA", 47.6062, -122.3321),
    "san francisco": ("San Francisco, CA", 37.7749, -122.4194),
    "sf": ("San Francisco, CA", 37.7749, -122.4194),
    "dallas": ("Dallas, TX", 32.7767, -96.7970),
    "houston": ("Houston, TX", 29.7604, -95.3698),
    "phoenix": ("Phoenix, AZ", 33.4484, -112.0740),
    "denver": ("Denver, CO", 39.7392, -104.9903),
    "las vegas": ("Las Vegas, NV", 36.1699, -115.1398),
    "vegas": ("Las Vegas, NV", 36.1699, -115.1398),
    "philadelphia": ("Philadelphia, PA", 39.9526, -75.1652),
    "philly": ("Philadelphia, PA", 39.9526, -75.1652),
    "atlanta": ("Atlanta, GA", 33.7490, -84.3880),
}


def is_weather_query(topic: str) -> bool:
    return eq.is_weather_query(topic)


def resolve_location(topic: str) -> Optional[tuple[str, float, float]]:
    topic_tokens = eq.tokenize(topic)
    topic_lower = f" {topic.lower()} "
    for alias, location in sorted(CITY_ALIASES.items(), key=lambda pair: len(pair[0]), reverse=True):
        alias_tokens = eq.tokenize(alias)
        if len(alias_tokens) == 1:
            if next(iter(alias_tokens)) in topic_tokens:
                return location
        elif f" {alias} " in topic_lower:
            return location
    return None


def _target_date(topic: str) -> str:
    today = datetime.now().astimezone().date()
    topic_lower = topic.lower()
    if "tomorrow" in topic_lower or "tmrw" in topic_lower:
        return (today + timedelta(days=1)).isoformat()
    return today.isoformat()


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/geo+json, application/json",
        "User-Agent": "last24hours-skill/1.0 (https://github.com/jask04/last24hours-skill)",
    }


def _period_probability(period: Dict[str, Any]) -> Optional[int]:
    value = (period.get("probabilityOfPrecipitation") or {}).get("value")
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _period_matches_date(period: Dict[str, Any], target_date: str) -> bool:
    start = period.get("startTime") or ""
    return start[:10] == target_date


def search_weather(topic: str, from_date: str, to_date: str, depth: str = "default") -> Dict[str, Any]:
    """Return a single official NWS weather forecast item for supported U.S. city prompts."""
    if not is_weather_query(topic):
        return {"items": []}

    location = resolve_location(topic)
    if not location:
        return {"items": [], "error": "No supported U.S. city alias found for official NWS weather lookup"}

    location_name, lat, lon = location
    target_date = _target_date(topic)
    point_url = f"{NWS_BASE}/points/{lat:.4f},{lon:.4f}"
    point = http.get(point_url, headers=_headers(), timeout=10, retries=2)
    props = point.get("properties", {})
    hourly_url = props.get("forecastHourly")
    if not hourly_url:
        return {"items": [], "error": f"NWS point lookup did not return an hourly forecast URL for {location_name}"}

    hourly = http.get(hourly_url, headers=_headers(), timeout=15, retries=2)
    periods = (hourly.get("properties") or {}).get("periods") or []
    target_periods = [period for period in periods if _period_matches_date(period, target_date)]
    if not target_periods:
        return {"items": [], "error": f"NWS hourly forecast did not include {target_date} for {location_name}"}

    probability_values = [value for value in (_period_probability(period) for period in target_periods) if value is not None]
    max_probability = max(probability_values) if probability_values else None
    representative = max(
        target_periods,
        key=lambda period: (_period_probability(period) or -1),
    )
    title = f"NWS forecast for {location_name} on {target_date}"
    short_forecast = representative.get("shortForecast") or "Forecast unavailable"
    temperature = representative.get("temperature")
    temperature_unit = representative.get("temperatureUnit", "F")
    wind_speed = representative.get("windSpeed") or ""
    wind_direction = representative.get("windDirection") or ""
    generated_at = (hourly.get("properties") or {}).get("generatedAt") or representative.get("startTime")

    return {
        "items": [{
            "title": title,
            "location": location_name,
            "forecast_date": target_date,
            "probability": (max_probability / 100.0) if max_probability is not None else None,
            "probability_pct": max_probability,
            "short_forecast": short_forecast,
            "temperature": temperature,
            "temperature_unit": temperature_unit,
            "wind": " ".join(part for part in (wind_speed, wind_direction) if part),
            "url": hourly_url,
            "date": (generated_at or "")[:10] or None,
            "source": "National Weather Service",
            "why_relevant": f"Official NWS hourly forecast for {location_name}; peak precipitation probability on {target_date} is {max_probability if max_probability is not None else 'unknown'}%.",
        }],
    }


def parse_weather_response(response: Dict[str, Any]) -> list[Dict[str, Any]]:
    return response.get("items", [])
