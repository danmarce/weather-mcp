"""Render a weather card as monospace TEXT — the card for clients that can't load an image link (stdio:
Claude Code, Claude Desktop). Same data as card.py's PNG, drawn with box-drawing characters and small
ASCII icons, meant to be shown inside a ```text fence. Widths are measured in terminal cells (East-Asian
wide characters count 2), so a place name like 東京 doesn't break the frame."""

from __future__ import annotations

import datetime
import unicodedata
from typing import Any

# 5 lines x 13 cells, pure ASCII so every monospace font aligns them.
ICONS: dict[str, list[str]] = {
    "clear": [
        "    \\   /    ",
        "     .-.     ",
        "  - (   ) -  ",
        "     `-'     ",
        "    /   \\    ",
    ],
    "moon": [
        "     _..     ",
        "   .' .'     ",
        "  |  (       ",
        "   '._'.     ",
        "             ",
    ],
    "partly": [
        "  \\  |  /    ",
        "  - .--.     ",
        "  .(    ).   ",
        " (___.__)_)  ",
        "             ",
    ],
    "cloud": [
        "             ",
        "    .--.     ",
        " .-(    ).   ",
        "(___.__)__)  ",
        "             ",
    ],
    "fog": [
        "             ",
        " _ - _ - _ - ",
        "  _ - _ - _  ",
        " _ - _ - _ - ",
        "             ",
    ],
    "drizzle": [
        "    .--.     ",
        " .-(    ).   ",
        "(___.__)__)  ",
        "  ,   ,   ,  ",
        "    ,   ,    ",
    ],
    "rain": [
        "    .--.     ",
        " .-(    ).   ",
        "(___.__)__)  ",
        "  ' ' ' ' '  ",
        " ' ' ' ' '   ",
    ],
    "snow": [
        "    .--.     ",
        " .-(    ).   ",
        "(___.__)__)  ",
        "  *  *  *    ",
        "    *  *  *  ",
    ],
    "storm": [
        "    .--.     ",
        " .-(    ).   ",
        "(___.__)__)  ",
        "   /_  /_    ",
        "    /   /    ",
    ],
}

COL = 14        # inner width of one daily column
MAX_DAYS = 4    # keeps the card under 80 columns (the full forecast is in the data)
MIN_INNER = 46


def _cw(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _width(s: str) -> int:
    return sum(_cw(c) for c in s)


def _fit(s: str, w: int) -> str:
    """Pad or truncate `s` to exactly `w` terminal cells."""
    if _width(s) <= w:
        return s + " " * (w - _width(s))
    out, used = "", 0
    for c in s:
        if used + _cw(c) > w - 1:
            break
        out += c
        used += _cw(c)
    return out + "…" + " " * (w - 1 - used)


def _num(v: Any, digits: int = 0) -> str:
    if v is None:
        return "--"
    return f"{v:.{digits}f}" if digits else str(round(v))


def _compass(deg: Any) -> str:
    if deg is None:
        return ""
    pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return pts[int((float(deg) % 360) / 22.5 + 0.5) % 16]


def _day_label(date: str | None) -> str:
    if not date:
        return ""
    try:
        return datetime.date.fromisoformat(date[:10]).strftime("%a %d")
    except ValueError:
        return date[:10]


def render_text_card(place: str, data: dict[str, Any]) -> str:
    cur = data["current"]
    u = data["units"]
    tu, wu, pu = u["temperature"], u["wind_speed"], u["precipitation"]
    days = (data.get("daily") or [])[:MAX_DAYS]
    n = max(len(days), 1)
    # Each daily cell is "│ " + text + " ", so n cells span sum(cols) + 3n - 3 inner cells.
    inner = max(MIN_INNER, n * (COL + 3) - 3)
    room = inner + 3 - 3 * n                     # cells left for the column texts
    cols = [room // n] * n
    cols[-1] += room - sum(cols)

    icon_kind = cur.get("icon", "cloud")
    if icon_kind == "clear" and not cur.get("is_day", True):
        icon_kind = "moon"
    icon = ICONS.get(icon_kind, ICONS["cloud"])

    feels = cur.get("apparent_temperature")
    wind = f"Wind {_num(cur.get('wind_speed'))} {wu} {_compass(cur.get('wind_direction'))}".rstrip()
    facts = [
        cur.get("condition", ""),
        f"{_num(cur.get('temperature'))}{tu}" + (f"  (feels {_num(feels)}{tu})" if feels is not None else ""),
        f"Humidity {_num(cur.get('humidity'))}%",
        wind,
        f"Precip {_num(cur.get('precipitation'), 1)} {pu}",
    ]

    lines = ["┌" + "─" * (inner + 2) + "┐"]
    lines.append("│ " + _fit(place, inner) + " │")
    lines.append("│ " + " " * inner + " │")
    for art, fact in zip(icon, facts):
        lines.append("│ " + _fit(f"{art}   {fact}", inner) + " │")

    if days:
        lines.append("├" + "┬".join("─" * (c + 2) for c in cols) + "┤")
        rows = [
            [_day_label(d.get("date")) for d in days],
            [d.get("condition", "") for d in days],
            [f"{_num(d.get('temp_max'))}° / {_num(d.get('temp_min'))}°" for d in days],
            [f"{_num(d.get('precipitation_probability_max'))}% · {_num(d.get('precipitation_sum'), 1)} {pu}"
             for d in days],
        ]
        for row in rows:
            lines.append("│ " + " │ ".join(_fit(v, c) for v, c in zip(row, cols)) + " │")
        lines.append("└" + "┴".join("─" * (c + 2) for c in cols) + "┘")
    else:
        lines.append("└" + "─" * (inner + 2) + "┘")
    return "\n".join(lines)
