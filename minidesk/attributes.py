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


# --------------------------------------------------------------------------
# Generic channel functions (used when a fixture profile has no ranges).
def _slots(prefix: str, n: int, start: int, width: int) -> list:
    return [[start + i * width, start + (i + 1) * width - 1, f"{prefix} {i + 1}"] for i in range(n)]


def generic_ranges(attr: str, moving: bool = True) -> list:
    if attr == "gobo":
        return [[0, 7, "Open"]] + _slots("Gobo", 8, 8, 16) + [[136, 255, "Gobo shake / scroll"]]
    if attr == "gobo_rot":
        return [[0, 127, "Index (angle)"], [128, 191, "Rotate CW"], [192, 255, "Rotate CCW"]]
    if attr == "prism":
        return [[0, 7, "Prism off"], [8, 127, "Prism on"], [128, 255, "Prism on + macro"]]
    if attr == "prism_rot":
        return [[0, 127, "Index (angle)"], [128, 191, "Rotate CW"], [192, 255, "Rotate CCW"]]
    if attr == "frost":
        return [[0, 7, "Frost off"], [8, 255, "Frost 0–100 %"]]
    if attr == "color":
        names = ["Open/White", "Red", "Orange", "Yellow", "Green", "Blue", "Magenta", "Cyan", "Pink",
                 "Light green", "Congo/UV"]
        w = 192 // len(names)
        out = [[i * w, (i + 1) * w - 1, n] for i, n in enumerate(names)]
        out[-1][1] = 191
        return out + [[192, 255, "Rainbow scroll"]]
    if attr == "shutter":
        if moving:
            return [[0, 7, "Closed"], [8, 247, "Strobe slow → fast"], [248, 255, "Open"]]
        return [[0, 10, "Open / no strobe"], [11, 255, "Strobe slow → fast"]]
    if attr == "strobe":
        return [[0, 10, "No strobe"], [11, 255, "Strobe slow → fast"]]
    if attr == "zoom":
        return [[0, 255, "Narrow → wide"]]
    if attr == "focus":
        return [[0, 255, "Near → far"]]
    if attr == "iris":
        return [[0, 255, "Open → closed"]]
    if attr == "control":
        return [[0, 99, "No function"], [100, 199, "Lamp on / special"], [200, 255, "Reset (hold 3 s)"]]
    return []


def range_label(ranges: list, value: int) -> str:
    for lo, hi, label in ranges:
        if lo <= value <= hi:
            return label
    return ""


def gobo_index(ranges: list, value: int) -> int:
    """0 = open, 1..n = gobo number, -1 = shake/scroll (generic)."""
    label = range_label(ranges, value).lower()
    if not label or "open" in label:
        return 0
    digits = "".join(ch for ch in label if ch.isdigit())
    if label.startswith("gobo") and digits:
        return int(digits)
    return -1 if "shake" in label or "scroll" in label else 1
