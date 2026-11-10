"""Effect generator: position shapes, intensity, colour and beam effects.

Effects are evaluated every engine frame on top of the mixed values:
* position shapes add an offset (``size`` DMX steps) to pan/tilt
* intensity effects drive the dimmer between ``low`` and ``high``
* colour effects set RGB / CMY / colour wheel
* beam effects move gobo / zoom / focus / iris / prism / frost channels

Parameters (like a console effect engine): speed (cycles/s = BPM/60), size,
low/high, phase spread across the fixtures, phase offset, wings (mirrored
groups), duty (on-time for step / strobe shapes), fade-in and direction.
"""
from __future__ import annotations

import colorsys
import math

from .attributes import WHEEL_COLOURS
from .model import EFFECT_TYPES, Effect, FixtureType

POSITION = {k for k, (_, f) in EFFECT_TYPES.items() if f == "Position"}
INTENSITY = {k for k, (_, f) in EFFECT_TYPES.items() if f == "Intensity"}
COLOUR = {k for k, (_, f) in EFFECT_TYPES.items() if f == "Color"}
BEAM = {k for k, (_, f) in EFFECT_TYPES.items() if f == "Beam"}

RGB_STEPS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
PALETTE = [(255, 0, 0), (255, 120, 0), (255, 230, 0), (0, 255, 0), (0, 230, 255), (0, 0, 255),
           (160, 0, 255), (255, 0, 200), (255, 255, 255)]


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
    """Position of a fixture in the effect cycle (0..1)."""
    return (t * eff.speed - fixture_phase(eff, fid) + eff.offset / 360.0) % 1.0


# ------------------------------------------------------------- wave forms
def tri(ph: float) -> float:
    """Triangle -1..1..-1."""
    return 4 * ph - 1 if ph < 0.5 else 3 - 4 * ph


def saw(ph: float) -> float:
    return 2 * ph - 1


def _polyline(points: list, ph: float) -> tuple[float, float]:
    """Walk a closed polygon at constant speed."""
    n = len(points)
    x = ph * n
    i = int(x) % n
    f = x - int(x)
    a, b = points[i], points[(i + 1) % n]
    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f


STAR = [(math.sin(2 * math.pi * k * 2 / 5), math.cos(2 * math.pi * k * 2 / 5)) for k in range(5)]


def shape_xy(kind: str, ph: float, fid: int = 0, t: float = 0.0, speed: float = 1.0) -> tuple[float, float]:
    """Normalised pan/tilt offset (-1..1) of a position shape."""
    a = 2 * math.pi * ph
    if kind == "circle":
        return math.sin(a), math.cos(a)
    if kind == "ellipse":
        return math.sin(a), 0.45 * math.cos(a)
    if kind == "diamond":
        return _polyline([(0, 1), (1, 0), (0, -1), (-1, 0)], ph)
    if kind == "square":
        return _polyline([(-1, 1), (1, 1), (1, -1), (-1, -1)], ph)
    if kind == "triangle":
        return _polyline([(0, 1), (0.87, -0.5), (-0.87, -0.5)], ph)
    if kind == "figure8":
        return math.sin(a), 0.6 * math.sin(2 * a)
    if kind == "s_shape":
        y = tri(ph)
        return math.sin(1.5 * math.pi * y) * 0.9, y
    if kind == "cross":
        return (tri(ph * 2 % 1.0), 0.0) if ph < 0.5 else (0.0, tri(ph * 2 % 1.0))
    if kind == "star":
        return _polyline(STAR, ph)
    if kind == "spiral":
        r = (tri(ph) + 1) / 2
        b = a * 4
        return r * math.sin(b), r * math.cos(b)
    if kind == "pan_saw":
        return saw(ph), 0.0
    if kind == "tilt_saw":
        return 0.0, saw(ph)
    if kind == "pan_wave":
        return math.sin(a), 0.0
    if kind == "tilt_wave":
        return 0.0, math.sin(a)
    if kind == "pan_swing":
        return tri(ph), 0.0
    if kind == "tilt_swing":
        return 0.0, tri(ph)
    if kind == "pan_step":
        return (1.0 if ph < 0.5 else -1.0), 0.0
    if kind == "tilt_step":
        return 0.0, (1.0 if ph < 0.5 else -1.0)
    if kind == "pos_random":
        cyc = int(t * speed + ph)            # new random point every cycle, smooth glide
        f = (t * speed + ph) % 1.0
        f = f * f * (3 - 2 * f)
        p0 = (_hash01(fid, cyc) * 2 - 1, _hash01(fid + 991, cyc) * 2 - 1)
        p1 = (_hash01(fid, cyc + 1) * 2 - 1, _hash01(fid + 991, cyc + 1) * 2 - 1)
        return p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f
    # ballyhoo: two incommensurate sines -> pseudo random sweep
    return math.sin(a + 1.3 * math.sin(0.37 * a)), math.sin(1.7 * a + 0.5)


def intensity_value(kind: str, ph: float, duty: float, fid: int, t: float, speed: float) -> float:
    """0..1 dimmer level of an intensity effect."""
    a = 2 * math.pi * ph
    if kind == "dim_sine":
        return (math.sin(a) + 1) / 2
    if kind == "dim_saw":
        return ph
    if kind == "dim_pulse":
        return 1.0 - ph
    if kind == "dim_triangle":
        return (tri(ph) + 1) / 2
    if kind == "dim_chase":
        return 1.0 if ph < duty else 0.0
    if kind == "dim_fade":
        x = min(1.0, max(0.0, 1.0 - abs(ph - duty / 2) / max(duty, 0.05) * 2 + 0.5))
        return x * x * (3 - 2 * x)
    if kind == "dim_random":
        return 1.0 if _hash01(fid, int(t * speed)) > 0.5 else 0.0
    if kind == "sparkle":
        slot = int(t * speed * 8)
        return 1.0 if _hash01(fid, slot) > 1.0 - duty * 0.3 else 0.0
    if kind == "strobe_random":
        slot = int(t * speed)
        return 1.0 if (_hash01(fid, slot) > 0.6 and ph < duty * 0.3) else 0.0
    # strobe
    return 1.0 if ph < duty * 0.3 else 0.0


def colour_value(eff: Effect, ph: float, fid: int, t: float) -> tuple[int, int, int]:
    if eff.type == "rainbow":
        return tuple(int(x * 255) for x in colorsys.hsv_to_rgb(ph, 1, 1))
    if eff.type == "color_fade":
        k = (tri(ph) + 1) / 2
        return tuple(int(a + (b - a) * k) for a, b in zip(eff.color_a, eff.color_b))
    if eff.type == "rgb_step":
        return RGB_STEPS[int(ph * len(RGB_STEPS)) % len(RGB_STEPS)]
    if eff.type == "color_random":
        return PALETTE[int(_hash01(fid, int(t * eff.speed)) * len(PALETTE)) % len(PALETTE)]
    return tuple(eff.color_a if ph < eff.duty else eff.color_b)


def _set_colour(ft: FixtureType, vals: list[int], rgb, level: float) -> None:
    chans = ft.channels
    attrs = {c.attr for c in chans}
    r, g, b = rgb
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
            vals[i] = 255 if (c.attr == "white" and (r, g, b) == (255, 255, 255)) else 0
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


def _beam(eff: Effect, ft: FixtureType, vals: list[int], ph: float, level: float) -> None:
    moving = ft.is_moving
    a = 2 * math.pi * ph
    target = {"zoom_wave": "zoom", "focus_wave": "focus", "iris_wave": "iris", "frost_wave": "frost",
              "gobo_step": "gobo", "prism_flash": "prism"}[eff.type]
    for i, c in enumerate(ft.channels):
        if c.attr != target:
            continue
        old = vals[i]
        if eff.type == "gobo_step":
            gobos = [(lo + hi) // 2 for lo, hi, lab in c.functions(moving)
                     if lab.lower().startswith("gobo") and any(ch.isdigit() for ch in lab)]
            if not gobos:
                continue
            new = gobos[int(ph * len(gobos)) % len(gobos)]
        elif eff.type == "prism_flash":
            on = [(lo + hi) // 2 for lo, hi, lab in c.functions(moving) if "on" in lab.lower() and "off" not in lab.lower()]
            off = [(lo + hi) // 2 for lo, hi, lab in c.functions(moving) if "off" in lab.lower()]
            new = (on[0] if on else 60) if ph < eff.duty else (off[0] if off else 0)
        else:
            new = eff.low + (eff.high - eff.low) * (math.sin(a) + 1) / 2
        vals[i] = int(max(0, min(255, old + (new - old) * level)))


def apply_effect(eff: Effect, ft: FixtureType, fid: int, vals: list[int], t: float,
                 level: float = 1.0, age: float = 1e9) -> None:
    """``t`` = effect clock, ``level`` = playback fader, ``age`` = seconds since the effect started."""
    if fid not in eff.fixtures:
        return
    if eff.fade > 0:
        level *= min(1.0, max(0.0, age / eff.fade))
    ph = wave(eff, t, fid)
    chans = ft.channels
    if eff.type in POSITION:
        dp, dt = shape_xy(eff.type, ph, fid, t, eff.speed)
        dp, dt = dp * eff.size * level, dt * eff.size * level
        for i, c in enumerate(chans):
            if c.attr == "pan":
                vals[i] = int(max(0, min(255, vals[i] + dp)))
            elif c.attr == "tilt":
                vals[i] = int(max(0, min(255, vals[i] + dt)))
        return
    if eff.type in INTENSITY:
        v = intensity_value(eff.type, ph, eff.duty, fid, t, eff.speed)
        out = eff.low + (eff.high - eff.low) * v
        dims = [i for i, c in enumerate(chans) if c.attr == "dimmer"]
        if level < 1.0:        # fade the effect in from the current value
            base = vals[dims[0]] if dims else 0
            out = base + (out - base) * level
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
        _set_colour(ft, vals, colour_value(eff, ph, fid, t), level)
        return
    if eff.type in BEAM:
        _beam(eff, ft, vals, ph, level)
