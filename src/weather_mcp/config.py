"""Runtime settings, all from environment variables (the only secret is the optional HTTP bearer).

Open-Meteo needs NO API key, so there is nothing to store here but the public endpoints, a default
location, and the capability-link plumbing (shared with forge-mcp's pattern)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Open-Meteo is free for non-commercial use, no key, global. Two hosts: the forecast API and the
# geocoding API. WMO weather codes are mapped in openmeteo.py.
DEFAULT_FORECAST_URL = "https://api.open-meteo.com/v1"
DEFAULT_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1"

# A sensible lab default location when a call gives neither a place name nor coordinates. Quito city
# centre is PUBLIC, city-level — deliberately NOT the home coordinates (those are location PII and stay
# in 1Password, never in a repo or a default). Override via env for another default.
DEFAULT_LAT = -0.1807
DEFAULT_LON = -78.4678
DEFAULT_NAME = "Quito"


@dataclass(frozen=True)
class Settings:
    forecast_url: str = field(default_factory=lambda: os.environ.get("WEATHER_FORECAST_URL", DEFAULT_FORECAST_URL).rstrip("/"))
    geocoding_url: str = field(default_factory=lambda: os.environ.get("WEATHER_GEOCODING_URL", DEFAULT_GEOCODING_URL).rstrip("/"))
    http_timeout: float = field(default_factory=lambda: float(os.environ.get("WEATHER_HTTP_TIMEOUT", "15")))
    # Default language for geocoding + condition labels (Open-Meteo geocoding is localized; labels are ours).
    language: str = field(default_factory=lambda: os.environ.get("WEATHER_LANGUAGE", "en"))
    # Default location when a call supplies neither place nor lat/lon.
    default_lat: float = field(default_factory=lambda: float(os.environ.get("WEATHER_DEFAULT_LAT", str(DEFAULT_LAT))))
    default_lon: float = field(default_factory=lambda: float(os.environ.get("WEATHER_DEFAULT_LON", str(DEFAULT_LON))))
    default_name: str = field(default_factory=lambda: os.environ.get("WEATHER_DEFAULT_NAME", DEFAULT_NAME))
    # Card image is served as a short-lived LINK at /img/<name> (base64 in the result would flood context).
    out_dir: str = field(default_factory=lambda: os.environ.get("WEATHER_OUT_DIR", "out"))
    # The base URL clients use to reach THIS server (e.g. http://yuki:8000, or a casita.digital name).
    # MUST be browser-reachable: OWUI loads the card client-side. Required for a card link to be returned.
    public_url: str = field(default_factory=lambda: os.environ.get("WEATHER_PUBLIC_URL", "").rstrip("/"))
    # How long a served card link stays valid (TTL GC).
    img_ttl: int = field(default_factory=lambda: int(os.environ.get("WEATHER_IMG_TTL", "600")))
    # Bearer token required on streamable-http when set (sent as an Authorization header).
    http_token: str | None = field(default_factory=lambda: os.environ.get("WEATHER_MCP_TOKEN") or None)
