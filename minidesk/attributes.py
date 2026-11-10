"""Attribute inference and colour helpers.

Fixture channels from the MINI 1000 console only carry a free-text name
("Dimmer", "Pan", "Col.Mix 1", ...).  This module maps those names to a small
set of attribute keys the engine and the visualizer understand.
"""
from __future__ import annotations

import re

# Feature groups (used to organise the programmer, like dot2 / QLC+)
FEATURE_OF = {
    "dimmer": "Intensity",
    "shutter": "Intensity",
    "strobe": "Intensity",
    "pan": "Position", "pan_fine": "Position",
    "tilt": "Position", "tilt_fine": "Position",
    "speed": "Position",
    "red": "Color", "green": "Color", "blue": "Color", "white": "Color",
    "amber": "Color", "uv": "Color", "cyan": "Color", "magenta": "Color",
    "yellow": "Color", "color": "Color", "color_fine": "Color",
    "colormacro": "Color", "ctc": "Color",
    "gobo": "Beam", "gobo_rot": "Beam", "prism": "Beam", "prism_rot": "Beam",
    "frost": "Beam", "zoom": "Beam", "focus": "Beam", "iris": "Beam",
    "fog": "Other", "fan": "Other", "effect": "Other", "control": "Other",
    "none": "Other",
}
FEATURES = ["Intensity", "Position", "Color", "Beam", "Other"]

# Attributes that are mixed Highest-Takes-Precedence between playbacks.
HTP_ATTRS = {"dimmer"}


def infer_attribute(name: str) -> str:
    """Return an attribute key for a channel name."""
    n = name.strip().lower()
    n = re.sub(r"\s+", " ", n)
    if not n or n in {"unused", "-", "none", "nc"}:
        return "none"
    if "fine" in n:
        if "pan" in n:
            return "pan_fine"
        if "tilt" in n:
            return "tilt_fine"
        return "none"
    if re.search(r"\b(dimmer|dim|intensity|master)\b", n) or n.startswith("dimmer"):
        return "dimmer"
    if "x/y speed" in n or "p/t speed" in n or n in {"pt speed", "xy speed"}:
        return "speed"
    if re.fullmatch(r"(x|pan)", n) or n.startswith("pan"):
        return "pan"
    if re.fullmatch(r"(y|tilt)", n) or n.startswith("tilt"):
        return "tilt"
    if "shutter" in n:
        return "shutter"
    if "strobe" in n or "strb" in n:
        return "strobe"
    for key in ("red", "green", "blue", "white", "amber", "cyan", "magenta", "yellow"):
        if re.search(rf"\b{key}\b", n) or n.startswith(key):
            return key
    if n in {"r"}:
        return "red"
    if n in {"g"}:
        return "green"
    if n in {"b"}:
        return "blue"
    if n in {"w"}:
        return "white"
    if re.search(r"\buv\b", n):
        return "uv"
    if "colormacro" in n or "col.mix" in n or "color mix" in n or "colour mix" in n \
            or "color macro" in n:
        return "colormacro"
    if n.startswith("col") or "color" in n or "colour" in n:
        if "speed" in n:
            return "effect"
        return "color"
    if "ctc" in n or "cto" in n:
        return "ctc"
    if "gobo" in n:
        return "gobo_rot" if "rot" in n else "gobo"
    if "prism" in n:
        return "prism_rot" if "rot" in n else "prism"
    if "frost" in n:
        return "frost"
    if "zoom" in n:
        return "zoom"
    if "focus" in n:
        return "focus"
    if "iris" in n:
        return "iris"
    if "fog" in n or "haze" in n or "smoke" in n:
        return "fog"
    if "fan" in n:
        return "fan"
    if "speed" in n:
        return "speed"
    if "effect" in n or "fx" in n or "macro" in n:
        return "effect"
    if "control" in n or "reset" in n or "lamp" in n:
        return "control"
    return "none"


# Approximate colours of a generic 8 slot colour wheel; real fixtures differ,
# but this gives a believable picture in the visualizer.
WHEEL_COLOURS = [
    (255, 255, 255),  # open / white
    (255, 40, 30),    # red
    (255, 140, 20),   # orange
    (255, 230, 40),   # yellow
    (40, 230, 60),    # green
    (40, 90, 255),    # blue
    (230, 40, 230),   # magenta
    (40, 230, 255),   # cyan
    (255, 170, 190),  # pink
    (170, 255, 120),  # light green
    (120, 60, 255),   # congo / uv
]


def wheel_colour(value: int) -> tuple[int, int, int]:
    """Map a colour wheel DMX value to an approximate RGB colour."""
    if value >= 192:  # rotation range on most wheels
        return WHEEL_COLOURS[(value // 4) % 8]
    slot = min(len(WHEEL_COLOURS) - 1, value * len(WHEEL_COLOURS) // 192)
    return WHEEL_COLOURS[slot]
