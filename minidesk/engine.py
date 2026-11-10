"""DMX engine: programmer + playbacks -> DMX universes.

Mixing rules (similar to dot2 / QLC+):
* intensity (``dimmer`` channels) is HTP between playbacks and scaled by the
  playback fader;
* every other attribute is LTP: the most recently activated playback wins;
* the programmer always wins (it is what you are editing);
* the grand master and blackout scale intensity at the very end.  Fixtures
  without a dimmer channel get their RGB/W channels scaled instead.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import copy
import random

from .attributes import HTP_ATTRS
from .effects import apply_effect
from .model import Effect, Fixture, FixtureType, Playback, Show, Step

COLOUR_ATTRS = {"red", "green", "blue", "white", "amber", "uv"}


@dataclass
class PlaybackState:
    pb: Playback
    level: float = 0.0          # fader 0..1
    running: bool = False
    paused: bool = False
    flash: bool = False
    index: int = -1             # current step
    stamp: float = 0.0          # activation order for LTP
    t_step: float = 0.0         # time since step started
    src: dict[tuple[int, int], int] = field(default_factory=dict)
    out: dict[tuple[int, int], int] = field(default_factory=dict)
    speed_factor: float = 1.0
    bounce: int = 1             # current bounce direction
    releasing: float = -1.0     # >= 0: seconds into the release fade
    taps: list = field(default_factory=list)

    @property
    def effective_level(self) -> float:
        lvl = 1.0 if self.flash else self.level
        if self.releasing >= 0 and self.pb.release > 0:
            lvl *= max(0.0, 1.0 - self.releasing / self.pb.release)
        return lvl

    def step(self) -> Optional[Step]:
        if 0 <= self.index < len(self.pb.steps):
            return self.pb.steps[self.index]
        return None


class Engine:
    FPS = 40

    def __init__(self, show: Show):
        self.lock = threading.RLock()
        self.grand_master = 1.0
        self.blackout = False
        self.programmer: dict[int, dict[int, int]] = {}
        self.selection: list[int] = []
        self.highlight = False
        self.states: list[PlaybackState] = []
        self.universes: dict[int, bytearray] = {}
        self.listeners: list[Callable[[], None]] = []
        self.effects: list[Effect] = []          # programmer effects (live)
        self.clock = 0.0                          # effect time base (seconds)
        self.speed_master = 1.0                   # scales all chase / cue timing (2 = twice as fast)
        self.fx_speed = 1.0                       # scales all effect speeds
        self._taps: list = []
        self._eff_start: dict[int, float] = {}
        self._stamp = 0.0
        self.set_show(show)

    # ----------------------------------------------------------------- setup
    def set_show(self, show: Show) -> None:
        with self.lock:
            self.show = show
            self.programmer.clear()
            self.selection.clear()
            self.states = [PlaybackState(pb) for pb in show.playbacks]
            self.rebuild_patch()

    def rebuild_patch(self) -> None:
        with self.lock:
            self._fx: list[tuple[Fixture, FixtureType]] = [
                (f, self.show.ftype(f)) for f in self.show.fixtures]
            self._by_id = {f.fid: (f, t) for f, t in self._fx}
            self.universes = {u: bytearray(512) for u in self.show.universes()}
            known = {id(s.pb) for s in self.states}
            for pb in self.show.playbacks:
                if id(pb) not in known:
                    self.states.append(PlaybackState(pb))
            alive = {id(pb) for pb in self.show.playbacks}
            self.states = [s for s in self.states if id(s.pb) in alive]

    def state_for(self, pb: Playback) -> PlaybackState:
        for s in self.states:
            if s.pb is pb:
                return s
        st = PlaybackState(pb)
        self.states.append(st)
        return st

    # ------------------------------------------------------------ programmer
    def select(self, fids: list[int], add: bool = False) -> None:
        with self.lock:
            if not add:
                self.selection = []
            for f in fids:
                if f in self.selection:
                    if add:
                        self.selection.remove(f)
                elif f in self._by_id:
                    self.selection.append(f)

    def set_attr(self, attr_or_name: str, value: int, fids: Optional[list[int]] = None,
                 by_name: bool = False) -> None:
        """Set an attribute (or channel name) on the selection."""
        value = max(0, min(255, int(value)))
        with self.lock:
            for fid in (fids if fids is not None else self.selection):
                if fid not in self._by_id:
                    continue
                _, ft = self._by_id[fid]
                for i, ch in enumerate(ft.channels):
                    if (ch.name == attr_or_name) if by_name else (ch.attr == attr_or_name):
                        self.programmer.setdefault(fid, {})[i] = value

    def set_channel(self, fid: int, ch: int, value: int) -> None:
        with self.lock:
            self.programmer.setdefault(fid, {})[ch] = max(0, min(255, int(value)))

    def set_intensity(self, percent: float, fids: Optional[list[int]] = None) -> None:
        """dot2 style 'At <percent>': dimmer or RGB-only fixtures."""
        v = int(max(0.0, min(100.0, percent)) * 255 / 100 + 0.5)
        with self.lock:
            for fid in (fids if fids is not None else self.selection):
                if fid not in self._by_id:
                    continue
                _, ft = self._by_id[fid]
                dims = ft.find("dimmer")
                if dims:
                    for i in dims:
                        self.programmer.setdefault(fid, {})[i] = v
                    for i in ft.find("shutter"):
                        if ft.is_moving:
                            self.programmer.setdefault(fid, {}).setdefault(i, 255)
                else:
                    cols = [i for i, c in enumerate(ft.channels) if c.attr in COLOUR_ATTRS]
                    for i in cols:
                        self.programmer.setdefault(fid, {})[i] = v

    def clear_programmer(self, selection_too: bool = True) -> None:
        with self.lock:
            self.programmer.clear()
            self.effects.clear()
            if selection_too:
                self.selection.clear()

    def programmer_value(self, fid: int, ch: int) -> Optional[int]:
        return self.programmer.get(fid, {}).get(ch)

    def snapshot_programmer(self) -> dict[int, dict[int, int]]:
        with self.lock:
            return {f: dict(c) for f, c in self.programmer.items() if c}

    # ------------------------------------------------------------- playbacks
    def _bump(self, st: PlaybackState) -> None:
        self._stamp += 1
        st.stamp = self._stamp

    def _first_index(self, st: PlaybackState) -> int:
        st.bounce = 1
        return len(st.pb.steps) - 1 if st.pb.direction == "backward" else 0

    def _next_index(self, st: PlaybackState, forward: bool = True) -> Optional[int]:
        """Next step honouring direction / bounce / random / loop. None = end reached."""
        n = len(st.pb.steps)
        if n == 0:
            return None
        if n == 1:
            return 0 if st.pb.loop else None
        i, d = st.index, st.pb.direction
        if d == "random":
            return random.choice([k for k in range(n) if k != i])
        if d == "bounce":
            step = st.bounce if forward else -st.bounce
            j = i + step
            if not 0 <= j < n:
                if not st.pb.loop and forward:
                    return None
                st.bounce = -st.bounce if forward else st.bounce
                j = i - step
            return max(0, min(n - 1, j))
        step = 1 if (d == "forward") == forward else -1
        j = i + step
        if not 0 <= j < n:
            if not st.pb.loop:
                return None
            j %= n
        return j

    def _start(self, st: PlaybackState) -> None:
        st.running, st.paused, st.releasing = True, False, -1.0
        if st.level <= 0 and not st.flash:
            st.level = 1.0
        self._goto(st, self._first_index(st))

    def go(self, st: PlaybackState) -> None:
        with self.lock:
            if not st.pb.steps:
                return
            if st.level <= 0 and not st.flash:
                st.level = 1.0
            if not st.running or st.releasing >= 0:
                self._start(st)
            else:
                st.paused = False
                j = self._next_index(st, True)
                if j is not None:
                    self._goto(st, j)

    def back(self, st: PlaybackState) -> None:
        with self.lock:
            if not st.pb.steps:
                return
            if not st.running:
                self._start(st)
                return
            j = self._next_index(st, False)
            if j is not None:
                self._goto(st, j)

    def goto(self, st: PlaybackState, index: int) -> None:
        with self.lock:
            if not st.pb.steps:
                return
            if not st.running:
                st.running, st.releasing = True, -1.0
                if st.level <= 0:
                    st.level = 1.0
            self._goto(st, max(0, min(index, len(st.pb.steps) - 1)))

    def step_progress(self, st: PlaybackState) -> float:
        """0..1 progress through the current step (fade + hold for chases)."""
        step = st.step()
        if step is None or not st.running:
            return 0.0
        total = self._fade_time(st, step)
        if st.pb.mode == "chase" or step.follow:
            total = max(total, self._hold_time(st, step))
        return 1.0 if total <= 0 else min(1.0, st.t_step / total)

    def tap_master(self, base_bpm: float = 120.0) -> float:
        """Global TAP: sets the speed master so that a 120 BPM chase follows the tapped tempo."""
        now = time.perf_counter()
        self._taps = [t for t in self._taps if now - t < 4.0] + [now]
        if len(self._taps) >= 2:
            iv = [b - a for a, b in zip(self._taps, self._taps[1:])]
            bpm = 60.0 / (sum(iv) / len(iv))
            self.speed_master = max(0.1, min(10.0, bpm / base_bpm))
        return self.speed_master

    def tap(self, st: PlaybackState) -> float:
        """Tap tempo: sets the chase speed from the average of the last taps."""
        now = time.perf_counter()
        st.taps = [t for t in st.taps if now - t < 4.0] + [now]
        if len(st.taps) >= 2:
            iv = [b - a for a, b in zip(st.taps, st.taps[1:])]
            st.pb.speed = max(0.05, sum(iv) / len(iv))
        return st.pb.speed

    def pause(self, st: PlaybackState) -> None:
        with self.lock:
            st.paused = not st.paused

    def stop(self, st: PlaybackState, fade: bool = False) -> None:
        """Stop a playback; with ``fade`` and a release time it fades out first."""
        with self.lock:
            if fade and st.pb.release > 0 and st.running:
                if st.releasing < 0:
                    st.releasing = 0.0
                return
            st.running = False
            st.paused = False
            st.releasing = -1.0
            st.index = -1
            st.out.clear()
            st.src.clear()

    def set_level(self, st: PlaybackState, level: float) -> None:
        with self.lock:
            level = max(0.0, min(1.0, level))
            was = st.level
            st.level = level
            if level > 0 and was <= 0 and not st.running and st.pb.steps:
                self._start(st)
                st.level = level
            elif level <= 0 and not st.flash and st.running:
                self.stop(st)

    def set_flash(self, st: PlaybackState, on: bool) -> None:
        with self.lock:
            st.flash = on
            if on and not st.running and st.pb.steps:
                lvl = st.level
                self._start(st)
                st.level = lvl
            elif not on and st.level <= 0:
                self.stop(st)

    def release_all(self) -> None:
        with self.lock:
            for st in self.states:
                st.level = 0
                st.flash = False
                self.stop(st)

    def _goto(self, st: PlaybackState, index: int) -> None:
        st.src = dict(st.out)
        st.index = index
        st.t_step = 0.0
        self._bump(st)

    def _times(self, st: PlaybackState, step: Step) -> tuple[float, float, float, float]:
        """(delay_in, fade_in, delay_out, fade_out) in seconds, after speed factor."""
        sf = max(st.speed_factor * self.speed_master, 0.01)
        fi = step.fade if step.fade > 0 else st.pb.fade
        fo = step.fade_out if step.fade_out >= 0 else fi
        if st.pb.mode == "chase" and st.pb.xfade > 0:      # crossfade as % of the step time
            h = step.hold if step.hold >= 0 else st.pb.speed
            fi = fo = h * min(100.0, st.pb.xfade) / 100.0
        di = max(0.0, step.delay)
        do = step.delay_out if step.delay_out >= 0 else di
        return di / sf, max(0.0, fi) / sf, max(0.0, do) / sf, max(0.0, fo) / sf

    def _fade_time(self, st: PlaybackState, step: Step) -> float:
        di, fi, do, fo = self._times(st, step)
        return max(di + fi, do + fo)

    def _hold_time(self, st: PlaybackState, step: Step) -> float:
        h = step.hold if step.hold >= 0 else st.pb.speed
        return max(0.02, h) / max(st.speed_factor * self.speed_master, 0.01)

    @staticmethod
    def _progress(t: float, delay: float, fade: float) -> float:
        if t < delay:
            return 0.0
        if fade <= 0:
            return 1.0
        return min(1.0, (t - delay) / fade)

    def _advance(self, st: PlaybackState, dt: float) -> None:
        step = st.step()
        if step is None:
            return
        if not st.paused:
            st.t_step += dt
        di, fi, do, fo = self._times(st, step)
        k_in = self._progress(st.t_step, di, fi)
        k_out = self._progress(st.t_step, do, fo)
        target = {(f, c): v for f, chans in step.values.items() for c, v in chans.items()}
        out = {}
        for key, v in target.items():
            htp = self._is_htp(key)
            a = st.src.get(key, 0 if htp else v)
            k = k_out if (htp and v < a) else k_in      # intensity going down uses fade out
            out[key] = round(a + (v - a) * k)
        for key, a in st.src.items():                    # intensity not in the new step fades out
            if key not in target and self._is_htp(key) and k_out < 1.0:
                out[key] = round(a * (1 - k_out))
        st.out = out
        if st.paused:
            return
        auto = (st.pb.mode == "chase" and len(st.pb.steps) > 1) or (st.pb.mode == "cuelist" and step.follow)
        if auto:
            wait = self._hold_time(st, step)
            if st.pb.mode == "chase" and st.pb.xfade > 0:
                wait = max(wait, 0.02)
                ready = st.t_step >= wait
            else:
                ready = st.t_step >= max(self._fade_time(st, step), wait)
            if ready:
                j = self._next_index(st, True)
                if j is not None and (j != st.index or st.pb.direction == "random"):
                    self._goto(st, j)

    def _is_htp(self, key: tuple[int, int]) -> bool:
        fid, ch = key
        e = self._by_id.get(fid)
        if not e:
            return False
        chans = e[1].channels
        return ch < len(chans) and chans[ch].attr in HTP_ATTRS

    # ------------------------------------------------------------------ tick
    def add_effect(self, eff: Effect) -> Effect:
        with self.lock:
            self.effects.append(eff)
            self._eff_start[id(eff)] = self.clock
        return eff

    def remove_effect(self, eff: Effect) -> None:
        with self.lock:
            if eff in self.effects:
                self.effects.remove(eff)

    def tick(self, dt: float) -> dict[int, bytearray]:
        with self.lock:
            self.clock += dt * self.fx_speed
            t = self.clock
            for st in self.states:
                if st.running:
                    self._advance(st, dt)
                    if st.releasing >= 0:
                        st.releasing += dt
                        if st.releasing >= st.pb.release:
                            self.stop(st)
                            st.level = 0.0
            for u in self.universes.values():
                u[:] = bytes(512)
            active = sorted((s for s in self.states if s.running and s.effective_level > 0),
                            key=lambda s: s.stamp)
            gm = 0.0 if self.blackout else self.grand_master
            for fx, ft in self._fx:
                if not fx.patched:
                    continue
                uni = self.universes.setdefault(fx.universe, bytearray(512))
                n = len(ft.channels)
                vals = [c.default for c in ft.channels]
                htp = [0.0] * n
                htp_set = [False] * n
                for st in active:
                    lvl = st.effective_level
                    for i in range(n):
                        v = st.out.get((fx.fid, i))
                        if v is None:
                            continue
                        if ft.channels[i].attr in HTP_ATTRS:
                            htp[i] = max(htp[i], v * lvl)
                            htp_set[i] = True
                        else:
                            vals[i] = v
                for i in range(n):
                    if htp_set[i]:
                        vals[i] = round(htp[i])
                for st in active:      # effects stored in the running steps
                    step = st.step()
                    if step and step.effects:
                        for eff in step.effects:
                            apply_effect(eff, ft, fx.fid, vals, t, st.effective_level, st.t_step)
                prog = self.programmer.get(fx.fid)
                if prog:
                    for i, v in prog.items():
                        if i < n:
                            vals[i] = v
                for eff in self.effects:
                    apply_effect(eff, ft, fx.fid, vals, t, 1.0, t - self._eff_start.get(id(eff), 0.0))
                if self.highlight and fx.fid in self.selection:
                    self._apply_highlight(ft, vals)
                if fx.invert_pan or fx.invert_tilt or fx.swap_pan_tilt:
                    self._pt_options(fx, ft, vals)
                if gm < 1.0:
                    dims = [i for i, c in enumerate(ft.channels) if c.attr in HTP_ATTRS]
                    scale = dims or [i for i, c in enumerate(ft.channels) if c.attr in COLOUR_ATTRS]
                    for i in scale:
                        vals[i] = round(vals[i] * gm)
                base = fx.address - 1
                for i, v in enumerate(vals):
                    a = base + i
                    if 0 <= a < 512:
                        uni[a] = v
            return self.universes

    @staticmethod
    def _pt_options(fx: Fixture, ft: FixtureType, vals: list[int]) -> None:
        idx = {c.attr: i for i, c in enumerate(ft.channels)}
        if fx.swap_pan_tilt:
            for a, b in (("pan", "tilt"), ("pan_fine", "tilt_fine")):
                if a in idx and b in idx:
                    vals[idx[a]], vals[idx[b]] = vals[idx[b]], vals[idx[a]]
        for flag, names in ((fx.invert_pan, ("pan", "pan_fine")), (fx.invert_tilt, ("tilt", "tilt_fine"))):
            if flag:
                for n in names:
                    if n in idx:
                        vals[idx[n]] = 255 - vals[idx[n]]

    @staticmethod
    def _apply_highlight(ft: FixtureType, vals: list[int]) -> None:
        for i, c in enumerate(ft.channels):
            if c.attr == "dimmer":
                vals[i] = 255
            elif c.attr in ("red", "green", "blue", "white"):
                vals[i] = 255
            elif c.attr in ("cyan", "magenta", "yellow", "color", "gobo", "prism", "frost"):
                vals[i] = 0
            elif c.attr == "shutter" and ft.is_moving:
                vals[i] = 255
            elif c.attr in ("shutter", "strobe") and not ft.is_moving:
                vals[i] = 0

    # -------------------------------------------------------------- storing
    def store(self, pb: Playback, mode: str = "add", index: Optional[int] = None,
              fade: float = 0.0, merge: bool = False) -> Step:
        """Store programmer into ``pb``: mode add | overwrite | merge."""
        with self.lock:
            vals = self.snapshot_programmer()
            effs = copy.deepcopy(self.effects)
            if mode == "add" or not pb.steps:
                st = Step(name=f"Step {len(pb.steps) + 1}", values=vals, fade=fade, effects=effs)
                if index is None or index >= len(pb.steps):
                    pb.steps.append(st)
                else:
                    pb.steps.insert(index, st)
                return st
            i = index if index is not None else len(pb.steps) - 1
            st = pb.steps[i]
            if mode == "merge":
                for f, chans in vals.items():
                    st.values.setdefault(f, {}).update(chans)
                st.effects += effs
            else:
                st.values = vals
                st.effects = effs
            return st

    # -------------------------------------------------------------- presets
    def apply_preset(self, preset, fids: Optional[list[int]] = None) -> int:
        """Put a preset into the programmer for the selection. Returns fixtures affected."""
        with self.lock:
            targets = fids if fids is not None else (self.selection or list(preset.values))
            by_type = {}
            for f, vals in preset.values.items():
                e = self._by_id.get(f)
                if e:
                    by_type.setdefault(e[0].type_key, vals)
            n = 0
            for fid in targets:
                e = self._by_id.get(fid)
                if not e:
                    continue
                vals = preset.values.get(fid) or by_type.get(e[0].type_key)
                if vals:
                    self.programmer.setdefault(fid, {}).update(vals)
                    n += 1
            return n

    def make_preset(self, name: str, category: str):
        """Create a preset from the programmer, keeping only channels of ``category``."""
        from .attributes import FEATURE_OF
        from .model import Preset
        with self.lock:
            vals = {}
            for fid, chans in self.programmer.items():
                e = self._by_id.get(fid)
                if not e:
                    continue
                ft = e[1]
                keep = {c: v for c, v in chans.items() if c < len(ft.channels) and (
                    category == "All" or FEATURE_OF.get(ft.channels[c].attr.replace("_fine", ""),
                                                        "Other") == category)}
                if keep:
                    vals[fid] = keep
            return Preset(name=name, category=category, values=vals)

    @property
    def programmer_empty(self) -> bool:
        return not any(self.programmer.values()) and not self.effects


class EngineRunner(threading.Thread):
    """Runs the engine at a fixed rate and hands frames to outputs."""

    def __init__(self, engine: Engine, outputs: Callable[[dict[int, bytearray]], None]):
        super().__init__(daemon=True)
        self.engine = engine
        self.outputs = outputs
        self._stop = threading.Event()

    def run(self) -> None:
        period = 1.0 / Engine.FPS
        last = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            dt, last = now - last, now
            frame = self.engine.tick(dt)
            try:
                self.outputs(frame)
            except Exception:   # outputs must never kill the engine
                pass
            time.sleep(max(0.0, period - (time.perf_counter() - now)))

    def stop(self) -> None:
        self._stop.set()
