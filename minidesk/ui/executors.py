"""Executor / playback fader bar (dot2 executor wing style)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel, QMenu, QProgressBar,
                               QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from ..engine import Engine, PlaybackState
from ..model import FIXED_BANKS, FIXED_PER_BANK, PB_BANKS, PB_PER_BANK


class ExecutorStrip(QWidget):
    selected = Signal(object)
    triggered = Signal(object)        # GO pressed (for MIDI feedback)

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.st: PlaybackState | None = None
        self.setFixedWidth(84)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.num = QLabel("")
        self.num.setAlignment(Qt.AlignCenter)
        self.name = QPushButton("—")
        self.name.setToolTip("Click to edit this playback in the Cues tab")
        self.name.setStyleSheet("text-align:center; font-size:8pt;")
        self.name.setMinimumHeight(30)
        self.name.clicked.connect(lambda: self.st and self.selected.emit(self.st))
        self.name.setContextMenuPolicy(Qt.CustomContextMenu)
        self.name.customContextMenuRequested.connect(self._menu)
        self.step = QLabel("")
        self.step.setAlignment(Qt.AlignCenter)
        self.step.setStyleSheet("color:#8fd18f; font-size:8pt;")
        self.prog = QProgressBar()
        self.prog.setRange(0, 1000)
        self.prog.setTextVisible(False)
        self.prog.setFixedHeight(4)
        self.prog.setObjectName("stepbar")
        self.slider = QSlider(Qt.Vertical)
        self.slider.setRange(0, 100)
        self.slider.setMinimumHeight(60)
        self.slider.valueChanged.connect(self._level)
        self.lvl = QLabel("0%")
        self.lvl.setAlignment(Qt.AlignCenter)
        row1 = QHBoxLayout()
        self.b_back = QPushButton("<")
        self.b_go = QPushButton("GO")
        self.b_go.setObjectName("go")
        row1.addWidget(self.b_back)
        row1.addWidget(self.b_go)
        row2 = QHBoxLayout()
        self.b_pause = QPushButton("||")
        self.b_stop = QPushButton("■")
        row2.addWidget(self.b_pause)
        row2.addWidget(self.b_stop)
        self.b_flash = QPushButton("Flash")
        self.b_flash.setObjectName("flash")
        for b in (self.b_back, self.b_go, self.b_pause, self.b_stop, self.b_flash):
            b.setFixedHeight(26)
            b.setStyleSheet("padding: 2px 4px;")
        self.b_go.clicked.connect(self._go)
        self.b_back.clicked.connect(lambda: self.st and self.engine.back(self.st))
        self.b_pause.clicked.connect(lambda: self.st and self.engine.pause(self.st))
        self.b_stop.clicked.connect(self._stop)
        self.b_flash.pressed.connect(lambda: self.st and self.engine.set_flash(self.st, True))
        self.b_flash.released.connect(lambda: self.st and self.engine.set_flash(self.st, False))
        for w in (self.num, self.name, self.step, self.prog):
            lay.addWidget(w)
        lay.addWidget(self.slider, 1, Qt.AlignHCenter)
        lay.addWidget(self.lvl)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addWidget(self.b_flash)

    def _go(self):
        if self.st:
            self.engine.go(self.st)
            self.triggered.emit(self.st)

    def _stop(self):
        if self.st:
            self.engine.stop(self.st, fade=True)
            if self.st.pb.release <= 0:
                self.slider.setValue(0)

    def _menu(self, pos):
        if not self.st:
            return
        m = QMenu(self)
        m.addAction("Edit cues…", lambda: self.selected.emit(self.st))
        m.addAction("TAP tempo", lambda: self.engine.tap(self.st))
        m.addAction("Speed ×2", lambda: setattr(self.st.pb, "speed", max(0.02, self.st.pb.speed / 2)))
        m.addAction("Speed ÷2", lambda: setattr(self.st.pb, "speed", self.st.pb.speed * 2))
        m.addSeparator()
        m.addAction("Stop immediately", lambda: (self.engine.stop(self.st), self.slider.setValue(0)))
        m.exec(self.name.mapToGlobal(pos))

    def bind(self, st: PlaybackState | None, empty_label: str = "") -> None:
        self.st = st
        self.empty_label = empty_label
        en = st is not None
        for w in (self.slider, self.b_go, self.b_back, self.b_pause, self.b_stop, self.b_flash, self.name):
            w.setEnabled(en)
        self.sync()

    def _level(self, v: int) -> None:
        if self.st:
            self.engine.set_level(self.st, v / 100.0)
        self.lvl.setText(f"{v}%")

    def sync(self) -> None:
        st = self.st
        if st is None:
            self.num.setText(getattr(self, "empty_label", ""))
            self.num.setToolTip("Empty position on the console")
            self.name.setText("—")
            self.step.setText("")
            self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(False)
            self.lvl.setText("")
            return
        self.num.setText(st.pb.console_label if st.pb.slot >= 0 else f"U{st.pb.number}")
        self.num.setToolTip(f"{st.pb.console_label} – {st.pb.bank}" + (
            f" bank {st.pb.console_bank}, position {st.pb.console_pos}" if st.pb.slot >= 0 else ""))
        nm = st.pb.name
        self.name.setText(nm if len(nm) <= 10 else nm[:9] + "…")
        n = len(st.pb.steps)
        if st.running:
            self.step.setText(f"{'❚❚ ' if st.paused else '▶ '}{st.index + 1}/{n}")
            self.name.setStyleSheet("text-align:center; font-size:8pt; background:#1f4d2e; border-color:#3fbf6a;")
            self.prog.setValue(int(self.engine.step_progress(st) * 1000))
        else:
            self.prog.setValue(0)
            self.step.setText(f"{n} step{'s' if n != 1 else ''}" + (" chase" if st.pb.mode == "chase" and n > 1 else ""))
            self.name.setStyleSheet("text-align:center; font-size:8pt;")
        v = round(st.level * 100)
        if self.slider.value() != v and not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(v)
            self.slider.blockSignals(False)
            self.lvl.setText(f"{v}%")


class FixedKey(QPushButton):
    """One of the 20 fixed playback keys: press = on / off (like the console's number keys)."""

    def __init__(self, engine: Engine, bar: "ExecutorBar", pos: int):
        super().__init__()
        self.engine, self.bar, self.pos = engine, bar, pos
        self.st: PlaybackState | None = None
        self.setMinimumSize(96, 46)
        self.setCheckable(False)
        self.clicked.connect(self._toggle)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def bind(self, st: PlaybackState | None, label: str) -> None:
        self.st, self.label = st, label
        self.setEnabled(st is not None)
        self.sync()

    def _toggle(self):
        st = self.st
        if not st:
            return
        if st.running:
            self.engine.stop(st, fade=True)
            st.level = 0.0
        else:
            self.engine.go(st)
            self.bar.playbackTriggered.emit(st)
        self.sync()

    def _menu(self, pos):
        if not self.st:
            return
        m = QMenu(self)
        m.addAction("Edit cues…", lambda: self.bar.playbackSelected.emit(self.st))
        m.addAction("GO (next cue)", lambda: self.engine.go(self.st))
        m.addAction("Stop immediately", lambda: (self.engine.stop(self.st), setattr(self.st, "level", 0.0)))
        m.exec(self.mapToGlobal(pos))

    def sync(self):
        st = self.st
        if st is None:
            self.setText(f"{self.pos}\n—")
            self.setStyleSheet("color:#5a5e6c;")
            self.setToolTip(f"{self.label}: empty")
            return
        nm = st.pb.name if len(st.pb.name) <= 13 else st.pb.name[:12] + "…"
        n = len(st.pb.steps)
        state = f"▶ {st.index + 1}/{n}" if st.running else f"{n} cue{'s' if n != 1 else ''}"
        self.setText(f"{self.pos}  {nm}\n{state}")
        self.setToolTip(f"{st.pb.console_label}  {st.pb.name}\nClick = on / off, right-click = more")
        self.setStyleSheet("background:#1f4d2e; border-color:#3fbf6a; font-weight:600;" if st.running
                           else "background:#2a2f14; border-color:#5d6a1f;" if n else "")


class ExecutorBar(QWidget):
    playbackSelected = Signal(object)
    playbackTriggered = Signal(object)

    MODES = ["Playback", "Fixed", "User", "All"]
    LABELS = {"Playback": "Playback banks (40 × 15)", "Fixed": "Fixed banks (20 × 20)",
              "User": "User (made here)", "All": "All, in order"}

    def __init__(self, engine: Engine, per_page: int = PB_PER_BANK, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.per_page = per_page
        self.page = 0
        self.filter = "Playback"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        side = QVBoxLayout()
        t = QLabel("Playbacks")
        t.setObjectName("title")
        side.addWidget(t)
        self.bank = QComboBox()
        for m in self.MODES:
            self.bank.addItem(self.LABELS[m], m)
        self.bank.setToolTip("Playback banks: 40 banks of 15 faders (console P1/1 … P40/15)\n"
                             "Fixed banks: 20 banks of 20 keys (console Fixed key + 1 … 20)")
        self.bank.currentIndexChanged.connect(lambda _i: self._bank(self.bank.currentData()))
        side.addWidget(self.bank)
        self.per_label = QLabel("Bank")
        side.addWidget(self.per_label)
        self.spin = QSpinBox()
        self.spin.setRange(1, 1)
        self.spin.valueChanged.connect(self._page)
        side.addWidget(self.spin)
        b_prev, b_next = QPushButton("◀"), QPushButton("▶")
        b_prev.clicked.connect(lambda: self.spin.setValue(self.spin.value() - 1))
        b_next.clicked.connect(lambda: self.spin.setValue(self.spin.value() + 1))
        r = QHBoxLayout()
        r.addWidget(b_prev)
        r.addWidget(b_next)
        side.addLayout(r)
        b_rel = QPushButton("Release all")
        b_rel.setObjectName("danger")
        b_rel.clicked.connect(self._release_all)
        side.addWidget(b_rel)
        lay.addLayout(side)
        side = QVBoxLayout()
        t2 = QLabel("Master")
        t2.setObjectName("title")
        side.addWidget(t2)
        self.sp = QSlider(Qt.Horizontal)
        self.sp.setRange(10, 400)
        self.sp.setValue(100)
        self.sp.setToolTip("Speed master for all chases (100 % = programmed speed)")
        self.sp_lbl = QLabel("Speed 100 %")
        self.sp.valueChanged.connect(self._speed)
        self.fxs = QSlider(Qt.Horizontal)
        self.fxs.setRange(10, 400)
        self.fxs.setValue(100)
        self.fxs.setToolTip("Speed of all effects")
        self.fxs_lbl = QLabel("FX speed 100 %")
        self.fxs.valueChanged.connect(self._fxspeed)
        b_tap = QPushButton("TAP")
        b_tap.setToolTip("Tap the beat: sets the speed master (120 BPM = 100 %)")
        b_tap.clicked.connect(self._tap)
        b_res = QPushButton("Reset")
        b_res.clicked.connect(lambda: (self.sp.setValue(100), self.fxs.setValue(100)))
        for w in (self.sp_lbl, self.sp, self.fxs_lbl, self.fxs):
            side.addWidget(w)
        r2 = QHBoxLayout()
        r2.addWidget(b_tap)
        r2.addWidget(b_res)
        side.addLayout(r2)
        side.addStretch(1)
        lay.addLayout(side)
        # faders (playback banks / user / all)
        self.strip_box = QWidget()
        sl = QHBoxLayout(self.strip_box)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(2)
        self.strips = []
        for _ in range(max(per_page, PB_PER_BANK)):
            s = ExecutorStrip(engine)
            s.selected.connect(self.playbackSelected.emit)
            s.triggered.connect(self.playbackTriggered.emit)
            self.strips.append(s)
            sl.addWidget(s)
        self.strip_layout = sl
        sl.addStretch(1)
        lay.addWidget(self.strip_box, 1)
        # fixed keys 1..20 (2 rows of 10, like the console)
        self.fixed_box = QWidget()
        g = QGridLayout(self.fixed_box)
        g.setContentsMargins(4, 4, 4, 4)
        g.setSpacing(4)
        self.keys = []
        for i in range(FIXED_PER_BANK):
            k = FixedKey(engine, self, i + 1)
            g.addWidget(k, i // 10, i % 10)
            self.keys.append(k)
        lay.addWidget(self.fixed_box, 1)
        self.fixed_box.hide()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync)
        self.timer.start(150)
        self.rebind()

    def _speed(self, v):
        self.engine.speed_master = v / 100
        self.sp_lbl.setText(f"Speed {v} %")

    def _fxspeed(self, v):
        self.engine.fx_speed = v / 100
        self.fxs_lbl.setText(f"FX speed {v} %")

    def _tap(self):
        m = self.engine.tap_master()
        self.sp.blockSignals(True)
        self.sp.setValue(round(m * 100))
        self.sp.blockSignals(False)
        self.sp_lbl.setText(f"Speed {round(m * 100)} %  ({round(m * 120)} BPM)")

    def _release_all(self):
        self.engine.release_all()
        self.sync()

    def _bank(self, mode):
        self.filter = mode or "Playback"
        self.spin.blockSignals(True)
        self.spin.setValue(1)
        self.spin.blockSignals(False)
        self.page = 0
        self.rebind()

    def _page(self, v):
        self.page = v - 1
        self.rebind()

    def visible_states(self) -> list[PlaybackState]:
        f = self.filter
        if f in ("Playback", "Fixed"):
            return sorted((s for s in self.engine.states if s.pb.bank == f and s.pb.slot >= 0),
                          key=lambda s: s.pb.slot)
        sts = sorted(self.engine.states, key=lambda s: s.pb.number)
        if f == "User":
            sts = [s for s in sts if s.pb.slot < 0]
        return sts

    def rebind(self) -> None:
        f = self.filter
        fixed = f == "Fixed"
        self.fixed_box.setVisible(fixed)
        self.strip_box.setVisible(not fixed)
        if f in ("Playback", "Fixed"):
            per = FIXED_PER_BANK if fixed else PB_PER_BANK
            pages = FIXED_BANKS if fixed else PB_BANKS
            by_slot = {s.pb.slot: s for s in self.visible_states()}
        else:
            per = self.per_page
            sts = self.visible_states()
            pages = max(1, (len(sts) + per - 1) // per)
        self.per_label.setText("Fixed page" if fixed else "Bank")
        self.spin.blockSignals(True)
        self.spin.setRange(1, pages)
        self.spin.setSuffix(f" / {pages}")
        self.spin.blockSignals(False)
        self.page = min(self.page, pages - 1)
        b = self.page
        if fixed:
            for i, k in enumerate(self.keys):
                k.bind(by_slot.get(b * per + i), f"F{b + 1}/{i + 1}")
            return
        for i, s in enumerate(self.strips):
            s.setVisible(i < per)
        if f == "Playback":
            for i, s in enumerate(self.strips[:per]):
                s.bind(by_slot.get(b * per + i), f"P{b + 1}/{i + 1}")
        else:
            chunk = sts[b * per:(b + 1) * per]
            for i, s in enumerate(self.strips[:per]):
                s.bind(chunk[i] if i < len(chunk) else None)

    def set_per_page(self, n: int) -> None:
        """Faders per page for the User / All lists (playback banks always have 15)."""
        while len(self.strips) < n:
            s = ExecutorStrip(self.engine)
            s.selected.connect(self.playbackSelected.emit)
            s.triggered.connect(self.playbackTriggered.emit)
            self.strip_layout.insertWidget(self.strip_layout.count() - 1, s)
            self.strips.append(s)
        while len(self.strips) > max(n, PB_PER_BANK):
            s = self.strips.pop()
            s.setParent(None)
            s.deleteLater()
        self.per_page = n
        self.rebind()

    def bank_step(self, d: int) -> None:
        self.spin.setValue(max(1, min(self.spin.maximum(), self.spin.value() + d)))

    def show_playback(self, st: PlaybackState) -> None:
        pb = st.pb
        if pb.slot >= 0:
            mode = pb.bank if pb.bank in ("Playback", "Fixed") else "All"
        else:
            mode = "User"
        if mode != self.filter:
            self.bank.setCurrentIndex(self.MODES.index(mode))
        if mode in ("Playback", "Fixed"):
            self.spin.setValue(pb.console_bank)
        else:
            sts = self.visible_states()
            if st in sts:
                self.spin.setValue(sts.index(st) // self.per_page + 1)

    def sync(self) -> None:
        if self.filter == "Fixed":
            for k in self.keys:
                k.sync()
        else:
            for s in self.strips:
                if s.isVisible():
                    s.sync()
