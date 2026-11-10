"""Executor / playback fader bar (dot2 executor wing style)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QVBoxLayout,
                               QWidget, QComboBox)

from ..engine import Engine, PlaybackState


class ExecutorStrip(QWidget):
    selected = Signal(object)

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.st: PlaybackState | None = None
        self.setFixedWidth(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.num = QLabel("")
        self.num.setAlignment(Qt.AlignCenter)
        self.name = QPushButton("—")
        self.name.setToolTip("Click to edit this playback in the Cues tab")
        self.name.setStyleSheet("text-align:center; font-size:8pt;")
        self.name.setMinimumHeight(34)
        self.name.clicked.connect(lambda: self.st and self.selected.emit(self.st))
        self.step = QLabel("")
        self.step.setAlignment(Qt.AlignCenter)
        self.step.setStyleSheet("color:#8fd18f; font-size:8pt;")
        self.slider = QSlider(Qt.Vertical)
        self.slider.setRange(0, 100)
        self.slider.setMinimumHeight(110)
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
        for b in (self.b_back, self.b_go, self.b_pause, self.b_stop):
            b.setFixedHeight(24)
        self.b_go.clicked.connect(lambda: self.st and self.engine.go(self.st))
        self.b_back.clicked.connect(lambda: self.st and self.engine.back(self.st))
        self.b_pause.clicked.connect(lambda: self.st and self.engine.pause(self.st))
        self.b_stop.clicked.connect(self._stop)
        self.b_flash.pressed.connect(lambda: self.st and self.engine.set_flash(self.st, True))
        self.b_flash.released.connect(lambda: self.st and self.engine.set_flash(self.st, False))
        for w in (self.num, self.name, self.step):
            lay.addWidget(w)
        lay.addWidget(self.slider, 1, Qt.AlignHCenter)
        lay.addWidget(self.lvl)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addWidget(self.b_flash)

    def _stop(self):
        if self.st:
            self.engine.stop(self.st)
            self.slider.setValue(0)

    def bind(self, st: PlaybackState | None) -> None:
        self.st = st
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
            self.num.setText("")
            self.name.setText("—")
            self.step.setText("")
            self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(False)
            self.lvl.setText("")
            return
        self.num.setText(f"Exec {st.pb.number}")
        nm = st.pb.name
        self.name.setText(nm if len(nm) <= 12 else nm[:11] + "…")
        n = len(st.pb.steps)
        if st.running:
            self.step.setText(f"{'❚❚ ' if st.paused else '▶ '}{st.index + 1}/{n}")
            self.name.setStyleSheet("text-align:center; font-size:8pt; background:#2f5e2f;")
        else:
            self.step.setText(f"{n} step{'s' if n != 1 else ''}" + (" chase" if st.pb.mode == "chase" and n > 1 else ""))
            self.name.setStyleSheet("text-align:center; font-size:8pt;")
        v = round(st.level * 100)
        if self.slider.value() != v and not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(v)
            self.slider.blockSignals(False)
            self.lvl.setText(f"{v}%")


class ExecutorBar(QWidget):
    playbackSelected = Signal(object)

    def __init__(self, engine: Engine, per_page: int = 10, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.per_page = per_page
        self.page = 0
        self.filter = "all"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        side = QVBoxLayout()
        t = QLabel("Executors")
        t.setObjectName("title")
        side.addWidget(t)
        self.bank = QComboBox()
        self.bank.addItems(["All", "With steps", "Fixed", "Playback", "User"])
        self.bank.currentTextChanged.connect(self._bank)
        side.addWidget(self.bank)
        side.addWidget(QLabel("Page"))
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
        side.addStretch(1)
        lay.addLayout(side)
        self.strips = []
        for _ in range(per_page):
            s = ExecutorStrip(engine)
            s.selected.connect(self.playbackSelected.emit)
            self.strips.append(s)
            lay.addWidget(s)
        lay.addStretch(1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync)
        self.timer.start(150)
        self.rebind()

    def _release_all(self):
        self.engine.release_all()
        self.sync()

    def _bank(self, txt):
        self.filter = txt
        self.spin.setValue(1)
        self.rebind()

    def _page(self, v):
        self.page = v - 1
        self.rebind()

    def visible_states(self) -> list[PlaybackState]:
        sts = sorted(self.engine.states, key=lambda s: s.pb.number)
        f = self.filter
        if f == "With steps":
            sts = [s for s in sts if s.pb.steps]
        elif f in ("Fixed", "Playback", "User"):
            sts = [s for s in sts if s.pb.bank == f]
        return sts

    def rebind(self) -> None:
        sts = self.visible_states()
        pages = max(1, (len(sts) + self.per_page - 1) // self.per_page)
        self.spin.blockSignals(True)
        self.spin.setRange(1, pages)
        self.spin.setSuffix(f" / {pages}")
        self.spin.blockSignals(False)
        self.page = min(self.page, pages - 1)
        chunk = sts[self.page * self.per_page:(self.page + 1) * self.per_page]
        for i, s in enumerate(self.strips):
            s.bind(chunk[i] if i < len(chunk) else None)

    def show_playback(self, st: PlaybackState) -> None:
        sts = self.visible_states()
        if st not in sts:
            self.bank.setCurrentText("All")
            sts = self.visible_states()
        if st in sts:
            self.spin.setValue(sts.index(st) // self.per_page + 1)

    def sync(self) -> None:
        for s in self.strips:
            s.sync()
