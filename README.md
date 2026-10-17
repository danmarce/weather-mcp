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
WEATHER_MCP_TOKEN=... WEATHER_PUBLIC_URL=http://your-host:8000 \
  uv run weather-mcp serve --transport http --host 0.0.0.0 --port 8000
uv run pytest                # no network: Open-Meteo is faked
```

`WEATHER_PUBLIC_URL` must be **browser-reachable** (the client loads the card) — a LAN name/IP, not an
internal container address. Without it, tools return data only (no card link).

### Claude Desktop / Claude Code (stdio)

```json
{
  "mcpServers": {
    "weather": { "command": "uv", "args": ["--directory", "/path/to/weather-mcp", "run", "weather-mcp", "serve"] }
  }
}
```

Over stdio there is no HTTP server to serve `/img/<token>`, so leave `WEATHER_PUBLIC_URL` unset: the tools
return the data only, which is what the model answers from anyway.

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

## Docker

```bash
docker build -t weather-mcp .
docker run --rm -p 8000:8000 -e WEATHER_MCP_TOKEN=... -e WEATHER_PUBLIC_URL=http://your-host:8000 weather-mcp
```

The server is stateless: no database, no volume. Card PNGs are written to `WEATHER_OUT_DIR` inside the
container and expire after `WEATHER_IMG_TTL`, so losing them on restart is fine. It needs outbound HTTPS to
the Open-Meteo API (free for non-commercial use, no key).

## Auth and exposure

Auth is deliberately simple: stdio, or streamable-HTTP with a single bearer token (`WEATHER_MCP_TOKEN`) on a
private network, for example behind [mcpo](https://github.com/open-webui/mcpo). `/healthz` stays open, and so
does `/img/*`: the client's browser loads the card without the bearer, so each card URL is an unguessable,
short-lived capability link instead. There is **no OAuth, no users and no audit log**, by design. To publish
it more widely, put a management layer in front of it: an MCP gateway or auth proxy that handles OAuth, users
and audit for all your servers at once.

## AI assistance

weather-mcp is developed openly with the help of Claude (Anthropic). Commits Claude helped write carry a
`Co-Authored-By: Claude` trailer. The code and design are open source so the work can be inspected, reused,
and given back.

## License

[MPL-2.0](LICENSE) © Daniel Núñez.
