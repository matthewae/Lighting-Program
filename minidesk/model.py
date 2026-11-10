"""Show data model: fixture types, patch, groups, playbacks and steps.

The model is deliberately simple (plain dataclasses) and is stored as JSON in
``*.mdshow`` files.  The MINI 1000 ``.SHO`` importer fills the same model.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from .attributes import infer_attribute

SHOW_VERSION = 1


@dataclass
class Channel:
    name: str
    attr: str = "none"
    default: int = 0
    ranges: list = field(default_factory=list)   # [[lo, hi, label], ...] channel functions; [] = generic

    @staticmethod
    def make(name: str, attr: Optional[str] = None, default: Optional[int] = None) -> "Channel":
        a = attr or infer_attribute(name)
        if default is None:
            default = 128 if a in ("pan", "tilt") else 0
        return Channel(name=name, attr=a, default=default)

    def functions(self, moving: bool = True) -> list:
        """Channel functions: explicit ranges or generic ones for the attribute."""
        from .attributes import generic_ranges
        return self.ranges or generic_ranges(self.attr, moving)


@dataclass
class FixtureType:
    name: str
    manufacturer: str = ""
    channels: list[Channel] = field(default_factory=list)
    beam_angle: float = 25.0      # degrees, default beam spread
    pan_range: float = 540.0      # degrees
    tilt_range: float = 270.0     # degrees
    kind: str = "par"             # visual model, see MODEL_KINDS
    lib_index: int = -1           # index in the console fixture library (-1 = not from console)
    model: str = ""               # 3D model: built-in name (see meshes.BUILTIN) or OBJ/GLB/STL file path
    model_scale: float = 1.0      # extra scale for imported models (they are auto-fitted first)

    @property
    def key(self) -> str:
        return f"{self.manufacturer}/{self.name}" if self.manufacturer else self.name

    @property
    def is_moving(self) -> bool:
        return any(c.attr in ("pan", "tilt") for c in self.channels)

    @property
    def model_label(self) -> str:
        return MODEL_KINDS.get(self.kind, self.kind)

    def find(self, attr: str) -> list[int]:
        return [i for i, c in enumerate(self.channels) if c.attr == attr]

    def guess_kind(self) -> None:
        n = (self.name + " " + self.manufacturer).lower()
        attrs = {c.attr for c in self.channels}
        if attrs & {"fog"} or "haze" in n or "fog" in n or "df-" in n:
            self.kind, self.beam_angle = "fog", 60
        elif self.is_moving:
            if "beam" in n or "bsw" in n or "280" in n or "230" in n:
                self.kind, self.beam_angle = "beam", 4
            elif "wash" in n:
                self.kind, self.beam_angle = "wash", 25
            else:
                self.kind, self.beam_angle = "spot", 15
        elif "blinder" in n:
            self.kind, self.beam_angle = "blinder", 70
        elif "bar" in n:
            self.kind, self.beam_angle = "ledbar", 30
        elif "strob" in n:
            self.kind, self.beam_angle = "strobe", 100
        elif "fresnel" in n or "fresnell" in n:
            self.kind, self.beam_angle = "fresnel", 40
        elif attrs & {"red", "green", "blue"}:
            self.kind, self.beam_angle = "par", 25
        else:
            self.kind, self.beam_angle = "generic", 30
        # 3D model (only the look – channels / addresses come from the profile)
        if self.kind == "fog":
            self.model = "fog_vertical" if (" vs" in f" {n}" or "vs " in n or "vertical" in n or "1500vs" in n) \
                else ("hazer" if "haz" in n else "fog")
        elif self.is_moving:
            from .meshes import bundled_defaults
            self.model = bundled_defaults().get("moving") or ("hybrid" if ("bsw" in n or "hybrid" in n) else self.kind)
        else:
            self.model = self.kind if self.kind != "generic" else "par" if attrs & {"red", "green", "blue"} else "generic"
        # moving heads should start with an open shutter
        if self.is_moving:
            for c in self.channels:
                if c.attr == "shutter" and c.default == 0:
                    c.default = 255


# Visual models a fixture type can be drawn as.
MODEL_KINDS = {
    "beam": "Moving head – Beam",
    "spot": "Moving head – Spot",
    "wash": "Moving head – Wash",
    "par": "LED PAR",
    "fresnel": "Fresnel / Profile",
    "strobe": "Strobe",
    "ledbar": "LED bar",
    "blinder": "Blinder",
    "fog": "Fog / Hazer",
    "generic": "Generic",
}
MOVING_KINDS = {"beam", "spot", "wash"}


@dataclass
class Fixture:
    fid: int                      # fixture number (1 based, shown to the user)
    name: str
    type_key: str
    universe: int = 0             # 0 based universe
    address: int = 0              # 1..512, 0 = not patched
    x: float = 0.0                # metres, stage left/right (0 = centre)
    y: float = 4.0                # metres, depth (0 = downstage edge)
    z: float = 5.0                # metres, height
    mount: str = "hang"           # hang | floor
    rot: float = 0.0              # yaw in degrees (0 = facing the audience / downstage)
    aim: float = 30.0             # fixed fixtures: tilt from straight down/up toward 'rot'
    slot: int = -1                # fixture index in the console file (-1 = new)
    invert_pan: bool = False      # patch options (like the console's pan/tilt invert & swap)
    invert_tilt: bool = False
    swap_pan_tilt: bool = False

    @property
    def patched(self) -> bool:
        return self.address > 0


@dataclass
class Group:
    name: str
    fixtures: list[int] = field(default_factory=list)   # fixture ids
    slot: int = -1                                       # group slot in the console file


EFFECT_TYPES = {
    # key: (label, feature)  – keys stay stable because they are stored in shows
    # Position (pan / tilt shapes)
    "circle": ("Circle", "Position"),
    "ellipse": ("Ellipse", "Position"),
    "diamond": ("Diamond", "Position"),
    "square": ("Square", "Position"),
    "triangle": ("Triangle", "Position"),
    "figure8": ("Figure 8", "Position"),
    "s_shape": ("S shape", "Position"),
    "cross": ("Cross", "Position"),
    "star": ("Star", "Position"),
    "spiral": ("Spiral", "Position"),
    "pan_saw": ("Pan saw", "Position"),
    "tilt_saw": ("Tilt saw", "Position"),
    "pan_wave": ("Pan sine", "Position"),
    "tilt_wave": ("Tilt sine", "Position"),
    "pan_swing": ("Pan swing (triangle)", "Position"),
    "tilt_swing": ("Tilt swing (triangle)", "Position"),
    "pan_step": ("Pan step", "Position"),
    "tilt_step": ("Tilt step", "Position"),
    "ballyhoo": ("Ballyhoo", "Position"),
    "pos_random": ("Random position", "Position"),
    "infinity": ("Infinity ∞", "Position"),
    "heart": ("Heart", "Position"),
    "rose": ("Flower (4 petals)", "Position"),
    "lissajous": ("Lissajous 3:2", "Position"),
    "zigzag": ("Zig-zag", "Position"),
    "fan": ("Fan in / out", "Position"),
    "pendulum": ("Pendulum", "Position"),
    "nod": ("Tilt nod", "Position"),
    "sweep": ("Sweep (pan + tilt drop)", "Position"),
    "jump": ("Random jump", "Position"),
    # Intensity (dimmer)
    "dim_sine": ("Dimmer sine", "Intensity"),
    "dim_saw": ("Dimmer saw (ramp up)", "Intensity"),
    "dim_pulse": ("Dimmer ramp down", "Intensity"),
    "dim_triangle": ("Dimmer triangle", "Intensity"),
    "dim_chase": ("Dimmer chase / step", "Intensity"),
    "dim_fade": ("Dimmer soft chase", "Intensity"),
    "dim_random": ("Dimmer random", "Intensity"),
    "sparkle": ("Sparkle", "Intensity"),
    "strobe": ("Strobe", "Intensity"),
    "strobe_random": ("Random strobe", "Intensity"),
    "breathe": ("Breathe", "Intensity"),
    "heartbeat": ("Heartbeat", "Intensity"),
    "flash_decay": ("Flash + decay", "Intensity"),
    "bounce": ("Bounce chase", "Intensity"),
    "scanner": ("Scanner (knight rider)", "Intensity"),
    "build": ("Build up", "Intensity"),
    "lightning": ("Lightning", "Intensity"),
    "flicker": ("Fire flicker", "Intensity"),
    "candle": ("Candle", "Intensity"),
    "odd_even": ("Odd / even", "Intensity"),
    # Colour
    "rainbow": ("Rainbow", "Color"),
    "color_chase": ("Colour chase A/B", "Color"),
    "color_fade": ("Colour fade A↔B", "Color"),
    "rgb_step": ("RGB step (R-G-B-W)", "Color"),
    "color_random": ("Random colour", "Color"),
    "color_wave": ("Colour wave (hue spread)", "Color"),
    "color3": ("3-colour chase", "Color"),
    "fire": ("Fire", "Color"),
    "ocean": ("Ocean", "Color"),
    "police": ("Police", "Color"),
    "pastel": ("Pastel rainbow", "Color"),
    "color_strobe": ("Colour flash", "Color"),
    # Beam
    "gobo_step": ("Gobo step", "Beam"),
    "zoom_wave": ("Zoom wave", "Beam"),
    "focus_wave": ("Focus wave", "Beam"),
    "iris_wave": ("Iris wave", "Beam"),
    "prism_flash": ("Prism on/off", "Beam"),
    "frost_wave": ("Frost wave", "Beam"),
    "zoom_bump": ("Zoom bump", "Beam"),
    "iris_pulse": ("Iris pulse", "Beam"),
    "gobo_shake": ("Gobo shake", "Beam"),
    "prism_spin": ("Prism spin", "Beam"),
}


@dataclass
class Effect:
    type: str = "circle"
    fixtures: list[int] = field(default_factory=list)
    speed: float = 0.5            # cycles per second
    size: float = 40.0            # position: DMX amplitude, intensity: depth % (0..100)
    spread: float = 360.0         # phase spread across fixtures (degrees)
    wings: int = 1                # mirror groups
    low: int = 0                  # intensity low value (0..255)
    high: int = 255               # intensity high value (0..255)
    color_a: tuple = (255, 0, 0)
    color_b: tuple = (0, 0, 255)
    reverse: bool = False
    offset: float = 0.0           # phase offset of the whole effect (degrees)
    duty: float = 0.5             # on-time fraction for chase / strobe (0..1)
    fade: float = 0.0             # seconds to ramp the effect in when it starts
    order: str = "forward"        # forward | backward | center_out | outside_in | odd_even | random
    blocks: int = 1               # fixtures that move together
    color_c: tuple = (0, 255, 0)  # third colour (3-colour chase)

    def to_json(self) -> dict:
        d = asdict(self)
        d["color_a"], d["color_b"], d["color_c"] = list(self.color_a), list(self.color_b), list(self.color_c)
        return d

    @staticmethod
    def from_json(d: dict) -> "Effect":
        d = dict(d)
        d["color_a"] = tuple(d.get("color_a", (255, 0, 0)))
        d["color_b"] = tuple(d.get("color_b", (0, 0, 255)))
        d["color_c"] = tuple(d.get("color_c", (0, 255, 0)))
        return Effect(**{k: v for k, v in d.items() if k in Effect.__dataclass_fields__})


@dataclass
class Step:
    name: str = ""
    values: dict[int, dict[int, int]] = field(default_factory=dict)   # fid -> {chan: value}
    fade: float = 0.0          # fade in (seconds)
    hold: float = -1.0         # seconds, -1 = use playback speed
    effects: list[Effect] = field(default_factory=list)
    fade_out: float = -1.0     # fade out for intensity going down, -1 = same as fade
    delay: float = 0.0         # delay before the fade in starts
    delay_out: float = -1.0    # delay before the fade out starts, -1 = same as delay
    follow: bool = False       # cuelist: go to the next cue automatically after fade + hold

    def to_json(self) -> dict:
        return {
            "name": self.name, "fade": self.fade, "hold": self.hold,
            "fade_out": self.fade_out, "delay": self.delay, "delay_out": self.delay_out,
            "follow": self.follow,
            "values": {str(f): {str(c): v for c, v in ch.items()} for f, ch in self.values.items()},
            "effects": [e.to_json() for e in self.effects],
        }

    @staticmethod
    def from_json(d: dict) -> "Step":
        return Step(
            name=d.get("name", ""), fade=float(d.get("fade", 0)), hold=float(d.get("hold", -1)),
            fade_out=float(d.get("fade_out", -1)), delay=float(d.get("delay", 0)),
            delay_out=float(d.get("delay_out", -1)), follow=bool(d.get("follow", False)),
            values={int(f): {int(c): int(v) for c, v in ch.items()} for f, ch in d.get("values", {}).items()},
            effects=[Effect.from_json(e) for e in d.get("effects", [])],
        )


PB_DIRECTIONS = ["forward", "backward", "bounce", "random"]


@dataclass
class Playback:
    name: str
    steps: list[Step] = field(default_factory=list)
    mode: str = "chase"        # chase | cuelist
    speed: float = 1.0         # seconds per step in chase mode (when step.hold < 0)
    fade: float = 0.0          # default crossfade (seconds) when step.fade == 0 in chase mode
    number: int = 0            # executor number
    bank: str = "Playback"     # label of origin (Fixed / Playback / User)
    source: str = ""           # info about where it was imported from
    slot: int = -1             # record index in the console file (-1 = not from console)
    direction: str = "forward" # forward | backward | bounce | random
    loop: bool = True          # chase/cuelist wraps around at the end (False = stop/hold at the end)
    xfade: float = 0.0         # chase crossfade as % of the step time (0 = use fade times)
    release: float = 0.0       # fade out time when the playback is stopped (seconds)

    def to_json(self) -> dict:
        return {
            "name": self.name, "mode": self.mode, "speed": self.speed, "fade": self.fade,
            "number": self.number, "bank": self.bank, "source": self.source, "slot": self.slot,
            "direction": self.direction, "loop": self.loop, "xfade": self.xfade, "release": self.release,
            "steps": [s.to_json() for s in self.steps],
        }

    @staticmethod
    def from_json(d: dict) -> "Playback":
        return Playback(
            name=d["name"], mode=d.get("mode", "chase"), speed=float(d.get("speed", 1)),
            fade=float(d.get("fade", 0)), number=int(d.get("number", 0)),
            bank=d.get("bank", "Playback"), source=d.get("source", ""), slot=int(d.get("slot", -1)),
            direction=d.get("direction", "forward"), loop=bool(d.get("loop", True)),
            xfade=float(d.get("xfade", 0)), release=float(d.get("release", 0)),
            steps=[Step.from_json(s) for s in d.get("steps", [])],
        )


PRESET_CATEGORIES = ["Intensity", "Position", "Color", "Beam", "All"]


@dataclass
class Preset:
    name: str
    category: str = "All"
    values: dict[int, dict[int, int]] = field(default_factory=dict)   # fid -> {chan: value}
    slot: int = -1             # preset record in the console file
    source: str = ""

    def to_json(self) -> dict:
        return {"name": self.name, "category": self.category, "slot": self.slot, "source": self.source,
                "values": {str(f): {str(c): v for c, v in ch.items()} for f, ch in self.values.items()}}

    @staticmethod
    def from_json(d: dict) -> "Preset":
        return Preset(name=d["name"], category=d.get("category", "All"), slot=int(d.get("slot", -1)),
                      source=d.get("source", ""),
                      values={int(f): {int(c): int(v) for c, v in ch.items()}
                              for f, ch in d.get("values", {}).items()})


@dataclass
class OutputConfig:
    artnet_enabled: bool = False
    artnet_target: str = "255.255.255.255"
    artnet_universe_offset: int = 0
    sacn_enabled: bool = False
    sacn_universe_offset: int = 1
    enttec_enabled: bool = False
    enttec_port: str = ""
    input_mode: str = "none"        # none | artnet | enttec
    input_universe: int = 0          # Art-Net universe to listen to
    input_bind: str = "0.0.0.0"
    input_enttec_port: str = ""
    input_merge: str = "replace"     # replace | htp
    opendmx_enabled: bool = False    # FTDI "Open DMX" style USB cable (output only)
    opendmx_port: str = ""
    midi_in: str = ""                # MIDI input device name
    midi_out: str = ""               # MIDI output device name
    midi_map: list = field(default_factory=list)   # [{"kind","ch","num","action","target"}]
    midi_feedback: bool = True       # send MIDI notes when executors are triggered
    auto_reconnect: bool = True      # re-open USB devices when they are plugged in again


@dataclass
class Show:
    name: str = "Untitled"
    types: dict[str, FixtureType] = field(default_factory=dict)
    fixtures: list[Fixture] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    playbacks: list[Playback] = field(default_factory=list)
    presets: list[Preset] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)
    stage_width: float = 12.0
    stage_depth: float = 8.0
    stage_height: float = 6.0
    console_info: dict = field(default_factory=dict)
    source_path: str = ""          # console .SHO file this show was imported from
    truss_model: str = ""          # "" = default (bundled user truss if present), "builtin", or a file

    # ---------------------------------------------------------------- lookup
    def fixture(self, fid: int) -> Optional[Fixture]:
        for f in self.fixtures:
            if f.fid == fid:
                return f
        return None

    def ftype(self, fx: Fixture) -> FixtureType:
        return self.types[fx.type_key]

    def next_fid(self) -> int:
        return max((f.fid for f in self.fixtures), default=0) + 1

    def universes(self) -> list[int]:
        u = sorted({f.universe for f in self.fixtures if f.patched})
        return u or [0]

    def add_type(self, ft: FixtureType) -> FixtureType:
        self.types[ft.key] = ft
        return ft

    def patch_conflicts(self) -> list[tuple[int, int]]:
        used: dict[tuple[int, int], int] = {}
        conflicts = []
        for f in self.fixtures:
            if not f.patched:
                continue
            for i in range(len(self.ftype(f).channels)):
                k = (f.universe, f.address + i)
                if k in used:
                    conflicts.append((used[k], f.fid))
                used[k] = f.fid
        return conflicts

    # ------------------------------------------------------------------ JSON
    def to_json(self) -> dict:
        return {
            "version": SHOW_VERSION,
            "name": self.name,
            "stage": [self.stage_width, self.stage_depth, self.stage_height],
            "types": [asdict(t) for t in self.types.values()],
            "fixtures": [asdict(f) for f in self.fixtures],
            "groups": [asdict(g) for g in self.groups],
            "playbacks": [p.to_json() for p in self.playbacks],
            "presets": [p.to_json() for p in self.presets],
            "output": asdict(self.output),
            "console_info": self.console_info,
            "source_path": self.source_path,
            "truss_model": self.truss_model,
        }

    @staticmethod
    def from_json(d: dict) -> "Show":
        s = Show(name=d.get("name", "Untitled"))
        st = d.get("stage")
        if st:
            s.stage_width, s.stage_depth, s.stage_height = st
        for t in d.get("types", []):
            chans = [Channel(**c) for c in t.pop("channels", [])]
            ft = FixtureType(channels=chans, **t)
            s.types[ft.key] = ft
        s.fixtures = [Fixture(**f) for f in d.get("fixtures", [])]
        s.groups = [Group(**g) for g in d.get("groups", [])]
        s.playbacks = [Playback.from_json(p) for p in d.get("playbacks", [])]
        s.presets = [Preset.from_json(p) for p in d.get("presets", [])]
        if "output" in d:
            s.output = OutputConfig(**{k: v for k, v in d["output"].items()
                                       if k in OutputConfig.__dataclass_fields__})
        s.console_info = d.get("console_info", {})
        s.source_path = d.get("source_path", "")
        s.truss_model = d.get("truss_model", "")
        return s

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_json(), fh, indent=1)

    @staticmethod
    def load(path: str) -> "Show":
        with open(path, encoding="utf-8") as fh:
            return Show.from_json(json.load(fh))


# --------------------------------------------------------------------------
# A few generic fixture types so the app is usable without a console file.
def builtin_types() -> list[FixtureType]:
    def ft(name, chans, **kw):
        t = FixtureType(name=name, manufacturer="Generic",
                        channels=[Channel.make(c) for c in chans], **kw)
        t.guess_kind()
        return t

    return [
        ft("Dimmer", ["Dimmer"]),
        ft("RGB", ["Red", "Green", "Blue"]),
        ft("RGBW PAR 8ch", ["Dimmer", "Red", "Green", "Blue", "White", "Strobe", "Macro", "Speed"]),
        ft("RGBWAUV PAR", ["Dimmer", "Red", "Green", "Blue", "White", "Amber", "UV", "Strobe"]),
        ft("Moving Head Spot 16ch", ["Pan", "Pan Fine", "Tilt", "Tilt Fine", "P/T Speed", "Dimmer",
                                     "Shutter", "Color", "Gobo", "Gobo Rot", "Prism", "Prism Rot",
                                     "Focus", "Zoom", "Frost", "Control"]),
        ft("Beam 230 16ch", ["Color", "Strobe", "Dimmer", "Gobo", "Prism", "Prism Rot", "Prism 2",
                             "Frost", "Focus", "Pan", "Pan Fine", "Tilt", "Tilt Fine", "P/T Speed",
                             "Reset", "Lamp"]),
        ft("Hazer", ["Fog", "Fan"]),
    ]
