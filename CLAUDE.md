# CLAUDE.md — weather-mcp

Context for Claude Code sessions in this repo. Read `~/.claude/mcp-server-standard.md` first — this server
follows it; `C:\Code\forge-mcp` is the reference implementation. This file records the *why* so a future
session doesn't undo a deliberate choice.

## What this is

A thin MCP server over **Open-Meteo** (free, **no API key**, global) that returns, for a location, both:
- **structured weather DATA** in the result's text block — what the LLM reasons over and answers from; and
- a rendered **weather card image**, returned as a short-lived **capability link** (`card_url`), not base64.

Built because OpenWebUI's existing weather *tool* returned only an image → the model got no data to reason
over. The fix is a tool that returns data as text AND the card as a link (so a non-vision local model like
Yuki's Gemma still answers from the data, while the human sees the card). Deploys behind mcpo → OWUI, same
as igepn-mcp / news-mcp.

## Deliberate choices (don't undo)

- **Open-Meteo, not Pirate Weather / OpenWeatherMap.** Keyless beats one-more-key (no secret to manage),
  it's global (covers Quito), and it's a sanctioned open API (data-access *with the grain* — no scraping).
  Pirate Weather is already in Home Assistant; weather-mcp stays decoupled from HA on purpose.
- **Image as a LINK, never base64** (mcp-server-standard §4). A card is small, but the principle holds: the
  card is served at `/img/<token>` (unguessable capability name, TTL GC, path-traversal-safe) exactly like
  forge-mcp's full-res images. `WEATHER_PUBLIC_URL` **must be browser-reachable** — OWUI loads the card
  client-side, so it can't be the internal `172.82.0.x` container IP; use a `casita.digital` name or
  `yuki:port`. Without `WEATHER_PUBLIC_URL` set, the tool returns data only (no card link) and says so.
- **`card_markdown` in the result + a docstring instruction** so the model embeds the card in its reply.
  That's how the human sees the image without the bytes entering model context.
- **Stateless** (standard §5): no cache, no DB. Inputs pass through verbatim; resolved coordinates + units
  are echoed so a result is reproducible. The caller owns any state.
- **All four hints explicit** on both tools (standard §1): read-only, non-destructive, idempotent,
  **openWorld = true** (both reach the public Open-Meteo API — judged by behaviour, not name).
- **ok / refused / error** result contract (standard §3): a place that matched nothing is a *refused* (with
  `advice`), never an exception; Open-Meteo unreachable is an *error*. Never a silent empty result.
- **Asset-free card** (card.py): Pillow 11's `ImageFont.load_default(size=...)` + primitive-drawn icons, so
  there's no bundled TTF/PNG to ship. Good enough to be legible; it's a status card, not art.

## Default location = city-level, never home PII

`WEATHER_DEFAULT_LAT/LON/NAME` defaults to **Quito city centre** (public, city-level). The **home
coordinates are location PII** and live in 1Password, never here (see the homelab repo's
`location-pii-is-secret-tier`). Don't hardcode a precise home default.

## Layout

`src/weather_mcp/`: `config.py` (env settings), `openmeteo.py` (forecast + geocoding client, WMO code map —
the MockTransport target), `card.py` (PNG render), `server.py` (tools + status contract + `/img` +
`BearerAuth`), `__init__.py` (`main()` / argparse / stdio|http). Tools: **get_forecast**, **geocode**.

## Tests

`tests/test_tools.py` — calls each tool by name through the server against a `FakeOpenMeteo`
(`httpx.MockTransport`, no network): asserts title + all four hints in the wire JSON, the data+card result,
geocode-then-forecast, and refused/error. `uv run pytest`. Behind the LAN TLS proxy, `uv` needs
`--system-certs` (sync/run).

## Not built yet (documented layers, add when wanted)

- **Alerts / air-quality / historical** — Open-Meteo has air-quality + archive APIs; add as tools if useful.
- **Hourly forecast** — currently current + daily only.
- **Richer card** — a bundled font + a background per condition/time-of-day if the default card feels plain.
