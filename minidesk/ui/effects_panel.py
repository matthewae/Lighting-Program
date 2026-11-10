"""Effect generator panel (position / intensity / colour effects)."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..engine import Engine
from ..model import EFFECT_TYPES, Effect

PRESETS = {
    "circle": dict(speed=0.5, size=40, spread=360),
    "figure8": dict(speed=0.4, size=40, spread=180),
    "pan_wave": dict(speed=0.5, size=50, spread=180),
    "tilt_wave": dict(speed=0.5, size=40, spread=360),
    "ballyhoo": dict(speed=0.3, size=60, spread=360),
    "dim_sine": dict(speed=0.5, spread=360),
    "dim_pulse": dict(speed=1.0, spread=360),
    "dim_chase": dict(speed=1.0, spread=360, duty=0.5),
    "dim_random": dict(speed=2.0, spread=0),
    "strobe": dict(speed=8.0, spread=0, duty=0.5),
    "rainbow": dict(speed=0.2, spread=360),
    "color_chase": dict(speed=1.0, spread=360, duty=0.5),
}


class EffectsPanel(QWidget):
    changed = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.col_a, self.col_b = (255, 0, 0), (0, 0, 255)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        hint = QLabel("Select fixtures, choose an effect, press <b>Start</b>. Running effects are part of the "
                      "programmer – press <b>Store…</b> to save them into a cue.")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        g = QGroupBox("Effect")
        f = QFormLayout(g)
        self.type = QComboBox()
        for feat in ("Position", "Intensity", "Color"):
            for k, (label, ft) in EFFECT_TYPES.items():
                if ft == feat:
                    self.type.addItem(f"{feat}: {label}", k)
        self.type.currentIndexChanged.connect(self._preset)
        f.addRow("Type", self.type)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.01, 30)
        self.speed.setDecimals(2)
        self.speed.setSuffix(" Hz")
        self.speed.setToolTip("Cycles per second (BPM = Hz × 60)")
        self.bpm = QLabel()
        self.speed.valueChanged.connect(lambda v: self.bpm.setText(f"= {v * 60:.0f} BPM"))
        r = QHBoxLayout()
        r.addWidget(self.speed)
        r.addWidget(self.bpm)
        f.addRow("Speed", r)
        self.size = QSpinBox()
        self.size.setRange(1, 127)
        self.size.setToolTip("Position effects: amplitude in DMX steps around the current pan/tilt")
        f.addRow("Size (position)", self.size)
        lr = QHBoxLayout()
        self.low = QSpinBox()
        self.low.setRange(0, 255)
        self.high = QSpinBox()
        self.high.setRange(0, 255)
        self.high.setValue(255)
        lr.addWidget(QLabel("Low"))
        lr.addWidget(self.low)
        lr.addWidget(QLabel("High"))
        lr.addWidget(self.high)
        f.addRow("Intensity range", lr)
        self.spread = QSpinBox()
        self.spread.setRange(0, 1440)
        self.spread.setSuffix(" °")
        self.spread.setToolTip("Phase spread across the fixtures: 0 = all together, 360 = one full wave")
        f.addRow("Phase spread", self.spread)
        self.offset = QSpinBox()
        self.offset.setRange(0, 359)
        self.offset.setSuffix(" °")
        f.addRow("Phase offset", self.offset)
        self.wings = QSpinBox()
        self.wings.setRange(1, 8)
        self.wings.setToolTip("Split the selection into mirrored parts (2 = symmetric from the centre)")
        f.addRow("Wings", self.wings)
        self.duty = QDoubleSpinBox()
        self.duty.setRange(0.05, 0.95)
        self.duty.setSingleStep(0.05)
        self.duty.setValue(0.5)
        f.addRow("Duty (chase/strobe)", self.duty)
        self.fade = QDoubleSpinBox()
        self.fade.setRange(0, 60)
        self.fade.setSuffix(" s")
        self.fade.setToolTip("Time to fade the effect in when it starts / when the cue is played")
        f.addRow("Effect fade-in", self.fade)
        self.reverse = QCheckBox("Reverse direction")
        f.addRow("", self.reverse)
        cr = QHBoxLayout()
        self.b_a, self.b_b = QPushButton("Colour A"), QPushButton("Colour B")
        self.b_a.clicked.connect(lambda: self._pick("a"))
        self.b_b.clicked.connect(lambda: self._pick("b"))
        cr.addWidget(self.b_a)
        cr.addWidget(self.b_b)
        f.addRow("Colour chase", cr)
        lay.addWidget(g)

        br = QHBoxLayout()
        b_start = QPushButton("▶ Start on selection")
        b_start.setObjectName("go")
        b_start.clicked.connect(self.start)
        b_upd = QPushButton("Apply to selected effect")
        b_upd.clicked.connect(self.update_selected)
        b_stop = QPushButton("Stop selected")
        b_stop.clicked.connect(self.stop_selected)
        b_all = QPushButton("Stop all")
        b_all.setObjectName("danger")
        b_all.clicked.connect(self.stop_all)
        for b in (b_start, b_upd, b_stop, b_all):
            br.addWidget(b)
        lay.addLayout(br)
        lay.addWidget(QLabel("Running programmer effects"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load_selected)
        lay.addWidget(self.list, 1)
        self._colours()
        self._preset()

    # ------------------------------------------------------------------ ui
    def _colours(self):
        self.b_a.setStyleSheet(f"background: rgb{self.col_a};")
        self.b_b.setStyleSheet(f"background: rgb{self.col_b};")

    def _pick(self, which):
        cur = self.col_a if which == "a" else self.col_b
        c = QColorDialog.getColor(QColor(*cur), self)
        if c.isValid():
            rgb = (c.red(), c.green(), c.blue())
            if which == "a":
                self.col_a = rgb
            else:
                self.col_b = rgb
            self._colours()

    def _preset(self, *_):
        k = self.type.currentData()
        pr = PRESETS.get(k, {})
        self.speed.setValue(pr.get("speed", 0.5))
        self.size.setValue(pr.get("size", 40))
        self.spread.setValue(pr.get("spread", 360))
        self.duty.setValue(pr.get("duty", 0.5))

    def _make(self, fixtures) -> Effect:
        return Effect(type=self.type.currentData(), fixtures=list(fixtures), speed=self.speed.value(),
                      size=self.size.value(), spread=self.spread.value(), wings=self.wings.value(),
                      low=self.low.value(), high=self.high.value(), color_a=self.col_a,
                      color_b=self.col_b, reverse=self.reverse.isChecked(), offset=self.offset.value(),
                      duty=self.duty.value(), fade=self.fade.value())

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        for e in self.engine.effects:
            label = EFFECT_TYPES.get(e.type, (e.type, ""))[0]
            it = QListWidgetItem(f"{label}  –  {len(e.fixtures)} fixtures  {e.speed:g} Hz  "
                                 f"spread {e.spread:g}°  wings {e.wings}")
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _load_selected(self, row):
        if not (0 <= row < len(self.engine.effects)):
            return
        e = self.engine.effects[row]
        i = self.type.findData(e.type)
        self.type.blockSignals(True)
        self.type.setCurrentIndex(i)
        self.type.blockSignals(False)
        self.speed.setValue(e.speed)
        self.size.setValue(int(e.size))
        self.spread.setValue(int(e.spread))
        self.offset.setValue(int(e.offset))
        self.wings.setValue(e.wings)
        self.low.setValue(e.low)
        self.high.setValue(e.high)
        self.duty.setValue(e.duty)
        self.fade.setValue(e.fade)
        self.reverse.setChecked(e.reverse)
        self.col_a, self.col_b = tuple(e.color_a), tuple(e.color_b)
        self._colours()

    # ------------------------------------------------------------- actions
    def start(self):
        if not self.engine.selection:
            self.list.addItem("⚠ select fixtures first")
            return
        self.engine.add_effect(self._make(self.engine.selection))
        self.refresh()
        self.changed.emit()

    def update_selected(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.engine.effects):
            old = self.engine.effects[row]
            new = self._make(old.fixtures)
            with self.engine.lock:
                self.engine.effects[row] = new
                self.engine._eff_start[id(new)] = self.engine.clock
            self.refresh()
            self.list.setCurrentRow(row)
            self.changed.emit()

    def stop_selected(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.engine.effects):
            self.engine.remove_effect(self.engine.effects[row])
            self.refresh()
            self.changed.emit()

    def stop_all(self):
        with self.engine.lock:
            self.engine.effects.clear()
        self.refresh()
        self.changed.emit()
