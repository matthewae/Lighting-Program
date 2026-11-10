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

from .attributes import HTP_ATTRS
from .model import Fixture, FixtureType, Playback, Show, Step

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

    @property
    def effective_level(self) -> float:
        return 1.0 if self.flash else self.level

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

    def go(self, st: PlaybackState) -> None:
        with self.lock:
            if not st.pb.steps:
                return
            if st.level <= 0 and not st.flash:
                st.level = 1.0
            if not st.running:
                st.running, st.paused = True, False
                self._goto(st, 0)
            else:
                st.paused = False
                self._goto(st, (st.index + 1) % len(st.pb.steps))

    def back(self, st: PlaybackState) -> None:
        with self.lock:
            if not st.pb.steps:
                return
            if not st.running:
                st.running = True
                if st.level <= 0:
                    st.level = 1.0
            self._goto(st, (st.index - 1) % len(st.pb.steps))

    def goto(self, st: PlaybackState, index: int) -> None:
        with self.lock:
            if not st.pb.steps:
                return
            if not st.running:
                st.running = True
                if st.level <= 0:
                    st.level = 1.0
            self._goto(st, max(0, min(index, len(st.pb.steps) - 1)))

    def pause(self, st: PlaybackState) -> None:
        with self.lock:
            st.paused = not st.paused

    def stop(self, st: PlaybackState) -> None:
        with self.lock:
            st.running = False
            st.paused = False
            st.index = -1
            st.out.clear()
            st.src.clear()

    def set_level(self, st: PlaybackState, level: float) -> None:
        with self.lock:
            level = max(0.0, min(1.0, level))
            was = st.level
            st.level = level
            if level > 0 and was <= 0 and not st.running and st.pb.steps:
                st.running = True
                self._goto(st, 0)
            elif level <= 0 and not st.flash and st.running:
                self.stop(st)

    def set_flash(self, st: PlaybackState, on: bool) -> None:
        with self.lock:
            st.flash = on
            if on and not st.running and st.pb.steps:
                st.running = True
                self._goto(st, 0)
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

    def _fade_time(self, st: PlaybackState, step: Step) -> float:
        f = step.fade if step.fade > 0 else st.pb.fade
        return max(0.0, f) / max(st.speed_factor, 0.01)

    def _hold_time(self, st: PlaybackState, step: Step) -> float:
        h = step.hold if step.hold >= 0 else st.pb.speed
        return max(0.02, h) / max(st.speed_factor, 0.01)

    def _advance(self, st: PlaybackState, dt: float) -> None:
        step = st.step()
        if step is None:
            return
        if not st.paused:
            st.t_step += dt
        fade = self._fade_time(st, step)
        target = {(f, c): v for f, chans in step.values.items() for c, v in chans.items()}
        if fade <= 0 or st.t_step >= fade:
            k = 1.0
        else:
            k = st.t_step / fade
        out = {}
        for key, v in target.items():
            a = st.src.get(key, 0 if self._is_htp(key) else v)
            out[key] = round(a + (v - a) * k)
        if k < 1.0:   # fade out values not present in the new step (intensity only)
            for key, a in st.src.items():
                if key not in target and self._is_htp(key):
                    out[key] = round(a * (1 - k))
        st.out = out
        if st.pb.mode == "chase" and len(st.pb.steps) > 1 and not st.paused:
            if st.t_step >= max(fade, self._hold_time(st, step)):
                self._goto(st, (st.index + 1) % len(st.pb.steps))

    def _is_htp(self, key: tuple[int, int]) -> bool:
        fid, ch = key
        e = self._by_id.get(fid)
        if not e:
            return False
        chans = e[1].channels
        return ch < len(chans) and chans[ch].attr in HTP_ATTRS

    # ------------------------------------------------------------------ tick
    def tick(self, dt: float) -> dict[int, bytearray]:
        with self.lock:
            for st in self.states:
                if st.running:
                    self._advance(st, dt)
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
                prog = self.programmer.get(fx.fid)
                if prog:
                    for i, v in prog.items():
                        if i < n:
                            vals[i] = v
                if self.highlight and fx.fid in self.selection:
                    self._apply_highlight(ft, vals)
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
            if mode == "add" or not pb.steps:
                st = Step(name=f"Step {len(pb.steps) + 1}", values=vals, fade=fade)
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
            else:
                st.values = vals
            return st


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
