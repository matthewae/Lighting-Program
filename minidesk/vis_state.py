"""Turn raw DMX of a fixture into something drawable (no Qt here)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .attributes import gobo_index, range_label, wheel_colour
from .model import Fixture, FixtureType


@dataclass
class VisState:
    intensity: float          # 0..1 after strobe / shutter
    colour: tuple[int, int, int]
    direction: tuple[float, float, float]
    beam_angle: float         # full angle, degrees
    fog: float = 0.0          # 0..1 for fog machines
    has_beam: bool = True
    gobo: int = 0             # 0 = open, n = gobo number, -1 = shake
    gobo_angle: float = 0.0   # degrees
    prism: int = 0            # number of facets (0 = off)
    prism_angle: float = 0.0  # degrees
    frost: float = 0.0        # 0..1
    yaw: float = 0.0          # degrees: fixture facing + pan
    tilt: float = 0.0         # degrees from straight down (hanging) / up (floor)


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
                        ft.beam_angle, 0.0, False, yaw=fx.rot, tilt=fx.aim)
    vals: dict[str, list[int]] = {}
    fine: dict[str, int] = {}
    chan_of: dict[str, object] = {}
    for i, ch in enumerate(ft.channels):
        v = _get(dmx, base, i)
        if ch.attr.endswith("_fine"):
            fine[ch.attr[:-5]] = v
        else:
            vals.setdefault(ch.attr, []).append(v)
            chan_of.setdefault(ch.attr, ch)

    def first(attr, default=0):
        return vals[attr][0] if attr in vals else default

    # --- intensity ------------------------------------------------------
    rgb_attrs = ("red", "green", "blue", "white", "amber", "uv")
    if "dimmer" in vals:
        inten = max(vals["dimmer"]) / 255.0
    elif any(a in vals for a in rgb_attrs):
        inten = 1.0
    else:
        inten = 0.0
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
        yaw, t = fx.rot, fx.aim
        direction = aim_direction(fx.aim, fx.rot, floor)
    # --- beam --------------------------------------------------------------
    moving = ft.is_moving
    angle = ft.beam_angle
    if "zoom" in vals and moving:
        angle = max(2.0, ft.beam_angle * (0.6 + first("zoom") / 255 * 2.0))
    if "iris" in vals and moving:
        angle *= 1.0 - 0.7 * first("iris") / 255
    frost = 0.0
    if "frost" in vals and moving:
        fv = first("frost")
        frost = 0.0 if fv < 8 else (fv - 8) / 247
        angle *= 1.0 + 1.5 * frost

    def rot(attr):
        if attr not in vals:
            return 0.0
        v = first(attr)
        lab = range_label(chan_of[attr].functions(moving), v).lower()
        if "ccw" in lab:
            return -(now * (30 + (v - 192) / 63 * 300)) % 360
        if "cw" in lab or "rotate" in lab:
            return (now * (30 + (v - 128) / 63 * 300)) % 360
        return v / 127 * 360

    gobo = 0
    for a in ("gobo",):
        if a in vals:
            for v, ch in zip(vals[a], [c for c in ft.channels if c.attr == a]):
                g = gobo_index(ch.functions(moving), v)
                if g:
                    gobo = g
                    break
    if gobo == -1:
        gobo = 1 + int(now * 4) % 3          # shake: alternate patterns
    prism = 0
    if "prism" in vals:
        pv = max(vals["prism"])
        lab = range_label(chan_of["prism"].functions(moving), pv).lower()
        if pv >= 8 and "off" not in lab:
            prism = 8 if ("8" in lab or "8" in chan_of["prism"].name) else 3
    prism_angle = rot("prism_rot")
    if prism and "macro" in range_label(chan_of["prism"].functions(moving), max(vals["prism"])).lower() \
            and "prism_rot" not in vals:
        prism_angle = (now * 90) % 360
    fog = 0.0
    if ft.kind == "fog":
        fog = max([max(vals[a]) for a in ("fog", "dimmer") if a in vals] or [0]) / 255.0
    return VisState(intensity=max(0.0, min(1.0, inten * gate)), colour=col, direction=direction,
                    beam_angle=angle, fog=fog, has_beam=ft.kind != "fog" or have_rgb,
                    gobo=gobo, gobo_angle=rot("gobo_rot"), prism=prism, prism_angle=prism_angle,
                    frost=frost, yaw=yaw, tilt=t)
