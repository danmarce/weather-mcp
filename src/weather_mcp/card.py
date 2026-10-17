"""Render a weather card PNG (the human-facing image). Kept asset-free on purpose: Pillow 11's
`ImageFont.load_default(size=...)` gives scalable text with no bundled TTF, and the condition icons are
drawn from primitives. The card is the *image* half of the tool result; the structured data is the
*text* half the LLM reasons over. Bytes go to an out-of-band capability link, never base64 in context."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw, ImageFont

W, H = 820, 380
PAD = 28

# Palette by day/night; condition tints the header band.
BG_DAY = (36, 48, 66)
BG_NIGHT = (20, 26, 40)
FG = (236, 240, 248)
MUTED = (150, 162, 182)
ACCENT = (250, 204, 86)   # sun / warm
COOL = (120, 180, 240)    # cloud / cool
RAIN = (96, 150, 224)
STORM = (180, 140, 240)


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)   # Pillow >= 10.1
    except TypeError:  # very old Pillow: fixed-size bitmap fallback
        return ImageFont.load_default()


def _icon(d: ImageDraw.ImageDraw, kind: str, cx: int, cy: int, r: int) -> None:
    """Draw a small weather glyph centred at (cx, cy) with nominal radius r."""
    if kind == "clear":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
        for a in range(0, 360, 45):
            import math
            dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
            d.line([cx + dx * (r + 6), cy + dy * (r + 6), cx + dx * (r + 16), cy + dy * (r + 16)],
                   fill=ACCENT, width=4)
        return
    if kind == "partly":
        d.ellipse([cx - r, cy - r - 8, cx + r - 6, cy + r - 14], fill=ACCENT)
    cloud = COOL if kind in ("partly", "cloud", "fog") else (208, 214, 226)
    d.ellipse([cx - r, cy - 4, cx, cy + r], fill=cloud)
    d.ellipse([cx - r // 2, cy - r, cx + r // 2, cy], fill=cloud)
    d.ellipse([cx, cy - 4, cx + r, cy + r], fill=cloud)
    d.rectangle([cx - r, cy + r // 2, cx + r, cy + r], fill=cloud)
    if kind in ("rain", "drizzle"):
        for i in range(-1, 2):
            d.line([cx + i * 14, cy + r + 4, cx + i * 14 - 4, cy + r + 18], fill=RAIN, width=4)
    elif kind == "storm":
        d.line([cx - 2, cy + r, cx - 10, cy + r + 16], fill=STORM, width=4)
        d.line([cx - 10, cy + r + 16, cx + 2, cy + r + 16], fill=STORM, width=4)
        d.line([cx + 2, cy + r + 16, cx - 6, cy + r + 30], fill=STORM, width=4)
    elif kind == "snow":
        for i in range(-1, 2):
            d.text((cx + i * 14 - 5, cy + r + 2), "*", font=_font(22), fill=(220, 230, 245))


def render_card(place: str, data: dict[str, Any]) -> bytes:
    cur = data["current"]
    daily = data.get("daily") or []
    tu = data["units"]["temperature"]
    wu = data["units"]["wind_speed"]
    img = Image.new("RGB", (W, H), BG_DAY if cur.get("is_day", True) else BG_NIGHT)
    d = ImageDraw.Draw(img)

    # Header: place + current condition
    d.text((PAD, PAD), place, font=_font(34), fill=FG)
    d.text((PAD, PAD + 44), cur.get("condition", ""), font=_font(22), fill=MUTED)

    # Big current temperature + icon
    temp = cur.get("temperature")
    d.text((PAD, PAD + 86), f"{round(temp)}{tu}" if temp is not None else "--", font=_font(84), fill=FG)
    _icon(d, cur.get("icon", "cloud"), W - 120, PAD + 70, 34)

    feels = cur.get("apparent_temperature")
    bits = []
    if feels is not None:
        bits.append(f"Feels {round(feels)}{tu}")
    if cur.get("humidity") is not None:
        bits.append(f"Hum {cur['humidity']}%")
    if cur.get("wind_speed") is not None:
        bits.append(f"Wind {round(cur['wind_speed'])} {wu}")
    d.text((PAD, PAD + 184), "   ".join(bits), font=_font(20), fill=MUTED)

    # Daily strip (up to 5)
    strip = daily[:5]
    if strip:
        col_w = (W - 2 * PAD) // len(strip)
        y0 = H - 118
        d.line([PAD, y0 - 14, W - PAD, y0 - 14], fill=(60, 72, 92), width=1)
        for i, day in enumerate(strip):
            cx = PAD + col_w * i + col_w // 2
            label = _weekday(day.get("date"))
            d.text((cx - _w(d, label, 18) // 2, y0), label, font=_font(18), fill=MUTED)
            _icon(d, day.get("icon", "cloud"), cx, y0 + 46, 16)
            hi = day.get("temp_max"); lo = day.get("temp_min")
            txt = f"{round(hi) if hi is not None else '--'}/{round(lo) if lo is not None else '--'}"
            d.text((cx - _w(d, txt, 18) // 2, y0 + 78), txt, font=_font(18), fill=FG)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _w(d: ImageDraw.ImageDraw, text: str, size: int) -> int:
    box = d.textbbox((0, 0), text, font=_font(size))
    return box[2] - box[0]


def _weekday(date: str | None) -> str:
    if not date:
        return ""
    import datetime
    try:
        return datetime.date.fromisoformat(date[:10]).strftime("%a")
    except ValueError:
        return date[5:10]
