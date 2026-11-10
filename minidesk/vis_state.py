"""Turn raw DMX of a fixture into something drawable (no Qt here)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .attributes import wheel_colour
from .model import Fixture, FixtureType


@dataclass
class VisState:
    intensity: float          # 0..1 after strobe / shutter
    colour: tuple[int, int, int]
    direction: tuple[float, float, float]
    beam_angle: float         # full angle, degrees
    fog: float = 0.0          # 0..1 for fog machines
    has_beam: bool = True


def _get(dmx: bytes, base: int, i: int) -> int:
    a = base + i
    return dmx[a] if 0 <= a < len(dmx) else 0


def aim_direction(tilt_deg: float, yaw_deg: float, floor: bool) -> tuple[float, float, float]:
    t = math.radians(tilt_deg)
    dx, dy, dz = 0.0, -math.sin(t), (math.cos(t) if floor else -math.cos(t))
    y = math.radians(yaw_deg)
    c, s = math.cos(y), math.sin(y)
    return (dx * c - dy * s, dx * s + dy * c, dz)


def strobe_gate(value: int, moving: bool, attr: str, now: float) -> float:
    """Return 0..1 multiplier for shutter / strobe channels."""
    if attr == "shutter" and moving:
        if value < 8:
            return 0.0
        if value >= 248:
            return 1.0
        freq = 1 + (value - 8) / 240 * 19
    else:
        if value <= 10:
            return 1.0
        freq = 1 + (value - 11) / 244 * 24
    return 1.0 if (now * freq) % 1.0 < 0.3 else 0.0


def compute(fx: Fixture, ft: FixtureType, dmx: bytes, now: float) -> VisState:
    base = fx.address - 1
    if not fx.patched:
        return VisState(0.0, (0, 0, 0), aim_direction(fx.aim, fx.rot, fx.mount == "floor"),
                        ft.beam_angle, 0.0, False)
    vals: dict[str, list[int]] = {}
    fine: dict[str, int] = {}
    for i, ch in enumerate(ft.channels):
        v = _get(dmx, base, i)
        if ch.attr.endswith("_fine"):
            fine[ch.attr[:-5]] = v
        else:
            vals.setdefault(ch.attr, []).append(v)

    def first(attr, default=0):
        return vals[attr][0] if attr in vals else default

    # --- intensity ------------------------------------------------------
    rgb_attrs = ("red", "green", "blue", "white", "amber", "uv")
    if "dimmer" in vals:
        inten = max(vals["dimmer"]) / 255.0
    elif any(a in vals for a in rgb_attrs):
        inten = 1.0
    else:
        inten = 0.0 if ft.kind != "fog" else 0.0
    gate = 1.0
    for attr in ("shutter", "strobe"):
        if attr in vals:
            gate = min(gate, strobe_gate(vals[attr][0], ft.is_moving, attr, now))
    # --- colour -----------------------------------------------------------
    r = g = b = 0.0
    have_rgb = False
    if any(a in vals for a in ("red", "green", "blue")):
        have_rgb = True
        r, g, b = max(vals.get("red", [0])), max(vals.get("green", [0])), max(vals.get("blue", [0]))
    if "white" in vals:
        have_rgb = True
        w = max(vals["white"])
        r, g, b = r + w * 0.9, g + w * 0.9, b + w * 0.85
    if "amber" in vals:
        have_rgb = True
        a = max(vals["amber"])
        r, g = r + a, g + a * 0.55
    if "uv" in vals:
        have_rgb = True
        u = max(vals["uv"])
        r, b = r + u * 0.35, b + u * 0.8
    if have_rgb:
        m = max(r, g, b)
        if m <= 0:
            inten_rgb = 0.0
            col = (0, 0, 0)
        else:
            inten_rgb = min(1.0, m / 255.0)
            col = (int(r / m * 255), int(g / m * 255), int(b / m * 255))
        inten *= inten_rgb
    else:
        col = (255, 225, 180) if ft.kind in ("fresnel", "generic") else (255, 255, 255)
        if any(a in vals for a in ("cyan", "magenta", "yellow")):
            col = (255 - first("cyan"), 255 - first("magenta"), 255 - first("yellow"))
        elif "color" in vals:
            col = wheel_colour(first("color"))
    # --- position --------------------------------------------------------
    floor = fx.mount == "floor"
    if "pan" in vals or "tilt" in vals:
        pan = (first("pan", 128) * 256 + fine.get("pan", 0)) / 65535.0
        tilt = (first("tilt", 128) * 256 + fine.get("tilt", 0)) / 65535.0
        yaw = fx.rot + (pan - 0.5) * ft.pan_range
        t = (tilt - 0.5) * ft.tilt_range
        direction = aim_direction(t, yaw, floor)
    else:
        direction = aim_direction(fx.aim, fx.rot, floor)
    # --- beam --------------------------------------------------------------
    angle = ft.beam_angle
    if "zoom" in vals and ft.kind == "moving":
        angle = max(2.0, ft.beam_angle * (0.6 + first("zoom") / 255 * 2.0))
    if "frost" in vals and first("frost") > 20 and ft.kind == "moving":
        angle *= 1.8
    fog = 0.0
    if ft.kind == "fog":
        fog = max([max(vals[a]) for a in ("fog", "dimmer") if a in vals] or [0]) / 255.0
    return VisState(intensity=max(0.0, min(1.0, inten * gate)), colour=col, direction=direction,
                    beam_angle=angle, fog=fog, has_beam=ft.kind != "fog" or have_rgb)
