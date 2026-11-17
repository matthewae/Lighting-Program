"""Effect library of the CODE MINI 1000T (Effect Select screen).

The four categories and their numbering are copied from the console screens:
Intensity 1-28, Position 1-107, Color 1-67, Beam 1-31.  Each entry is turned into
an :class:`Effect` using the console naming scheme:

* ``<name>``           all fixtures together (parallel)
* ``Spread``           phase spread over all fixtures
* ``O/E``, ``Odd/Even`` odd and even fixtures opposite (180 degrees)
* ``G3 .. G12``        fixtures in groups of N (phase step 360/N, shown as Effect Spread)
* ``S``                symmetric (mirrored from the centre)
* ``Parallel``         all together
* ``Swap``             snap between two states, ``Step`` stepping, ``a:b`` on:off ratio chase

Numbered variants whose exact console behaviour is not documented (``Dimmer 1``,
``Swap3`` ...) map to: 1 = spread, 2 = odd/even, 3 = groups of 3, 4 = groups of 4.
"""
from __future__ import annotations

import re

from .model import Effect

CATEGORIES = ["Intensity", "Position", "Color", "Beam"]

INTENSITY = [
    "Dimmer", "Dimmer 1", "Dimmer 2", "Dimmer 3", "Dimmer 4",
    "DimLinear", "DimLinear1", "DimLinear2", "DimLinear3", "DimLinear4",
    "DimmerPWM", "DimmerPWM1", "DimmerPWM2", "DimmerPWM3", "Dimmer1:1",
    "Dimmer1:2", "Dimmer1:3", "Dimmer1:4", "Dimmer1:9", "Dimmer2:1",
    "Dimmer3:1", "DimmSlow1:1", "DimmSlow1:2", "DimmSlow2:1", "DimmerStep",
    "Dimmer Chase", "DimSymmetry1", "DimSymmetry2",
]

POSITION = [
    "Circle", "Circle Spread", "Circle Odd/Even", "Circle G3", "Circle G4",
    "Circle G5", "Circle G6", "Circle G8", "Circle G9", "Circle G12",
    "Tilt Parallel", "Tilt Spread", "Tilt Odd/Even", "TiltSwingG3", "TiltSwingG4",
    "TiltSwingG5", "TiltSwingG6", "TiltSwing S", "TiltSwingG8", "TiltSwingG9",
    "TiltSAW Parall", "TiltSAW O/E", "TiltSAW G3", "TiltSAW G4", "TiltSAW G5",
    "TiltSAW G6", "TiltSAW G8", "TiltSAW G12", "TiltSAW S", "Pan Swing",
    "PanSwingO/E", "PanSwing G3", "PanSwing G4", "PanSwing G6", "PanSwing G8",
    "PanSwing G9", "PanSwingG12", "Pan SAW", "PanSAW O/E", "Pan SAW G3",
    "Pan SAW G4", "Pan SAW G6", "Pan SAW G8", "Square", "SquareSpread",
    "Square O/E", "Square G3", "Square G4", "Square G5", "Square G6",
    "Square G8", "Square G12", "Diamond", "DiamondSpread", "Diamond O/E",
    "Diamond G3", "Diamond G4", "Diamond G5", "Diamond G6", "Diamond G8",
    "Spiral", "SpiralSpread", "Spiral O/E", "SpiralSpread1", "SpiralSpread2",
    "Triangle", "TriangleSpread", "Triangle O/E", "Triangle G3", "Triangle G4",
    "Triangle G5", "Triangle G6", "Triangle G9", "Zigzag Up", "ZigzagUp Spread",
    "ZigzagUp O/E", "ZigzagUp G3", "ZigzagUp G4", "ZigzagUp G5", "ZigzagUp G6",
    "ZigzagUp G8", "ZigzagUp G9", "Zigzag Down", "Z DownSpread", "Z Down O/E",
    "Z Down G3", "Z Down G4", "Z Down G5", "Z Down G6", "Z Down G8",
    "Z Down G9", "Random", "Random1", "Random2", "Random3",
    "Pan Swap1", "Pan Swap2", "Pan Swap3", "Pan Swap4", "Tilt Swap1",
    "Tilt Swap2", "Tilt Swap3", "Tilt Swap4", "XY Swap1", "XY Swap2",
    "XY Swap3", "XY Swap4",
]

COLOR = [
    "Rainbow", "RainbowSpread", "RainbowSpread1", "RainbowSpread2", "Rainbow 1",
    "Rainbow 2", "Red", "RedSpread", "RedOdd/Even", "Red 1",
    "Green", "GreenSpread", "GreenO/E", "Green 1", "Blue",
    "BlueSpread", "BlueO/E", "Blue 1", "Color1Effect", "Color1Spread",
    "Color1Spread1", "Color1Spread2", "Color1Spread3", "Color1Step1", "Color1Step2",
    "Color1Step3", "Color1 2-1", "Color1 2-2", "Color1 2-3", "Color2Effect",
    "Color2Spread", "Color2 S1", "Color2 S2", "Color2 S3", "Color2Step1",
    "Color2Step2", "Color2Step3", "Color2 2-1", "Color2 2-2", "Color2 2-3",
    "RainbowStep", "RainbowStep1", "RainbowStep2", "RainbowStep3", "Red Step",
    "Green Step", "Blue Step", "Color1 Swap1", "Color1 Swap2", "Color1 Swap3",
    "Color1 Swap4", "Color2 Swap1", "Color2 Swap2", "Color2 Swap3", "Color2 Swap4",
    "Red Swap1", "Red Swap2", "Red Swap3", "GreenSwap1", "GreenSwap2",
    "GreenSwap3", "BlueSwap1", "BlueSwap2", "BlueSwap3", "RainbowSwap1",
    "RainbowSwap2", "RainbowSwap3",
]

BEAM = [
    "Iris", "Iris Spread", "Iris 1", "Iris 2", "Gobo",
    "Gobo Spread", "Gobo Spread1", "Gobo Spread2", "Iris Step1", "Iris Step2",
    "Gobo Step1", "Gobo Step2", "FocusEffect", "FocusLinear", "FocusStep",
    "PrismEffect", "PrismSpread", "PrismStep", "FocusSwap1", "FocusSwap2",
    "FocusSwap3", "FocusSwap4", "PrismSwap1", "PrismSwap2", "PrismSwap3",
    "PrismSwap4", "FrostEffect", "FrostSpread", "FrostStep", "FrostSwap1",
    "FrostSwap2",
]

LIBRARY = {"Intensity": INTENSITY, "Position": POSITION, "Color": COLOR, "Beam": BEAM}
LETTER = {"Intensity": "I", "Position": "P", "Color": "C", "Beam": "B"}
DEFAULT_BPM = {"Intensity": 30.0, "Position": 15.0, "Color": 20.0, "Beam": 20.0}
DEFAULT_SIZE = {"Intensity": 100.0, "Position": 40.0, "Color": 100.0, "Beam": 100.0}
COLOURS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255)}
ORDERS = {"forward": "Forward", "backward": "Backward", "center_out": "Centre → out",
          "outside_in": "Outside → in", "random": "Random"}


def entries(category: str) -> list[tuple[int, str]]:
    """[(console number, name)] of a category; 'All' = every category."""
    if category == "All":
        out = []
        for c in CATEGORIES:
            out += [(n, f"{name}") for n, name in entries(c)]
        return out
    return [(i + 1, name) for i, name in enumerate(LIBRARY[category])]


def all_entries() -> list[tuple[str, int, str]]:
    return [(c, i + 1, n) for c in CATEGORIES for i, n in enumerate(LIBRARY[c])]


# ----------------------------------------------------------------- phasing
def _phase(token: str) -> dict:
    """Effect phasing keywords from the console name suffix."""
    t = token.lower().replace(" ", "")
    if t in ("", "parallel", "parall", "effect"):
        return {"phase_step": 0.0}
    m = re.fullmatch(r"g(\d+)", t)
    if m:
        n = int(m.group(1))
        return {"groups": n, "phase_step": 360.0 / n}
    if t in ("o/e", "oddeven", "odd/even", "oe"):
        return {"groups": 2, "phase_step": 180.0}
    if t == "s":
        return {"wings": 2, "spread": 360.0, "phase_step": -1.0}
    if t == "spread":
        return {"spread": 360.0, "phase_step": -1.0}
    m = re.fullmatch(r"(?:spread|s)(\d)", t)
    if m:                       # Spread1 / Spread2 / S1..S3: groups of 3, 4, 5
        n = int(m.group(1)) + 2
        return {"groups": n, "phase_step": 360.0 / n}
    m = re.fullmatch(r"(\d)", t)
    if m:
        return _variant(int(m.group(1)))
    return {"phase_step": 0.0}


def _variant(k: int) -> dict:
    return {1: {"spread": 360.0, "phase_step": -1.0},
            2: {"groups": 2, "phase_step": 180.0},
            3: {"groups": 3, "phase_step": 120.0},
            4: {"groups": 4, "phase_step": 90.0}}.get(k, {"phase_step": 0.0})


# ------------------------------------------------------------------ parse
_POS_BASES = [("circle", "circle"), ("tiltswing", "tilt_wave"), ("tiltsaw", "tilt_saw"),
              ("tiltswap", "tilt_step"), ("tilt", "tilt_wave"), ("panswing", "pan_wave"),
              ("pansaw", "pan_saw"), ("panswap", "pan_step"), ("xyswap", "xy_step"),
              ("square", "square"), ("diamond", "diamond"), ("spiral", "spiral"),
              ("triangle", "triangle"), ("zigzagup", "zigzag_up"), ("zigzagdown", "zigzag_down"),
              ("zdown", "zigzag_down"), ("random", "pos_random")]


def _position(n: str) -> dict:
    for base, typ in _POS_BASES:
        if n.startswith(base):
            rest = n[len(base):]
            if typ == "pos_random":
                return {"type": {"": "pos_random", "1": "jump", "2": "ballyhoo", "3": "pos_random"}.get(rest, "pos_random"),
                        "phase_step": 0.0 if rest == "3" else -1.0, "spread": 360.0}
            kw = {"type": typ}
            kw.update(_phase(rest))
            return kw
    return {"type": "circle", "phase_step": 0.0}


def _intensity(n: str) -> dict:
    m = re.fullmatch(r"(dimmslow|dimmer)(\d):(\d)", n)
    if m:
        a, b = int(m.group(2)), int(m.group(3))
        return {"type": "dim_soft" if m.group(1) == "dimmslow" else "dim_chase", "duty": a / (a + b),
                "groups": a + b, "phase_step": 360.0 / (a + b)}
    m = re.fullmatch(r"dimmerpwm(\d?)", n)
    if m:
        k = m.group(1)
        kw = {"type": "dim_chase", "duty": 0.5}
        kw.update({"": {"phase_step": 0.0}, "1": {"spread": 360.0, "phase_step": -1.0},
                   "2": {"phase_step": 30.0}, "3": {"groups": 2, "phase_step": 180.0}}[k])
        return kw
    m = re.fullmatch(r"dimlinear(\d?)", n)
    if m:
        return {"type": "dim_triangle", **_phase(m.group(1))}
    if n == "dimmerstep":
        return {"type": "dim_step", "spread": 360.0, "phase_step": -1.0}
    if n == "dimmerchase":
        return {"type": "dim_fade", "duty": 0.3, "spread": 360.0, "phase_step": -1.0}
    if n.startswith("dimsymmetry"):
        return {"type": "dim_fade", "duty": 0.35, "spread": 360.0, "phase_step": -1.0,
                "order": "center_out" if n.endswith("1") else "outside_in"}
    m = re.fullmatch(r"dimmer(\d?)", n)
    if m:
        return {"type": "dim_sine", **_phase(m.group(1))}
    return {"type": "dim_sine", "phase_step": 0.0}


def _colour(n: str) -> dict:
    m = re.fullmatch(r"rainbow(step|swap|spread)?(\d?)", n)
    if m:
        kind, k = m.group(1) or "", m.group(2)
        typ = {"step": "rainbow_step", "swap": "rainbow_swap"}.get(kind, "rainbow")
        if kind == "spread":
            ph = _phase("spread" + k) if k else _phase("spread")
        elif kind == "":
            ph = {"": {"phase_step": 0.0}, "1": _variant(2), "2": _variant(3)}.get(k, {"phase_step": 0.0})
        else:
            ph = _variant(int(k)) if k else {"phase_step": 0.0}
        return {"type": typ, **ph}
    m = re.fullmatch(r"(red|green|blue)(.*)", n)
    if m:
        col, rest = COLOURS[m.group(1)], m.group(2)
        kw = {"color_a": col, "color_b": (0, 0, 0)}
        if rest == "step":
            return {"type": "color_chase", "duty": 0.5, "spread": 360.0, "phase_step": -1.0, **kw}
        ms = re.fullmatch(r"swap(\d)", rest)
        if ms:
            ph = {1: _variant(2), 2: _variant(3), 3: _variant(1)}[int(ms.group(1))]
            return {"type": "color_chase", "duty": 0.5, **ph, **kw}
        if rest == "1":
            return {"type": "color_fade", **_variant(3), **kw}
        return {"type": "color_fade", **_phase(rest), **kw}
    m = re.fullmatch(r"color([12])(.*)", n)
    if m:
        attr = "color" if m.group(1) == "1" else "color2"
        rest = m.group(2)
        kw = {"type": "wheel_fx", "attribute": attr}
        if rest == "effect":
            return {**kw, "wave": "scroll", "phase_step": 0.0}
        if rest.startswith("spread") or re.fullmatch(r"s\d", rest):
            return {**kw, "wave": "step", **_phase(rest)}
        ms = re.fullmatch(r"step(\d)", rest)
        if ms:
            return {**kw, "wave": "step", **_variant(int(ms.group(1)))}
        ms = re.fullmatch(r"2-(\d)", rest)
        if ms:
            return {**kw, "wave": "swap", **{1: {"phase_step": 0.0}, 2: _variant(2), 3: _variant(3)}[int(ms.group(1))]}
        ms = re.fullmatch(r"swap(\d)", rest)
        if ms:
            return {**kw, "wave": "swap", **_variant(int(ms.group(1)))}
        return {**kw, "wave": "step", "phase_step": 0.0}
    return {"type": "rainbow", "phase_step": 0.0}


def _beam(n: str) -> dict:
    m = re.fullmatch(r"(iris|gobo|focus|prism|frost)(.*)", n)
    if not m:
        return {"type": "beam_fx", "attribute": "iris", "phase_step": 0.0}
    attr, rest = m.group(1), m.group(2)
    kw = {"type": "beam_fx", "attribute": attr}
    default_wave = {"gobo": "step", "prism": "swap"}.get(attr, "sine")
    if rest in ("", "effect"):
        return {**kw, "wave": default_wave, "phase_step": 0.0}
    if rest == "linear":
        return {**kw, "wave": "linear", "phase_step": 0.0}
    if rest.startswith("spread"):
        return {**kw, "wave": default_wave, **_phase(rest)}
    ms = re.fullmatch(r"(step|swap)(\d?)", rest)
    if ms:
        wave = "step" if ms.group(1) == "step" else "swap"
        ph = _variant(int(ms.group(2))) if ms.group(2) else {"spread": 360.0, "phase_step": -1.0}
        return {**kw, "wave": wave, **ph}
    if rest.isdigit():
        return {**kw, "wave": default_wave, **_variant(int(rest) + 1)}
    return {**kw, "wave": default_wave, "phase_step": 0.0}


def spec(category: str, name: str) -> dict:
    n = name.lower().replace(" ", "")
    return {"Intensity": _intensity, "Position": _position, "Color": _colour, "Beam": _beam}[category](n)


# ------------------------------------------------------------- make / units
def make(category: str, number: int, fixtures: list[int], bpm: float | None = None,
         size_pct: float | None = None) -> Effect:
    """Effect for console library entry ``category number`` on ``fixtures``."""
    name = LIBRARY[category][number - 1]
    kw = spec(category, name)
    eff = Effect(fixtures=list(fixtures))
    for k, v in kw.items():
        setattr(eff, k, v)
    eff.console = f"{category} {number}"
    eff.label = name
    eff.mode = "rel" if category == "Position" else "abs"
    set_bpm(eff, DEFAULT_BPM[category] if bpm is None else bpm)
    set_size_pct(eff, DEFAULT_SIZE[category] if size_pct is None else size_pct)
    return eff


def category_of(eff: Effect) -> str:
    if eff.console:
        return eff.console.split()[0]
    from .model import EFFECT_TYPES
    return EFFECT_TYPES.get(eff.type, ("", "Position"))[1]


def letter(eff: Effect) -> str:
    return LETTER.get(category_of(eff), "?")


def bpm(eff: Effect) -> float:
    return eff.speed * 60.0


def set_bpm(eff: Effect, value: float) -> None:
    eff.speed = max(0.1, float(value)) / 60.0


def size_pct(eff: Effect) -> float:
    cat = category_of(eff)
    if cat == "Position":
        return eff.size / 1.28
    if cat == "Intensity":
        return (eff.high - eff.low) / 2.55
    return 100.0 * (eff.high - eff.low) / 255.0


def set_size_pct(eff: Effect, pct: float) -> None:
    pct = max(0.0, min(100.0, float(pct)))
    cat = category_of(eff)
    if cat == "Position":
        eff.size = pct * 1.28                      # 100 % = +-128 DMX = the full pan / tilt range
    else:
        eff.high = 255
        eff.low = int(round(255 - 2.55 * pct))


def spread_deg(eff: Effect) -> float:
    """Console 'Effect Spread': degrees between consecutive fixtures (or groups)."""
    if eff.phase_step >= 0:
        return eff.phase_step
    n = max(1, len(eff.fixtures) // max(1, eff.wings))
    return eff.spread / n


def set_spread_deg(eff: Effect, deg: float) -> None:
    eff.phase_step = max(0.0, min(360.0, float(deg)))
