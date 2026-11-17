"""CODE MINI 1000T programmer surface: attribute keys, encoder wheels A/B/C, Locate.

Each fixture type in the console library has a table of 40 *slots* (coarse/fine
channel numbers).  The attribute keys show three slots on the wheels A, B and C;
pressing the key again shows the second page (slot + 20).  The mapping below was
taken from the console screens, e.g. CM-280 on ``Tilt/Pan`` shows "- / Tilt / Pan",
on ``Beam`` "Zoom / Focus / -", the strobe on ``Dimmer`` "Dimmer / - / Dimmer BL".
"""
from __future__ import annotations

from .model import FixtureType

# key -> slots shown on wheels (A, B, C) on page 1 (page 2 = +20)
ATTRIBUTE_KEYS: dict[str, tuple] = {
    "Dimmer": (0, 1, 3),
    "Tilt/Pan": (None, 4, 5),
    "Colour": (None, 6, 7),
    "Colour Mix": (18, 19, 17),
    "Gobo1": (None, 10, 11),
    "Gobo2": (None, 12, 13),
    "Beam": (8, 9, 2),
    "Effect": (None, 16, None),
    "Control": (None, 14, 15),
}
KEYS = list(ATTRIBUTE_KEYS)
WHEELS = "ABC"
NSLOTS = 40

# where a channel goes when a fixture type has no console slot table (user / built-in types)
_DEFAULT_SLOT = {
    "dimmer": 0, "white": 1, "strobe": 2, "shutter": 3, "tilt": 4, "pan": 5,
    "color": 6, "effect": 7, "zoom": 8, "focus": 9, "gobo": 10, "frost": 11,
    "gobo_rot": 13, "speed": 14, "control": 15, "prism_rot": 16, "blue": 17,
    "red": 18, "green": 19, "prism": 36, "iris": 22, "colormacro": 26, "amber": 21,
    "uv": 23, "cyan": 38, "magenta": 39, "yellow": 37, "ctc": 27, "fog": 20, "fan": 34,
}


def type_slots(ft: FixtureType) -> list[list[int]]:
    """40 [coarse, fine] (1 based channel numbers, 0 = empty) for a fixture type."""
    if ft.slots and len(ft.slots) >= NSLOTS:
        return ft.slots
    slots = [[0, 0] for _ in range(NSLOTS)]
    used = set()
    fine_of = {}
    for i, c in enumerate(ft.channels):
        if c.attr.endswith("_fine"):
            fine_of[c.attr[:-5]] = i + 1
    second = {"gobo": 12, "color": 24}            # second gobo / colour wheel
    for i, c in enumerate(ft.channels):
        a = c.attr
        if a.endswith("_fine") or a == "none":
            continue
        s = _DEFAULT_SLOT.get(a)
        if s is not None and s in used and a in second:
            s = second[a]
        if s is None or s in used:
            s = next((k for k in range(20, NSLOTS) if k not in used and k not in _DEFAULT_SLOT.values()), None)
        if s is None:
            continue
        used.add(s)
        slots[s] = [i + 1, fine_of.get(a, 0)]
    return slots


def wheel_slot(key: str, page: int, wheel: int) -> int | None:
    s = ATTRIBUTE_KEYS[key][wheel]
    if s is None:
        return None
    return s + 20 * (page % 2)


def slot_channel(ft: FixtureType, slot: int | None) -> tuple[int, int] | None:
    """(coarse index, fine index or -1), 0 based, of a slot – None if empty."""
    if slot is None:
        return None
    sl = type_slots(ft)
    if slot >= len(sl):
        return None
    c, f = sl[slot]
    if not c or c > len(ft.channels):
        return None
    return c - 1, (f - 1 if f and f <= len(ft.channels) else -1)


def wheel_label(ft: FixtureType, key: str, page: int, wheel: int) -> str:
    ch = slot_channel(ft, wheel_slot(key, page, wheel))
    return ft.channels[ch[0]].name if ch else ""


def key_has_channels(ft: FixtureType, key: str) -> bool:
    return any(slot_channel(ft, wheel_slot(key, p, w)) for p in (0, 1) for w in range(3))


def key_pages(fts: list[FixtureType], key: str) -> int:
    """1 or 2: does any selected type use the second page of this key?"""
    for ft in fts:
        if any(slot_channel(ft, wheel_slot(key, 1, w)) for w in range(3)):
            return 2
    return 1


def fmt_value(v: int) -> str:
    """Console style: '50% (128)'."""
    return f"{round(v * 100 / 255)}% ({v})"


# ------------------------------------------------------------------ locate
def locate_values(ft: FixtureType) -> dict[int, int]:
    """Console 'Locate': full, open white, pan/tilt centre, beam effects off."""
    out = {}
    moving = ft.is_moving
    for i, c in enumerate(ft.channels):
        a = c.attr
        if a == "dimmer":
            out[i] = 255
        elif a == "shutter":
            out[i] = 255 if moving else 0
        elif a == "strobe":
            out[i] = 0
        elif a in ("pan", "tilt"):
            out[i] = 128
        elif a in ("pan_fine", "tilt_fine"):
            out[i] = 0
        elif a in ("red", "green", "blue", "white"):
            out[i] = 255
        elif a in ("amber", "uv", "cyan", "magenta", "yellow", "color", "gobo", "gobo_rot", "prism",
                   "prism_rot", "frost", "effect", "colormacro", "ctc"):
            out[i] = 0
        elif a in ("zoom", "focus"):
            out[i] = 128
        elif a == "iris":
            out[i] = 0
    return out


def open_full_values(ft: FixtureType) -> dict[int, int]:
    """'Fixture Open/Full': intensity full and shutter open (nothing else touched)."""
    out = {}
    for i, c in enumerate(ft.channels):
        if c.attr == "dimmer":
            out[i] = 255
        elif c.attr == "shutter":
            out[i] = 255 if ft.is_moving else 0
    if not any(c.attr == "dimmer" for c in ft.channels):     # RGB only fixtures: white
        for i, c in enumerate(ft.channels):
            if c.attr in ("red", "green", "blue", "white"):
                out[i] = 255
    return out


def even_odd(selection: list[int], state: int) -> tuple[list[int], int]:
    """Even/Odd key: 0 = all, 1 = odd positions, 2 = even positions (in selection order)."""
    state = (state + 1) % 3
    if state == 0:
        return list(selection), 0
    return [f for k, f in enumerate(selection) if (k % 2 == 0) == (state == 1)], state
