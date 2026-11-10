"""MIDI input/output with "MIDI learn" mapping to MiniDesk actions.

Backends (first available wins):
* Windows: WinMM through ctypes – built into Windows, nothing to install
* python-rtmidi (``pip install python-rtmidi``) on Linux/macOS

Use it to drive MiniDesk from the console's MIDI port or any MIDI controller
(notes / control changes are learned), and to send MIDI notes out when a
playback is triggered (feedback / triggering a device that listens to MIDI).
"""
from __future__ import annotations

import sys
import threading
from typing import Callable, Optional

ACTIONS = {
    "exec_go": "Playback GO",
    "exec_back": "Playback back",
    "exec_flash": "Playback flash (hold)",
    "exec_fader": "Playback fader",
    "exec_stop": "Playback stop",
    "gm": "Grand master",
    "blackout": "Blackout toggle",
    "bank_next": "Next bank",
    "bank_prev": "Previous bank",
    "release_all": "Release all",
}


def parse(status: int, d1: int, d2: int) -> Optional[dict]:
    kind = status & 0xF0
    ch = status & 0x0F
    if kind == 0x90 and d2 > 0:
        return {"kind": "note", "ch": ch, "num": d1, "val": d2, "on": True}
    if kind == 0x80 or (kind == 0x90 and d2 == 0):
        return {"kind": "note", "ch": ch, "num": d1, "val": 0, "on": False}
    if kind == 0xB0:
        return {"kind": "cc", "ch": ch, "num": d1, "val": d2, "on": d2 > 0}
    if kind == 0xC0:
        return {"kind": "pc", "ch": ch, "num": d1, "val": 127, "on": True}
    return None


# --------------------------------------------------------------- backends
class _WinMM:
    name = "Windows MIDI (WinMM)"

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes
        self.w = ctypes.WinDLL("winmm")
        W = wintypes

        class INCAPS(ctypes.Structure):
            _fields_ = [("wMid", W.WORD), ("wPid", W.WORD), ("vDriverVersion", W.UINT),
                        ("szPname", W.WCHAR * 32), ("dwSupport", W.DWORD)]

        class OUTCAPS(ctypes.Structure):
            _fields_ = [("wMid", W.WORD), ("wPid", W.WORD), ("vDriverVersion", W.UINT),
                        ("szPname", W.WCHAR * 32), ("wTechnology", W.WORD), ("wVoices", W.WORD),
                        ("wNotes", W.WORD), ("wChannelMask", W.WORD), ("dwSupport", W.DWORD)]
        self.INCAPS, self.OUTCAPS = INCAPS, OUTCAPS
        self.CB = ctypes.WINFUNCTYPE(None, W.HANDLE, W.UINT, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t)

    def inputs(self) -> list[str]:
        out = []
        for i in range(self.w.midiInGetNumDevs()):
            caps = self.INCAPS()
            if self.w.midiInGetDevCapsW(i, self.ct.byref(caps), self.ct.sizeof(caps)) == 0:
                out.append(caps.szPname)
        return out

    def outputs(self) -> list[str]:
        out = []
        for i in range(self.w.midiOutGetNumDevs()):
            caps = self.OUTCAPS()
            if self.w.midiOutGetDevCapsW(i, self.ct.byref(caps), self.ct.sizeof(caps)) == 0:
                out.append(caps.szPname)
        return out

    def open_input(self, name: str, cb: Callable[[int, int, int], None]):
        idx = self.inputs().index(name)
        handle = self.ct.c_void_p()

        def _cb(h, msg, inst, p1, p2):
            if msg == 0x3C3:   # MIM_DATA
                cb(p1 & 0xFF, (p1 >> 8) & 0x7F, (p1 >> 16) & 0x7F)
        cfunc = self.CB(_cb)
        if self.w.midiInOpen(self.ct.byref(handle), idx, cfunc, 0, 0x30000) != 0:
            raise OSError(f"cannot open MIDI input {name}")
        self.w.midiInStart(handle)
        w = self.w

        class Port:
            keep = cfunc

            def close(self_):
                w.midiInStop(handle)
                w.midiInClose(handle)
        return Port()

    def open_output(self, name: str):
        idx = self.outputs().index(name)
        handle = self.ct.c_void_p()
        if self.w.midiOutOpen(self.ct.byref(handle), idx, 0, 0, 0) != 0:
            raise OSError(f"cannot open MIDI output {name}")
        w = self.w

        class Port:
            def send(self_, status, d1, d2):
                w.midiOutShortMsg(handle, status | (d1 << 8) | (d2 << 16))

            def close(self_):
                w.midiOutClose(handle)
        return Port()


class _RtMidi:
    name = "python-rtmidi"

    def __init__(self):
        import rtmidi  # noqa: F401
        self.rtmidi = rtmidi

    def inputs(self):
        return self.rtmidi.MidiIn().get_ports()

    def outputs(self):
        return self.rtmidi.MidiOut().get_ports()

    def open_input(self, name, cb):
        m = self.rtmidi.MidiIn()
        m.open_port(self.inputs().index(name))
        m.set_callback(lambda ev, _d: len(ev[0]) >= 2 and cb(ev[0][0], ev[0][1], ev[0][2] if len(ev[0]) > 2 else 0))

        class Port:
            def close(self_):
                m.close_port()
        return Port()

    def open_output(self, name):
        m = self.rtmidi.MidiOut()
        m.open_port(self.outputs().index(name))

        class Port:
            def send(self_, status, d1, d2):
                m.send_message([status, d1, d2])

            def close(self_):
                m.close_port()
        return Port()


def backend():
    if sys.platform.startswith("win"):
        try:
            return _WinMM()
        except Exception:
            pass
    try:
        return _RtMidi()
    except Exception:
        return None


# ---------------------------------------------------------------- manager
class MidiManager:
    """Keeps the MIDI ports open and turns messages into actions."""

    def __init__(self, on_action: Callable[[str, int, float, bool], None],
                 on_message: Optional[Callable[[dict], None]] = None):
        self.on_action = on_action          # (action, target, value 0..1, pressed)
        self.on_message = on_message        # every parsed message (for the monitor / learn)
        self.mapping: list[dict] = []
        self.backend = backend()
        self.inp = None
        self.out = None
        self.learn: Optional[Callable[[dict], None]] = None
        self.last = ""
        self.lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.backend is not None

    def inputs(self) -> list[str]:
        try:
            return self.backend.inputs() if self.backend else []
        except Exception:
            return []

    def outputs(self) -> list[str]:
        try:
            return self.backend.outputs() if self.backend else []
        except Exception:
            return []

    def open(self, inp: str, out: str) -> list[str]:
        self.close()
        errs = []
        if not self.backend:
            return ["No MIDI backend (on Linux/macOS: pip install python-rtmidi)"] if (inp or out) else []
        if inp:
            try:
                self.inp = self.backend.open_input(inp, self._raw)
            except Exception as e:
                errs.append(str(e))
        if out:
            try:
                self.out = self.backend.open_output(out)
            except Exception as e:
                errs.append(str(e))
        return errs

    def close(self) -> None:
        for p in (self.inp, self.out):
            try:
                if p:
                    p.close()
            except Exception:
                pass
        self.inp = self.out = None

    def _raw(self, status: int, d1: int, d2: int) -> None:
        msg = parse(status, d1, d2)
        if msg:
            self.feed(msg)

    def feed(self, msg: dict) -> None:
        """Handle one parsed message (also used by tests)."""
        self.last = f"{msg['kind']} ch{msg['ch'] + 1} #{msg['num']} = {msg['val']}"
        if self.on_message:
            self.on_message(msg)
        if self.learn and msg["on"]:
            cb, self.learn = self.learn, None
            cb(msg)
            return
        for m in self.mapping:
            if m["kind"] == msg["kind"] and m["ch"] == msg["ch"] and m["num"] == msg["num"]:
                value = msg["val"] / 127.0
                self.on_action(m["action"], int(m.get("target", 1)), value, msg["on"])

    def send_note(self, num: int, ch: int = 0, vel: int = 127) -> None:
        if self.out:
            try:
                self.out.send(0x90 | (ch & 0x0F), num & 0x7F, vel & 0x7F)
                self.out.send(0x80 | (ch & 0x0F), num & 0x7F, 0)
            except Exception:
                pass

    @staticmethod
    def default_bank_map(first_exec: int, count: int = 15) -> list[dict]:
        """Notes 0..n-1 = GO, CC 0..n-1 = faders of the executors starting at ``first_exec``."""
        m = []
        for i in range(count):
            m.append({"kind": "note", "ch": 0, "num": i, "action": "exec_go", "target": first_exec + i})
            m.append({"kind": "cc", "ch": 0, "num": i, "action": "exec_fader", "target": first_exec + i})
        return m
