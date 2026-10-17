"""Thin async client over the Open-Meteo forecast + geocoding APIs (free, keyless, global).

Stateless: every call hits Open-Meteo live and returns a normalized dict. No cache, no DB — the caller
owns state. Inputs (place name, coordinates) pass through verbatim; the resolved coordinates are echoed
back so a result is reproducible."""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings

# WMO weather interpretation codes -> (human label, icon kind for the card). Icon kinds are the small
# set card.py knows how to draw: clear, partly, cloud, fog, drizzle, rain, snow, storm.
WMO: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "clear"),
    1: ("Mainly clear", "partly"), 2: ("Partly cloudy", "partly"), 3: ("Overcast", "cloud"),
    45: ("Fog", "fog"), 48: ("Depositing rime fog", "fog"),
    51: ("Light drizzle", "drizzle"), 53: ("Moderate drizzle", "drizzle"), 55: ("Dense drizzle", "drizzle"),
    56: ("Light freezing drizzle", "drizzle"), 57: ("Dense freezing drizzle", "drizzle"),
    61: ("Slight rain", "rain"), 63: ("Moderate rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Light freezing rain", "rain"), 67: ("Heavy freezing rain", "rain"),
    71: ("Slight snow", "snow"), 73: ("Moderate snow", "snow"), 75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Slight rain showers", "rain"), 81: ("Moderate rain showers", "rain"), 82: ("Violent rain showers", "rain"),
    85: ("Slight snow showers", "snow"), 86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Thunderstorm with slight hail", "storm"), 99: ("Thunderstorm with heavy hail", "storm"),
}


def describe(code: int | None) -> tuple[str, str]:
    """(label, icon_kind) for a WMO weather code; a safe fallback for anything unknown/missing."""
    if code is None:
        return ("Unknown", "cloud")
    return WMO.get(int(code), (f"Code {code}", "cloud"))


UNITS = {
    "metric": {"temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm",
               "t": "°C", "w": "km/h", "p": "mm"},
    "imperial": {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch",
                 "t": "°F", "w": "mph", "p": "in"},
}

_CURRENT = ["temperature_2m", "relative_humidity_2m", "apparent_temperature", "is_day",
            "precipitation", "weather_code", "wind_speed_10m", "wind_direction_10m"]
_DAILY = ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
          "precipitation_probability_max", "wind_speed_10m_max", "sunrise", "sunset"]


class OpenMeteoError(RuntimeError):
    """Open-Meteo is unreachable or returned an error (a genuine fault, not a policy decision)."""


class OpenMeteoClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._client = httpx.AsyncClient(timeout=settings.http_timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            r = await self._client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise OpenMeteoError(f"Open-Meteo GET {url} failed: {e}") from e

    async def geocode(self, name: str, language: str | None = None, count: int = 5) -> list[dict[str, Any]]:
        """Resolve a place name to candidate locations. Empty list = no match (a caller-fixable input,
        not a fault)."""
        data = await self._get(f"{self.s.geocoding_url}/search",
                               {"name": name, "count": count, "language": language or self.s.language, "format": "json"})
        out = []
        for r in data.get("results") or []:
            out.append({
                "name": r.get("name"), "country": r.get("country"), "admin1": r.get("admin1"),
                "latitude": r.get("latitude"), "longitude": r.get("longitude"),
                "timezone": r.get("timezone"), "population": r.get("population"),
            })
        return out

    async def forecast(self, lat: float, lon: float, days: int, units: str) -> dict[str, Any]:
        """Current conditions + an N-day daily forecast, normalized. `days` is clamped 1..16."""
        u = UNITS.get(units, UNITS["metric"])
        days = max(1, min(int(days), 16))
        params = {
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": days,
            "current": ",".join(_CURRENT), "daily": ",".join(_DAILY),
            "temperature_unit": u["temperature_unit"], "wind_speed_unit": u["wind_speed_unit"],
            "precipitation_unit": u["precipitation_unit"],
        }
        data = await self._get(f"{self.s.forecast_url}/forecast", params)
        cur = data.get("current") or {}
        c_label, c_icon = describe(cur.get("weather_code"))
        current = {
            "time": cur.get("time"),
            "temperature": cur.get("temperature_2m"), "apparent_temperature": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"), "precipitation": cur.get("precipitation"),
            "wind_speed": cur.get("wind_speed_10m"), "wind_direction": cur.get("wind_direction_10m"),
            "is_day": bool(cur.get("is_day", 1)), "weather_code": cur.get("weather_code"),
            "condition": c_label, "icon": c_icon,
        }
        d = data.get("daily") or {}
        daily = []
        for i, day in enumerate(d.get("time") or []):
            label, icon = describe((d.get("weather_code") or [None])[i] if i < len(d.get("weather_code") or []) else None)
            daily.append({
                "date": day,
                "temp_max": _at(d, "temperature_2m_max", i), "temp_min": _at(d, "temperature_2m_min", i),
                "precipitation_sum": _at(d, "precipitation_sum", i),
                "precipitation_probability_max": _at(d, "precipitation_probability_max", i),
                "wind_speed_max": _at(d, "wind_speed_10m_max", i),
                "sunrise": _at(d, "sunrise", i), "sunset": _at(d, "sunset", i),
                "weather_code": _at(d, "weather_code", i), "condition": label, "icon": icon,
            })
        return {
            "latitude": data.get("latitude", lat), "longitude": data.get("longitude", lon),
            "timezone": data.get("timezone"), "elevation": data.get("elevation"),
            "units": {"temperature": u["t"], "wind_speed": u["w"], "precipitation": u["p"]},
            "current": current, "daily": daily,
        }


def _at(block: dict[str, Any], key: str, i: int) -> Any:
    arr = block.get(key)
    return arr[i] if isinstance(arr, list) and i < len(arr) else None
