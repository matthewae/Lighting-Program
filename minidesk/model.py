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

    @staticmethod
    def make(name: str, attr: Optional[str] = None, default: Optional[int] = None) -> "Channel":
        a = attr or infer_attribute(name)
        if default is None:
            default = 128 if a in ("pan", "tilt") else 0
        return Channel(name=name, attr=a, default=default)


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

    @property
    def patched(self) -> bool:
        return self.address > 0


@dataclass
class Group:
    name: str
    fixtures: list[int] = field(default_factory=list)   # fixture ids
    slot: int = -1                                       # group slot in the console file


EFFECT_TYPES = {
    # key: (label, feature)
    "circle": ("Circle", "Position"),
    "figure8": ("Figure 8", "Position"),
    "pan_wave": ("Pan wave", "Position"),
    "tilt_wave": ("Tilt wave", "Position"),
    "ballyhoo": ("Ballyhoo (random sweep)", "Position"),
    "dim_sine": ("Dimmer sine", "Intensity"),
    "dim_pulse": ("Dimmer pulse / ramp", "Intensity"),
    "dim_chase": ("Dimmer chase (on/off)", "Intensity"),
    "dim_random": ("Dimmer random", "Intensity"),
    "strobe": ("Strobe flash", "Intensity"),
    "rainbow": ("Rainbow", "Color"),
    "color_chase": ("Color chase (2 colours)", "Color"),
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

    def to_json(self) -> dict:
        d = asdict(self)
        d["color_a"], d["color_b"] = list(self.color_a), list(self.color_b)
        return d

    @staticmethod
    def from_json(d: dict) -> "Effect":
        d = dict(d)
        d["color_a"] = tuple(d.get("color_a", (255, 0, 0)))
        d["color_b"] = tuple(d.get("color_b", (0, 0, 255)))
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

    def to_json(self) -> dict:
        return {
            "name": self.name, "fade": self.fade, "hold": self.hold,
            "fade_out": self.fade_out, "delay": self.delay, "delay_out": self.delay_out,
            "values": {str(f): {str(c): v for c, v in ch.items()} for f, ch in self.values.items()},
            "effects": [e.to_json() for e in self.effects],
        }

    @staticmethod
    def from_json(d: dict) -> "Step":
        return Step(
            name=d.get("name", ""), fade=float(d.get("fade", 0)), hold=float(d.get("hold", -1)),
            fade_out=float(d.get("fade_out", -1)), delay=float(d.get("delay", 0)),
            delay_out=float(d.get("delay_out", -1)),
            values={int(f): {int(c): int(v) for c, v in ch.items()} for f, ch in d.get("values", {}).items()},
            effects=[Effect.from_json(e) for e in d.get("effects", [])],
        )


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

    def to_json(self) -> dict:
        return {
            "name": self.name, "mode": self.mode, "speed": self.speed, "fade": self.fade,
            "number": self.number, "bank": self.bank, "source": self.source, "slot": self.slot,
            "steps": [s.to_json() for s in self.steps],
        }

    @staticmethod
    def from_json(d: dict) -> "Playback":
        return Playback(
            name=d["name"], mode=d.get("mode", "chase"), speed=float(d.get("speed", 1)),
            fade=float(d.get("fade", 0)), number=int(d.get("number", 0)),
            bank=d.get("bank", "Playback"), source=d.get("source", ""), slot=int(d.get("slot", -1)),
            steps=[Step.from_json(s) for s in d.get("steps", [])],
        )


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


@dataclass
class Show:
    name: str = "Untitled"
    types: dict[str, FixtureType] = field(default_factory=dict)
    fixtures: list[Fixture] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    playbacks: list[Playback] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)
    stage_width: float = 12.0
    stage_depth: float = 8.0
    stage_height: float = 6.0
    console_info: dict = field(default_factory=dict)
    source_path: str = ""          # console .SHO file this show was imported from

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
            "output": asdict(self.output),
            "console_info": self.console_info,
            "source_path": self.source_path,
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
        if "output" in d:
            s.output = OutputConfig(**{k: v for k, v in d["output"].items()
                                       if k in OutputConfig.__dataclass_fields__})
        s.console_info = d.get("console_info", {})
        s.source_path = d.get("source_path", "")
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
