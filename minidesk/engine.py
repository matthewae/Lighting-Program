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
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "highest": 3}
# attributes that jump (do not cross-fade); they switch at the cue's "Snap Percent"
SNAP_ATTRS = {"gobo", "gobo_rot", "color", "prism", "prism_rot", "colormacro", "effect", "control",
              "shutter", "strobe", "fog", "fan"}
# console Edit Time attribute groups
TIME_GROUPS = ["Dimmer", "Shutter", "Position", "Colour", "Gobo", "Beam"]
_GROUP_OF = {"dimmer": "Dimmer", "shutter": "Shutter", "strobe": "Shutter",
             "pan": "Position", "tilt": "Position", "pan_fine": "Position", "tilt_fine": "Position",
             "speed": "Position", "red": "Colour", "green": "Colour", "blue": "Colour", "white": "Colour",
             "amber": "Colour", "uv": "Colour", "cyan": "Colour", "magenta": "Colour", "yellow": "Colour",
             "color": "Colour", "colormacro": "Colour", "ctc": "Colour", "gobo": "Gobo", "gobo_rot": "Gobo",
             "prism": "Beam", "prism_rot": "Beam", "frost": "Beam", "zoom": "Beam", "focus": "Beam",
             "iris": "Beam"}


def time_group(attr: str) -> Optional[str]:
    return _GROUP_OF.get(attr)


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
    timing: dict = field(default_factory=dict)   # (fid, ch) -> (d_in, f_in, d_out, f_out, snap) of the step
    fx_clock: float = 0.0       # effect clock of this playback (fader = FX speed modes)

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
        self.held: dict[tuple[int, int], int] = {}   # LTP kept after "Release Dimmer Only" playbacks
        self.align = False                        # console "Fixture Align": wheels set the same value
        self.even_odd_state = 0
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

    # ------------------------------------------------- console programmer surface
    def output_value(self, fid: int, ch: int) -> int:
        """Current DMX value of a fixture channel (last frame)."""
        e = self._by_id.get(fid)
        if not e or not e[0].patched:
            return self.programmer.get(fid, {}).get(ch, 0)
        u = self.universes.get(e[0].universe)
        a = e[0].address - 1 + ch
        return u[a] if u is not None and 0 <= a < 512 else 0

    def wheel_value(self, key: str, page: int, wheel: int) -> Optional[tuple[str, int]]:
        """(label, value) of an encoder wheel for the first selected fixture that has it."""
        from . import console
        slot = console.wheel_slot(key, page, wheel)
        for fid in self.selection:
            e = self._by_id.get(fid)
            if not e:
                continue
            ch = console.slot_channel(e[1], slot)
            if ch:
                v = self.programmer.get(fid, {}).get(ch[0])
                return e[1].channels[ch[0]].name, (self.output_value(fid, ch[0]) if v is None else v)
        return None

    def wheel_move(self, key: str, page: int, wheel: int, delta: int = 0, value: Optional[int] = None) -> None:
        """Turn an encoder: relative for every fixture, or (Fixture Align) the same value for all."""
        from . import console
        slot = console.wheel_slot(key, page, wheel)
        with self.lock:
            first = None
            for fid in self.selection:
                e = self._by_id.get(fid)
                if not e:
                    continue
                ch = console.slot_channel(e[1], slot)
                if not ch:
                    continue
                c, f = ch
                cur = self.programmer.get(fid, {}).get(c)
                cur = self.output_value(fid, c) if cur is None else cur
                if value is not None:
                    new = value
                elif self.align and first is not None:
                    new = first
                else:
                    new = cur + delta
                new = max(0, min(255, int(new)))
                if first is None:
                    first = new
                self.programmer.setdefault(fid, {})[c] = new
                if f >= 0:
                    self.programmer[fid].setdefault(f, 0)

    def open_full(self, fids: Optional[list[int]] = None) -> None:
        from . import console
        with self.lock:
            for fid in (fids if fids is not None else self.selection):
                e = self._by_id.get(fid)
                if e:
                    self.programmer.setdefault(fid, {}).update(console.open_full_values(e[1]))

    def locate(self, fids: Optional[list[int]] = None) -> None:
        from . import console
        with self.lock:
            for fid in (fids if fids is not None else self.selection):
                e = self._by_id.get(fid)
                if e:
                    self.programmer.setdefault(fid, {}).update(console.locate_values(e[1]))

    def even_odd(self, base: list[int]) -> list[int]:
        """Even/Odd key over ``base`` (the full selection): all -> odd -> even -> all."""
        from . import console
        sel, self.even_odd_state = console.even_odd(base, self.even_odd_state)
        with self.lock:
            self.selection = [f for f in sel if f in self._by_id]
        return self.selection

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
            if st.running and st.pb.release_mode == "dimmer":    # keep LTP values on stage
                for key, v in st.out.items():
                    if not self._is_htp(key):
                        self.held[key] = v
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
            self.held.clear()
            for st in self.states:
                st.level = 0
                st.flash = False
                self.stop(st)

    def _goto(self, st: PlaybackState, index: int) -> None:
        st.src = dict(st.out)
        st.index = index
        st.t_step = 0.0
        st.timing = self._step_timing(st, st.pb.steps[index]) if 0 <= index < len(st.pb.steps) else {}
        self._bump(st)

    def _step_timing(self, st: PlaybackState, step: Step) -> dict:
        """Per channel (delay in, fade in, delay out, fade out, snap) for the console cue options:
        attribute times, fixture overlap + order direction and snap percent (unscaled seconds)."""
        if not (step.attr_times or step.overlap < 100.0 or step.snap > 0):
            return {}
        sf = 1.0
        di, fi, do, fo = (x * max(st.speed_factor * self.speed_master, 0.01) for x in self._times(st, step))
        fids = list(step.values)
        n = len(fids)
        order = step.order_dir
        if order == "backward":
            fids = fids[::-1]
        elif order == "random":
            rnd = random.Random(id(step))
            rnd.shuffle(fids)
        elif order in ("center_out", "outside_in"):
            mid = (n - 1) / 2
            fids = sorted(fids, key=lambda f: abs(list(step.values).index(f) - mid),
                          reverse=order == "outside_in")
        rank = {f: k for k, f in enumerate(fids)}
        ov = max(0.0, min(1.0, step.overlap / 100.0))
        out = {}
        for fid, chans in step.values.items():
            e = self._by_id.get(fid)
            if not e:
                continue
            for c in chans:
                attr = e[1].channels[c].attr if c < len(e[1].channels) else "none"
                g = time_group(attr)
                d1, f1, d2, f2 = di, fi, do, fo
                if g and g in step.attr_times:
                    d1, f1 = step.attr_times[g]
                    d2, f2 = d1, f1
                if ov < 1.0 and n > 1:                  # fixtures one after another
                    k = rank.get(fid, 0)
                    fa = f1 / (1 + (n - 1) * (1 - ov))
                    fb = f2 / (1 + (n - 1) * (1 - ov))
                    d1, f1 = d1 + k * fa * (1 - ov), fa
                    d2, f2 = d2 + k * fb * (1 - ov), fb
                out[(fid, c)] = (d1 / sf, f1 / sf, d2 / sf, f2 / sf, attr in SNAP_ATTRS)
        return out
    def _times(self, st: PlaybackState, step: Step) -> tuple[float, float, float, float]:
        """(delay_in, fade_in, delay_out, fade_out) in seconds, after speed factor."""
        sf = max(st.speed_factor * self.speed_master, 0.01)
        if not st.pb.use_times:                            # "Use Delay and Fade time" off: cues snap
            return 0.0, 0.0, 0.0, 0.0
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
        if st.pb.run_mode == "beat":                       # one step per beat of the TAP tempo
            h = 0.5
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
        timing = st.timing
        sf = max(st.speed_factor * self.speed_master, 0.01)
        snap = max(0.0, min(100.0, step.snap)) / 100.0
        for key, v in target.items():
            htp = self._is_htp(key)
            a = st.src.get(key, 0 if htp else v)
            tm = timing.get(key)
            if tm:
                ki = self._progress(st.t_step, tm[0] / sf, tm[1] / sf)
                ko = self._progress(st.t_step, tm[2] / sf, tm[3] / sf)
                if tm[4] and not htp:                    # snap attribute: jump at Snap Percent
                    ki = 1.0 if (st.t_step >= tm[0] / sf and ki >= snap) else 0.0
            else:
                ki, ko = k_in, k_out
                if not htp and self._is_snap(key):        # gobo / wheel / prism ... jump
                    ki = 1.0 if (st.t_step >= di and k_in >= snap) else 0.0
            k = ko if (htp and v < a) else ki            # intensity going down uses fade out
            out[key] = round(a + (v - a) * k)
        for key, a in st.src.items():                    # intensity not in the new step fades out
            if key not in target and self._is_htp(key) and k_out < 1.0:
                out[key] = round(a * (1 - k_out))
        if step.mib and k_out >= 1.0 and len(st.pb.steps) > 1:   # move in black
            nxt = st.pb.steps[(st.index + 1) % len(st.pb.steps)]
            for fid, chans in nxt.values.items():
                e = self._by_id.get(fid)
                if not e:
                    continue
                dims = [i for i, c in enumerate(e[1].channels) if c.attr in HTP_ATTRS]
                if dims and all(out.get((fid, i), 0) == 0 for i in dims):
                    for c, v in chans.items():
                        if c not in dims:
                            out[(fid, c)] = v
        st.out = out
        if st.paused:
            return
        auto = (st.pb.mode == "chase" and len(st.pb.steps) > 1) or (st.pb.mode == "cuelist" and step.follow)
        if st.pb.run_mode == "manual":                     # only GO advances
            auto = False
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

    def _is_snap(self, key: tuple[int, int]) -> bool:
        fid, ch = key
        e = self._by_id.get(fid)
        if not e:
            return False
        chans = e[1].channels
        return ch < len(chans) and chans[ch].attr in SNAP_ATTRS

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
                    lvl = st.effective_level
                    k = lvl if st.pb.fx_mode in ("speed", "size_speed") else 1.0
                    st.fx_clock += dt * self.fx_speed * k
                    self._advance(st, dt)
                    if st.releasing >= 0:
                        st.releasing += dt
                        if st.releasing >= st.pb.release:
                            self.stop(st)
                            st.level = 0.0
            for u in self.universes.values():
                u[:] = bytes(512)
            active = sorted((s for s in self.states if s.running and s.effective_level > 0),
                            key=lambda s: (PRIORITY_RANK.get(s.pb.priority, 1), s.stamp))
            held = self.held
            gm = 0.0 if self.blackout else self.grand_master
            for fx, ft in self._fx:
                if not fx.patched:
                    continue
                uni = self.universes.setdefault(fx.universe, bytearray(512))
                n = len(ft.channels)
                vals = [c.default for c in ft.channels]
                if held:
                    for i in range(n):
                        v = held.get((fx.fid, i))
                        if v is not None:
                            vals[i] = v
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
                        lvl = st.effective_level
                        mode = st.pb.fx_mode
                        for eff in step.effects:
                            from .effects import INTENSITY
                            if mode in ("size", "size_speed") or eff.type in INTENSITY:
                                k = lvl                  # fader scales the effect (size / intensity)
                            else:
                                k = 1.0                  # Normal: fader = intensity only
                            apply_effect(eff, ft, fx.fid, vals, st.fx_clock, k, st.t_step)
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
