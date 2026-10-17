"""MCP server: Open-Meteo weather as tools that return BOTH structured data (for the LLM) AND a rendered
card image (for the human) — the card travels as a short-lived capability LINK, never base64 (which would
flood the model's context; see mcp-server-standard §4, and forge-mcp's /img pattern this copies).

Design contract:
  * Stateless proxy: every call hits Open-Meteo live; no cache, no DB. Inputs pass through verbatim; the
    resolved coordinates + units are echoed so a result is reproducible.
  * ok / refused / error status on every result — branch on `status`, never on prose.
  * No API key anywhere (Open-Meteo is keyless); the only secret is the optional HTTP bearer.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent, ToolAnnotations

from .card import render_card
from .config import Settings
from .openmeteo import UNITS, OpenMeteoClient, OpenMeteoError

INSTRUCTIONS = """\
Weather from Open-Meteo (free, no API key, global). Tools: get_forecast (current conditions + an N-day
daily forecast) and geocode (place name -> coordinates).

get_forecast returns, in its text block, the structured weather DATA (temperatures, precipitation, wind,
per-day forecast) for you to reason over and answer in the user's language. With include_card=True (the
default) it ALSO renders a weather CARD image and returns `card_url` (a short-lived link) plus a ready
`card_markdown` string: include that markdown in your reply so the user sees the card. The image is a
LINK, not base64 — it costs ~zero context and renders in the client; never paste image bytes.

Pass a place name as `location` ("Quito", "Berlin"), or exact `latitude`+`longitude`. With neither, a
configured default location is used. `units` is "metric" (default) or "imperial". `days` is 1..16.

Every result has a `status`: "ok" (data returned), "refused" (a caller-fixable input — e.g. a place name
that matched nothing; `reason`/`advice` say how to adjust, don't retry unchanged), or "error" (a genuine
fault — Open-Meteo unreachable; `kind`+`detail`; a reworded query won't help). Branch on `status`.
"""


def _read_hints(title: str, open_world: bool) -> ToolAnnotations:
    # Pure reads: not destructive, idempotent (same args -> same answer modulo live weather). openWorld
    # is TRUE — both tools reach the public Open-Meteo API, outside this server's own backend.
    return ToolAnnotations(title=title, readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                           openWorldHint=open_world)


def _text(payload: dict[str, Any]) -> list[Any]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


def _refused(reason: str, **extra: Any) -> list[Any]:
    """A caller-fixable input decision (not an error): adjust the request, don't retry unchanged."""
    return _text({"status": "refused", "reason": reason, **extra})


def _error(kind: str, detail: str) -> list[Any]:
    """A genuine fault (Open-Meteo down / bad response) — infra, not policy; a prompt change won't fix it."""
    return _text({"status": "error", "kind": kind, "detail": detail})


IMG_NAME_RE = __import__("re").compile(r"[A-Za-z0-9_-]+\.png")  # capability-token filenames only (no traversal)


def _purge_expired(settings: Settings) -> None:
    now = time.time()
    try:
        for fn in os.listdir(settings.out_dir):
            p = os.path.join(settings.out_dir, fn)
            if fn.endswith(".png") and now - os.path.getmtime(p) > settings.img_ttl:
                try:
                    os.remove(p)
                except OSError:
                    pass
    except OSError:
        pass


def _save_card(settings: Settings, png: bytes) -> str:
    """Write the card under an unguessable capability name; return it (served at /img/<name>)."""
    os.makedirs(settings.out_dir, exist_ok=True)
    _purge_expired(settings)
    name = f"{secrets.token_urlsafe(12)}.png"
    with open(os.path.join(settings.out_dir, name), "wb") as f:
        f.write(png)
    return name


def build_server(settings: Settings) -> MCPServer:
    mcp = MCPServer(name="weather", instructions=INSTRUCTIONS)
    client = OpenMeteoClient(settings)

    @mcp.tool(title="Get forecast", annotations=_read_hints("Get forecast", open_world=True),
              structured_output=False)
    async def get_forecast(
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        days: int = 3,
        units: str = "metric",
        language: str | None = None,
        include_card: bool = True,
    ) -> list[Any]:
        """Current conditions + an N-day daily forecast for a place. Returns the structured DATA in the
        text block (for you to answer from) and, with include_card=True, a `card_url` + `card_markdown`
        for a rendered weather card image (include the markdown in your reply so the user sees it).

        Args:
            location: a place name ("Quito", "Berlin, DE"); geocoded via Open-Meteo. Ignored if
                latitude+longitude are given. With neither, the server's default location is used.
            latitude/longitude: exact coordinates (both required together) — overrides `location`.
            days: number of daily-forecast days, 1..16 (default 3).
            units: "metric" (°C, km/h, mm — default) or "imperial" (°F, mph, in).
            language: language for geocoding the place name (default from config, e.g. "en"/"es").
            include_card: default True = also render a weather card and return its link; False = data only.
        """
        if units not in UNITS:
            return _refused(f"unknown units {units!r}", advice='use "metric" or "imperial"')
        # Resolve coordinates: explicit lat/lon > geocoded place > configured default.
        if latitude is not None and longitude is not None:
            lat, lon, place = float(latitude), float(longitude), location or f"{float(latitude):.3f}, {float(longitude):.3f}"
        elif location:
            try:
                hits = await client.geocode(location, language)
            except OpenMeteoError as e:
                return _error("open_meteo", str(e))
            if not hits:
                return _refused(f"no location matched {location!r}",
                                advice="try a more specific name, or pass latitude+longitude")
            h = hits[0]
            lat, lon = float(h["latitude"]), float(h["longitude"])
            place = ", ".join(x for x in (h.get("name"), h.get("admin1"), h.get("country")) if x)
        else:
            lat, lon, place = settings.default_lat, settings.default_lon, settings.default_name
        try:
            data = await client.forecast(lat, lon, days, units)
        except OpenMeteoError as e:
            return _error("open_meteo", str(e))

        out: dict[str, Any] = {"status": "ok", "source": "open-meteo", "place": place, **data}
        if include_card:
            if settings.public_url:
                try:
                    name = _save_card(settings, render_card(place, data))
                    url = f"{settings.public_url}/img/{name}"
                    out["card_url"] = url
                    out["card_ttl_seconds"] = settings.img_ttl
                    out["card_markdown"] = f"![weather in {place}]({url})"
                    out["note"] = "include `card_markdown` in your reply so the user sees the card image."
                except Exception as e:  # noqa: BLE001 - a card failure must not fail the data result
                    out["card_error"] = f"card render failed: {e}"
            else:
                out["note"] = "WEATHER_PUBLIC_URL not set, so no card link can be given (data only)."
        return _text(out)

    @mcp.tool(title="Geocode place", annotations=_read_hints("Geocode place", open_world=True),
              structured_output=False)
    async def geocode(query: str, count: int = 5, language: str | None = None) -> list[Any]:
        """Resolve a place name to candidate coordinates (name, admin region, country, lat/lon, timezone).
        Use it to disambiguate before get_forecast, or when a user names an ambiguous place.

        Args:
            query: the place name to search for.
            count: max candidates to return (default 5).
            language: result language (default from config).
        """
        try:
            hits = await client.geocode(query, language, count=max(1, min(int(count), 20)))
        except OpenMeteoError as e:
            return _error("open_meteo", str(e))
        if not hits:
            return _refused(f"no location matched {query!r}", advice="try a more specific or differently-spelled name")
        return _text({"status": "ok", "source": "open-meteo", "query": query, "results": hits})

    return mcp


# --- streamable-http bearer gate -------------------------

import hmac  # noqa: E402


class BearerAuth:
    """ASGI gate for streamable-http:
      * /healthz     — always open (Docker healthcheck).
      * /img/<name>  — open, serves a saved card PNG by its capability token (short-lived; no bearer so a
                       browser/client can load it without the server secret). Path-traversal-safe.
      * everything else — the MCP app, requiring `Authorization: Bearer <token>` when a token is set.
    """

    def __init__(self, app, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.expected = f"Bearer {settings.http_token}".encode() if settings.http_token else None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            path = scope["path"]
            if path == "/healthz":
                await _respond(send, 200, b"ok")
                return
            if path.startswith("/img/"):
                await self._serve_image(path[len("/img/"):], send)
                return
            if self.expected is not None:
                got = dict(scope["headers"]).get(b"authorization", b"")
                if not hmac.compare_digest(got, self.expected):
                    await _respond(send, 401, b"unauthorized")
                    return
        await self.app(scope, receive, send)

    async def _serve_image(self, name: str, send) -> None:
        if not IMG_NAME_RE.fullmatch(name):  # capability tokens only — blocks path traversal
            await _respond(send, 404, b"not found")
            return
        path = os.path.join(self.settings.out_dir, name)
        if not os.path.isfile(path) or time.time() - os.path.getmtime(path) > self.settings.img_ttl:
            await _respond(send, 404, b"not found or expired")
            return
        with open(path, "rb") as f:
            data = f.read()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"image/png"), (b"content-length", str(len(data)).encode())]})
        await send({"type": "http.response.body", "body": data})


async def _respond(send, status: int, body: bytes) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
