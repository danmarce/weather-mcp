"""Tool-level: call each MCP tool by name through the server, against a fake Open-Meteo (no network).

Pins what matters: the declared title + all four hints as the wire JSON, the ok/refused/error contract a
caller actually sees, that a place name is geocoded then forecast, and that a card link comes back."""

import asyncio
import json

import httpx
import pytest

from weather_mcp import openmeteo as om
from weather_mcp.config import Settings
from weather_mcp.server import build_server
from weather_mcp.textcard import _width


class FakeOpenMeteo:
    """Answers the two Open-Meteo endpoints the client uses; records every request."""

    def __init__(self, down: bool = False, no_geo: bool = False) -> None:
        self.down = down
        self.no_geo = no_geo
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.url.path, dict(req.url.params)))
        if self.down:
            raise httpx.ConnectError("connection refused", request=req)
        if req.url.path.endswith("/search"):
            if self.no_geo:
                return httpx.Response(200, json={"results": []})
            return httpx.Response(200, json={"results": [{
                "name": "Quito", "country": "Ecuador", "admin1": "Pichincha",
                "latitude": -0.18, "longitude": -78.47, "timezone": "America/Guayaquil", "population": 1600000,
            }]})
        if req.url.path.endswith("/forecast"):
            return httpx.Response(200, json={
                "latitude": -0.18, "longitude": -78.47, "timezone": "America/Guayaquil", "elevation": 2850,
                "current": {"time": "2026-10-16T12:00", "temperature_2m": 19.4, "relative_humidity_2m": 62,
                            "apparent_temperature": 19.0, "is_day": 1, "precipitation": 0.0, "weather_code": 2,
                            "wind_speed_10m": 11.0, "wind_direction_10m": 120},
                "daily": {"time": ["2026-10-16", "2026-10-17", "2026-10-18"],
                          "weather_code": [2, 61, 95], "temperature_2m_max": [21.0, 20.0, 19.0],
                          "temperature_2m_min": [9.0, 10.0, 11.0], "precipitation_sum": [0.0, 4.2, 12.0],
                          "precipitation_probability_max": [10, 70, 90], "wind_speed_10m_max": [14, 18, 22],
                          "sunrise": ["2026-10-16T06:10"] * 3, "sunset": ["2026-10-16T18:12"] * 3},
            })
        return httpx.Response(404)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("WEATHER_OUT_DIR", str(tmp_path))
    monkeypatch.setenv("WEATHER_PUBLIC_URL", "http://weather.test:8000")
    fake = FakeOpenMeteo()
    real = httpx.AsyncClient
    monkeypatch.setattr(om.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
    return fake, Settings()


def _call(settings: Settings, name: str, args: dict, transport: str = "http") -> dict:
    res = asyncio.run(build_server(settings, transport).call_tool(name, args))
    texts = [c for c in res.content if c.type == "text"]
    return json.loads(texts[-1].text)


def test_every_tool_declares_title_and_all_four_hints():
    tools = asyncio.run(build_server(Settings()).list_tools())
    assert {t.name for t in tools} == {"get_forecast", "geocode"}
    for t in tools:
        wire = t.annotations.model_dump(by_alias=True)
        for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
            assert isinstance(wire.get(hint), bool), f"{t.name}.{hint} unset"
        assert t.title and wire.get("title") == t.title, f"{t.name} missing title"
        assert wire["readOnlyHint"] and wire["openWorldHint"] and not wire["destructiveHint"]


def test_get_forecast_by_coords_returns_data_and_card(env):
    fake, s = env
    d = _call(s, "get_forecast", {"latitude": -0.18, "longitude": -78.47, "days": 3})
    assert d["status"] == "ok"
    assert d["current"]["temperature"] == 19.4 and d["current"]["condition"] == "Partly cloudy"
    assert len(d["daily"]) == 3 and d["daily"][2]["condition"] == "Thunderstorm"
    assert d["card"] == "image"
    assert d["card_url"].startswith("http://weather.test:8000/img/") and d["card_markdown"].startswith("![weather")
    assert not any(p.endswith("/search") for p, _ in fake.calls)  # coords given: no geocode


def test_get_forecast_by_location_geocodes_then_forecasts(env):
    fake, s = env
    d = _call(s, "get_forecast", {"location": "Quito"})
    assert d["status"] == "ok" and d["place"].startswith("Quito")
    paths = [p for p, _ in fake.calls]
    assert any(p.endswith("/search") for p in paths) and any(p.endswith("/forecast") for p in paths)


def test_unknown_location_is_refused_not_error(env):
    fake, s = env
    fake.no_geo = True
    d = _call(s, "get_forecast", {"location": "Xyzzyville"})
    assert d["status"] == "refused" and d["advice"]
    assert not any(p.endswith("/forecast") for p, _ in fake.calls)  # never reached the forecast API


def test_card_none_omits_card(env):
    _, s = env
    d = _call(s, "get_forecast", {"latitude": 1.0, "longitude": 2.0, "card": "none"})
    assert d["status"] == "ok" and d["card"] == "none"
    assert "card_url" not in d and "card_markdown" not in d


def _assert_text_card(d: dict) -> None:
    assert d["card"] == "text" and "card_url" not in d
    md = d["card_markdown"]
    assert md.startswith("```text\n") and md.endswith("\n```")
    lines = md.splitlines()[1:-1]
    assert lines[0].startswith("┌") and lines[-1].startswith("└")
    assert len({_width(line) for line in lines}) == 1, "text card frame is ragged"
    assert "Thunderstorm" in md and "Pichincha" not in md  # coords given: place is the coordinates


def test_stdio_auto_gives_text_card_even_with_public_url(env):
    _, s = env  # WEATHER_PUBLIC_URL is set, but stdio can't serve /img
    d = _call(s, "get_forecast", {"latitude": -0.18, "longitude": -78.47}, transport="stdio")
    _assert_text_card(d)
    assert "card_note" not in d


def test_http_without_public_url_gives_text_card(env, monkeypatch):
    monkeypatch.delenv("WEATHER_PUBLIC_URL")
    d = _call(Settings(), "get_forecast", {"latitude": -0.18, "longitude": -78.47})
    _assert_text_card(d)


def test_image_requested_on_stdio_falls_back_to_text(env):
    _, s = env
    d = _call(s, "get_forecast", {"latitude": -0.18, "longitude": -78.47, "card": "image"}, transport="stdio")
    _assert_text_card(d)
    assert d["card_note"]


def test_text_card_on_request_over_http(env):
    _, s = env
    d = _call(s, "get_forecast", {"latitude": -0.18, "longitude": -78.47, "card": "text"})
    _assert_text_card(d)


def test_bad_card_mode_refused(env):
    _, s = env
    d = _call(s, "get_forecast", {"latitude": 1.0, "longitude": 2.0, "card": "png"})
    assert d["status"] == "refused" and d["advice"]


def test_bad_units_refused(env):
    _, s = env
    d = _call(s, "get_forecast", {"latitude": 1.0, "longitude": 2.0, "units": "kelvin"})
    assert d["status"] == "refused"


def test_geocode_ok_and_no_match(env):
    fake, s = env
    d = _call(s, "geocode", {"query": "Quito"})
    assert d["status"] == "ok" and d["results"][0]["name"] == "Quito"
    fake.no_geo = True
    d2 = _call(s, "geocode", {"query": "Xyzzyville"})
    assert d2["status"] == "refused"


def test_open_meteo_down_is_error(env):
    fake, s = env
    fake.down = True
    d = _call(s, "get_forecast", {"latitude": 1.0, "longitude": 2.0})
    assert d["status"] == "error" and d["kind"] == "open_meteo"
