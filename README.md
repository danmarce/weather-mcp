# weather-mcp

Weather as **MCP tools**, over [Open-Meteo](https://open-meteo.com/) — **free, no API key, global**. Each
forecast returns **structured data for the LLM** *and* a **weather card** for the user: a rendered image (as
a short-lived link, not base64), or a monospace text card where no image link can be served, such as over
stdio in Claude Code.

## Tools

| Tool | What it does |
|---|---|
| **get_forecast** | Current conditions + an N-day daily forecast for a place (by name or lat/lon). Returns the data as text + a `card_markdown` for the model to put in its reply. `card`: `auto` (default), `image`, `text` or `none`. |
| **geocode** | Resolve a place name to candidate coordinates (name, region, country, lat/lon, timezone). |

`card="auto"` gives an image link when the server can serve one (streamable-http with `WEATHER_PUBLIC_URL`
set) and the text card otherwise. A caller whose client doesn't display images from links can ask for
`card="text"` on any transport. The result's `card` field echoes the form actually returned.

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
internal container address. Without it, the card is text instead of an image link.

### Claude Desktop / Claude Code (stdio)

```json
{
  "mcpServers": {
    "weather": { "command": "uv", "args": ["--directory", "/path/to/weather-mcp", "run", "weather-mcp", "serve"] }
  }
}
```

Over stdio there is no HTTP server to serve `/img/<token>`, so the card comes back as monospace text in a
```` ```text ```` fence (`WEATHER_PUBLIC_URL` is ignored). It renders cleanly in Claude Code's terminal and
in Claude Desktop.

## Config (env)

| Var | Default | Notes |
|---|---|---|
| `WEATHER_MCP_TOKEN` | — | Bearer required on streamable-http when set. |
| `WEATHER_PUBLIC_URL` | — | Browser-reachable base URL; enables the image card link (HTTP only). |
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
