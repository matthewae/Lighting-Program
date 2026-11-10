"""Effect generator (position, intensity and colour effects).

Effects are evaluated every engine frame on top of the mixed values:
position effects add an offset to pan/tilt, intensity effects drive the
dimmer between ``low`` and ``high``, colour effects set RGB/CMY/colour wheel.
"""
from __future__ import annotations

import colorsys
import math

from .attributes import WHEEL_COLOURS
from .model import EFFECT_TYPES, Effect, FixtureType

POSITION = {k for k, (_, f) in EFFECT_TYPES.items() if f == "Position"}
INTENSITY = {k for k, (_, f) in EFFECT_TYPES.items() if f == "Intensity"}
COLOUR = {k for k, (_, f) in EFFECT_TYPES.items() if f == "Color"}


def _hash01(a: int, b: int) -> float:
    x = (a * 73856093) ^ (b * 19349663)
    x = (x ^ (x >> 13)) * 1274126177
    return ((x ^ (x >> 16)) & 0xFFFF) / 65535.0


def fixture_phase(eff: Effect, fid: int) -> float:
    """Phase offset (0..1) of a fixture inside the effect, honouring wings."""
    fx = eff.fixtures
    if fid not in fx or len(fx) < 2:
        return 0.0
    n = len(fx)
    wings = max(1, min(eff.wings, n))
    per = math.ceil(n / wings)
    i = fx.index(fid)
    w, k = divmod(i, per)
    if w % 2 == 1:                       # mirror every second wing
        k = per - 1 - k
    if eff.reverse:
        k = per - 1 - k
    return (k / per) * (eff.spread / 360.0)


def wave(eff: Effect, t: float, fid: int) -> float:
    """Return the effect position in the cycle (0..1) for a fixture."""
    return (t * eff.speed - fixture_phase(eff, fid) + eff.offset / 360.0) % 1.0


def apply_effect(eff: Effect, ft: FixtureType, fid: int, vals: list[int], t: float,
                 level: float = 1.0, age: float = 1e9) -> None:
    """``t`` = effect clock, ``level`` = playback fader, ``age`` = seconds since the effect started."""
    if fid not in eff.fixtures:
        return
    if eff.fade > 0:
        level *= min(1.0, max(0.0, age / eff.fade))
    ph = wave(eff, t, fid)
    a = 2 * math.pi * ph
    chans = ft.channels
    if eff.type in POSITION:
        size = eff.size
        if eff.type == "circle":
            dp, dt = math.sin(a), math.cos(a)
        elif eff.type == "figure8":
            dp, dt = math.sin(a), math.sin(2 * a) * 0.6
        elif eff.type == "pan_wave":
            dp, dt = math.sin(a), 0.0
        elif eff.type == "tilt_wave":
            dp, dt = 0.0, math.sin(a)
        else:   # ballyhoo: two incommensurate sines -> pseudo random sweep
            dp, dt = math.sin(a + 1.3 * math.sin(0.37 * a)), math.sin(1.7 * a + 0.5)
        dp, dt = dp * size * level, dt * size * level
        for i, c in enumerate(chans):
            if c.attr == "pan":
                vals[i] = int(max(0, min(255, vals[i] + dp)))
            elif c.attr == "tilt":
                vals[i] = int(max(0, min(255, vals[i] + dt)))
        return
    if eff.type in INTENSITY:
        if eff.type == "dim_sine":
            v = (math.sin(a) + 1) / 2
        elif eff.type == "dim_pulse":
            v = 1.0 - ph
        elif eff.type == "dim_chase":
            v = 1.0 if ph < eff.duty else 0.0
        elif eff.type == "dim_random":
            cyc = int(t * eff.speed)
            v = 1.0 if _hash01(fid, cyc) > 0.5 else 0.0
        else:   # strobe
            v = 1.0 if ph < eff.duty * 0.3 else 0.0
        out = eff.low + (eff.high - eff.low) * v
        if level < 1.0:        # fade the effect in from the current value
            dims0 = [vals[i] for i, c in enumerate(chans) if c.attr == "dimmer"]
            base = dims0[0] if dims0 else 0
            out = base + (out - base) * level
        dims = [i for i, c in enumerate(chans) if c.attr == "dimmer"]
        if dims:
            for i in dims:
                vals[i] = int(max(0, min(255, out)))
            for i, c in enumerate(chans):
                if c.attr == "shutter" and ft.is_moving and vals[i] < 8:
                    vals[i] = 255
        else:   # no dimmer channel: scale the colour, or use white if nothing is set
            cols = [i for i, c in enumerate(chans) if c.attr in ("red", "green", "blue", "white", "amber", "uv")]
            if any(vals[i] for i in cols):
                for i in cols:
                    vals[i] = int(vals[i] * out / 255.0)
            else:
                whites = [i for i in cols if chans[i].attr == "white"]
                for i in (whites or [i for i in cols if chans[i].attr in ("red", "green", "blue")]):
                    vals[i] = int(out)
        return
    if eff.type in COLOUR:
        if eff.type == "rainbow":
            r, g, b = (int(x * 255) for x in colorsys.hsv_to_rgb(ph, 1, 1))
        else:
            r, g, b = eff.color_a if ph < eff.duty else eff.color_b
        attrs = {c.attr for c in chans}
        if level < 1.0:
            cur = {c.attr: vals[i] for i, c in enumerate(chans)}
            r = int(cur.get("red", r) + (r - cur.get("red", r)) * level)
            g = int(cur.get("green", g) + (g - cur.get("green", g)) * level)
            b = int(cur.get("blue", b) + (b - cur.get("blue", b)) * level)
        for i, c in enumerate(chans):
            if c.attr == "red":
                vals[i] = r
            elif c.attr == "green":
                vals[i] = g
            elif c.attr == "blue":
                vals[i] = b
            elif c.attr in ("white", "amber", "uv") and attrs & {"red", "green", "blue"}:
                vals[i] = 0
            elif c.attr == "cyan":
                vals[i] = 255 - r
            elif c.attr == "magenta":
                vals[i] = 255 - g
            elif c.attr == "yellow":
                vals[i] = 255 - b
            elif c.attr == "color" and not attrs & {"red", "green", "blue", "cyan"}:
                best = min(range(len(WHEEL_COLOURS)),
                           key=lambda j: sum((x - y) ** 2 for x, y in zip(WHEEL_COLOURS[j], (r, g, b))))
                vals[i] = int(best * 192 / len(WHEEL_COLOURS)) + 2
