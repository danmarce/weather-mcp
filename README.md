# weather-mcp

Weather as **MCP tools**, over [Open-Meteo](https://open-meteo.com/) — **free, no API key, global**. Each
forecast returns **structured data for the LLM** *and* a rendered **weather card image** (as a short-lived
link, not base64), so a model can both reason over the numbers and show the user a card.

## Tools

| Tool | What it does |
|---|---|
| **get_forecast** | Current conditions + an N-day daily forecast for a place (by name or lat/lon). Returns the data as text + (default) a `card_url`/`card_markdown` for the card image. |
| **geocode** | Resolve a place name to candidate coordinates (name, region, country, lat/lon, timezone). |

Every result carries a `status`: `ok` / `refused` (caller-fixable input, with `advice`) / `error` (a fault).
Branch on `status`, not prose.

## Why it returns an image *and* data

OpenWebUI's stock weather tool returned only an image — the model got nothing to reason over. This returns
the **data as text** (the model answers from it, even a non-vision local model) and the **card as a link**
the client renders. The image never enters the model's context as bytes (it's an out-of-band capability
link, the forge-mcp pattern).

## Run

```bash
uv sync                      # (--system-certs behind a TLS-inspecting proxy)
# stdio (local MCP client):
uv run weather-mcp serve
# streamable-http (behind mcpo / on the LAN):
WEATHER_MCP_TOKEN=... WEATHER_PUBLIC_URL=http://yuki:8000 \
  uv run weather-mcp serve --transport http --host 0.0.0.0 --port 8000
```

`WEATHER_PUBLIC_URL` must be **browser-reachable** (the client loads the card) — a LAN name/IP, not an
internal container address. Without it, tools return data only (no card link).

## Config (env)

| Var | Default | Notes |
|---|---|---|
| `WEATHER_MCP_TOKEN` | — | Bearer required on streamable-http when set. |
| `WEATHER_PUBLIC_URL` | — | Browser-reachable base URL; enables the card link. |
| `WEATHER_OUT_DIR` | `out` | Where card PNGs are written (served at `/img/<token>`, TTL-GC'd). |
| `WEATHER_IMG_TTL` | `600` | Card link lifetime (seconds). |
| `WEATHER_DEFAULT_LAT/LON/NAME` | Quito (city-level) | Fallback when a call gives neither place nor coords. **Not** home coordinates. |
| `WEATHER_LANGUAGE` | `en` | Geocoding language. |
| `WEATHER_HTTP_TIMEOUT` | `15` | Seconds. |

## Auth & deployment

Transports: **stdio**, or **streamable-http + bearer token** on a private network (behind mcpo). No OAuth
in the server — put a gateway/auth proxy in front if exposing it more widely. `/healthz` is open; `/img/*`
is open (capability-token URLs, short-lived); everything else needs the bearer when a token is set.
Open-Meteo is free for non-commercial use.

## License

MPL-2.0.
