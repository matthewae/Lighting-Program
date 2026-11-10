"""Effect engine panel: shape library (position / intensity / colour / beam) + parameters."""
from __future__ import annotations

import colorsys
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTabWidget,
                               QToolButton, QVBoxLayout, QWidget)

from ..effects import intensity_value, shape_xy
from ..engine import Engine
from ..model import EFFECT_TYPES, Effect

PRESETS = {
    "circle": dict(speed=0.5, size=40, spread=360), "ellipse": dict(speed=0.5, size=50, spread=360),
    "diamond": dict(speed=0.4, size=40, spread=360), "square": dict(speed=0.35, size=40, spread=360),
    "triangle": dict(speed=0.4, size=40, spread=360), "figure8": dict(speed=0.4, size=40, spread=180),
    "s_shape": dict(speed=0.25, size=45, spread=180), "cross": dict(speed=0.3, size=45, spread=0),
    "star": dict(speed=0.25, size=45, spread=360), "spiral": dict(speed=0.12, size=50, spread=360),
    "pan_saw": dict(speed=0.5, size=50, spread=360), "tilt_saw": dict(speed=0.5, size=40, spread=360),
    "pan_wave": dict(speed=0.5, size=50, spread=180), "tilt_wave": dict(speed=0.5, size=40, spread=360),
    "pan_swing": dict(speed=0.4, size=50, spread=180), "tilt_swing": dict(speed=0.4, size=40, spread=180),
    "pan_step": dict(speed=1.0, size=40, spread=180, duty=0.5), "tilt_step": dict(speed=1.0, size=40, spread=180),
    "ballyhoo": dict(speed=0.3, size=60, spread=360), "pos_random": dict(speed=0.5, size=50, spread=360),
    "dim_sine": dict(speed=0.5, spread=360), "dim_saw": dict(speed=1.0, spread=360),
    "dim_pulse": dict(speed=1.0, spread=360), "dim_triangle": dict(speed=0.7, spread=360),
    "dim_chase": dict(speed=1.0, spread=360, duty=0.5), "dim_fade": dict(speed=0.8, spread=360, duty=0.4),
    "dim_random": dict(speed=2.0, spread=0), "sparkle": dict(speed=2.0, spread=0, duty=0.5),
    "strobe": dict(speed=8.0, spread=0, duty=0.5), "strobe_random": dict(speed=8.0, spread=0, duty=0.5),
    "rainbow": dict(speed=0.2, spread=360), "color_chase": dict(speed=1.0, spread=360, duty=0.5),
    "color_fade": dict(speed=0.3, spread=360), "rgb_step": dict(speed=0.5, spread=360),
    "color_random": dict(speed=1.0, spread=0),
    "gobo_step": dict(speed=0.5, spread=0), "zoom_wave": dict(speed=0.3, spread=360),
    "focus_wave": dict(speed=0.3, spread=360), "iris_wave": dict(speed=0.3, spread=360),
    "prism_flash": dict(speed=0.5, spread=0, duty=0.5), "frost_wave": dict(speed=0.3, spread=360),
    "infinity": dict(speed=0.3, size=45, spread=360), "heart": dict(speed=0.25, size=45, spread=0),
    "rose": dict(speed=0.15, size=50, spread=360), "lissajous": dict(speed=0.2, size=45, spread=360),
    "zigzag": dict(speed=0.2, size=45, spread=180), "fan": dict(speed=0.3, size=60, spread=0),
    "pendulum": dict(speed=0.4, size=50, spread=90), "nod": dict(speed=0.6, size=40, spread=360),
    "sweep": dict(speed=0.25, size=50, spread=180), "jump": dict(speed=0.5, size=50, spread=0),
    "breathe": dict(speed=0.2, spread=180), "heartbeat": dict(speed=1.1, spread=0),
    "flash_decay": dict(speed=1.0, spread=360), "bounce": dict(speed=0.5, spread=0, duty=0.5),
    "scanner": dict(speed=0.4, spread=0, duty=0.5), "build": dict(speed=0.3, spread=0),
    "lightning": dict(speed=1.0, spread=0), "flicker": dict(speed=1.0, spread=0), "candle": dict(speed=1.0, spread=0),
    "odd_even": dict(speed=1.0, spread=0), "color_wave": dict(speed=0.3, spread=360),
    "color3": dict(speed=0.6, spread=360), "fire": dict(speed=1.0, spread=0), "ocean": dict(speed=0.15, spread=360),
    "police": dict(speed=1.0, spread=180), "pastel": dict(speed=0.15, spread=360),
    "color_strobe": dict(speed=6.0, spread=0, duty=0.5), "zoom_bump": dict(speed=1.0, spread=360),
    "iris_pulse": dict(speed=1.0, spread=360), "gobo_shake": dict(speed=1.0, spread=0),
    "prism_spin": dict(speed=0.5, spread=0),
}
SHORT = {"dim_sine": "Sine", "dim_saw": "Saw ↑", "dim_pulse": "Ramp ↓", "dim_triangle": "Triangle",
         "dim_chase": "Chase / step", "dim_fade": "Soft chase", "dim_random": "Random", "strobe_random": "Rnd strobe",
         "pan_wave": "Pan sine", "tilt_wave": "Tilt sine", "pan_swing": "Pan swing", "tilt_swing": "Tilt swing",
         "pos_random": "Random", "color_chase": "Chase A/B", "color_fade": "Fade A↔B", "rgb_step": "RGB step",
         "color_random": "Random", "prism_flash": "Prism on/off", "rose": "Flower", "lissajous": "Lissajous",
         "sweep": "Sweep", "jump": "Jump", "flash_decay": "Flash decay", "scanner": "Scanner",
         "flicker": "Fire flicker", "odd_even": "Odd/Even", "bounce": "Bounce", "color_wave": "Hue wave", "color3": "3 colours",
         "pastel": "Pastel", "color_strobe": "Colour flash", "infinity": "Infinity ∞", "fan": "Fan"}
ORDERS = [("forward", "→ Forward"), ("backward", "← Backward"), ("center_out", "↔ Centre out"),
          ("outside_in", "→← Outside in"), ("odd_even", "Odd / even"), ("random", "Random")]
CATS = [("Position", "Position"), ("Intensity", "Intensity"), ("Color", "Colour"), ("Beam", "Beam")]


def shape_icon(kind: str, feature: str, size: int = 46) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    m = 6
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    p.setPen(QPen(QColor(60, 64, 80), 1))
    p.setBrush(QColor(22, 24, 32))
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 6, 6)
    path = QPainterPath()
    accent = QColor(255, 196, 64)
    if feature == "Position" and kind == "fan":
        c = QPointF(r.center().x(), r.bottom())
        for k in range(-3, 4):
            path.moveTo(c)
            path.lineTo(QPointF(c.x() + k * r.width() / 7, r.top()))
    elif feature == "Position":
        for i in range(97):
            x, y = shape_xy(kind, i / 96, 3, i / 96 * 3)
            pt = QPointF(r.center().x() + x * r.width() / 2, r.center().y() - y * r.height() / 2)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
    elif feature == "Intensity" and kind in ("bounce", "scanner", "odd_even", "build"):
        p.setPen(Qt.NoPen)
        lit = {"bounce": [0, 0, 1, 0, 0], "scanner": [0, 0.3, 0.7, 1, 0.4], "odd_even": [1, 0, 1, 0, 1],
               "build": [1, 0, 1, 1, 0]}[kind]
        for i, v in enumerate(lit):
            p.setBrush(QColor(int(60 + 195 * v), int(60 + 136 * v), int(60 + 4 * v)))
            p.drawEllipse(QPointF(r.left() + r.width() * (i + 0.5) / 5, r.center().y()), 4, 4)
        p.end()
        return QIcon(pm)
    elif feature == "Intensity":
        for i in range(97):
            v = intensity_value(kind, (i / 96 * 2) % 1.0, 0.5, 3, i / 96 * 2, 1)
            pt = QPointF(r.left() + r.width() * i / 96, r.bottom() - v * r.height())
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
    elif feature == "Color":
        p.setPen(Qt.NoPen)
        n = 12
        for i in range(n):
            if kind == "rainbow":
                c = QColor(*[int(x * 255) for x in colorsys.hsv_to_rgb(i / n, 1, 1)])
            elif kind == "rgb_step":
                c = QColor(*[(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)][i * 4 // n])
            elif kind == "color_random":
                c = QColor(*[(255, 0, 0), (0, 230, 255), (255, 230, 0), (160, 0, 255)][(i * 7) % 4])
            elif kind == "color_fade":
                k = i / (n - 1)
                c = QColor(int(255 * (1 - k)), 0, int(255 * k))
            elif kind in ("fire", "ocean", "pastel", "color_wave"):
                h, sat = {"fire": (0.02 + 0.09 * (i % 4) / 3, 1), "ocean": (0.5 + 0.16 * i / n, 1),
                          "pastel": (i / n, 0.4), "color_wave": (0.9 + 0.2 * i / n, 1)}[kind]
                c = QColor(*[int(x * 255) for x in colorsys.hsv_to_rgb(h % 1.0, sat, 1)])
            elif kind == "police":
                c = QColor(255, 0, 0) if i < n // 2 else QColor(0, 40, 255)
            elif kind == "color3":
                c = QColor(*[(255, 0, 0), (0, 255, 0), (0, 0, 255)][i * 3 // n])
            elif kind == "color_strobe":
                c = QColor(255, 255, 255) if i % 3 == 0 else QColor(255, 0, 0)
            else:
                c = QColor(255, 0, 0) if i < n // 2 else QColor(0, 0, 255)
            p.setBrush(c)
            p.drawRect(QRectF(r.left() + r.width() * i / n, r.top() + r.height() * 0.25, r.width() / n + 0.5,
                              r.height() * 0.5))
        p.end()
        return QIcon(pm)
    else:
        p.setPen(QPen(accent, 2))
        c = r.center()
        if kind == "gobo_step":
            for k in range(5):
                a = 2 * math.pi * k / 5
                p.drawEllipse(QPointF(c.x() + math.cos(a) * 10, c.y() + math.sin(a) * 10), 3, 3)
        elif kind == "prism_flash":
            for k in range(3):
                a = 2 * math.pi * k / 3
                p.drawEllipse(QPointF(c.x() + math.cos(a) * 8, c.y() + math.sin(a) * 8), 6, 6)
        else:
            for k, rad in enumerate((6, 11, 16)):
                p.setPen(QPen(QColor(255, 196, 64, 255 - k * 70), 2))
                p.drawEllipse(c, rad, rad)
        p.end()
        return QIcon(pm)
    p.setPen(QPen(accent, 2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


class EffectsPanel(QWidget):
    changed = Signal()
    storeRequested = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.col_a, self.col_b = (255, 0, 0), (0, 0, 255)
        self.kind = "circle"
        self.buttons: dict[str, QToolButton] = {}
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # --- left: library -------------------------------------------------
        left = QVBoxLayout()
        hint = QLabel("1. Select fixtures   2. Click a shape   3. Adjust the parameters   "
                      "4. <b>Store…</b> to put it into a cue")
        hint.setWordWrap(True)
        left.addWidget(hint)
        self.cat_tabs = QTabWidget()
        self.cat_tabs.setStyleSheet("QTabBar::tab { padding: 6px 10px; margin: 2px 1px 0 1px; }")
        self._grids = []
        self._cols = 0
        for feat, label in CATS:
            w = QWidget()
            g = QGridLayout(w)
            g.setSpacing(6)
            g.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            keys = [k for k, (_, f) in EFFECT_TYPES.items() if f == feat]
            for i, k in enumerate(keys):
                b = QToolButton()
                b.setText(SHORT.get(k, EFFECT_TYPES[k][0]))
                b.setIcon(shape_icon(k, feat))
                b.setIconSize(QSize(46, 46))
                b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                b.setCheckable(True)
                b.setFixedSize(100, 80)
                b.setToolTip(f"{EFFECT_TYPES[k][0]} – click to choose, double-click to start on the selection")
                b.clicked.connect(lambda _=False, key=k: self.choose(key))
                b.mouseDoubleClickEvent = lambda e, key=k: (self.choose(key), self.start())
                g.addWidget(b, i // 5, i % 5)
                self.buttons[k] = b
            self._grids.append((g, [self.buttons[k] for k in keys]))
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setWidget(w)
            self.cat_tabs.addTab(sc, label)
        left.addWidget(self.cat_tabs, 1)
        bl = QHBoxLayout()
        b_start = QPushButton("▶  Start on selection")
        b_start.setObjectName("go")
        b_start.clicked.connect(self.start)
        b_store = QPushButton("💾  Store…")
        b_store.clicked.connect(self.storeRequested.emit)
        bl.addWidget(b_start, 2)
        bl.addWidget(b_store, 1)
        left.addLayout(bl)
        lw = QWidget()
        lw.setLayout(left)
        root.addWidget(lw, 5)

        # --- right: parameters + running effects ---------------------------
        right = QVBoxLayout()
        self.title = QLabel("Circle")
        self.title.setObjectName("title")
        right.addWidget(self.title)
        g = QGroupBox("Parameters")
        f = QFormLayout(g)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.01, 30)
        self.speed.setDecimals(2)
        self.speed.setSuffix(" Hz")
        self.bpm = QSpinBox()
        self.bpm.setRange(1, 1800)
        self.bpm.setSuffix(" BPM")
        self.speed.valueChanged.connect(lambda v: (self.bpm.blockSignals(True), self.bpm.setValue(round(v * 60)),
                                                   self.bpm.blockSignals(False)))
        self.bpm.valueChanged.connect(lambda v: self.speed.setValue(v / 60))
        r = QHBoxLayout()
        r.addWidget(self.speed)
        r.addWidget(self.bpm)
        f.addRow("Speed", r)
        self.size = QSpinBox()
        self.size.setRange(1, 127)
        self.size.setToolTip("Position: amplitude in DMX steps around the current pan / tilt")
        f.addRow("Size", self.size)
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
        f.addRow("Range", lr)
        self.spread = QSpinBox()
        self.spread.setRange(0, 1440)
        self.spread.setSuffix(" °")
        self.spread.setToolTip("Phase spread over the fixtures: 0 = all together, 360 = one full wave")
        f.addRow("Spread", self.spread)
        self.offset = QSpinBox()
        self.offset.setRange(0, 359)
        self.offset.setSuffix(" °")
        f.addRow("Offset", self.offset)
        self.wings = QSpinBox()
        self.wings.setRange(1, 8)
        self.wings.setToolTip("Mirror groups (2 = symmetric from the centre)")
        f.addRow("Wings", self.wings)
        self.order = QComboBox()
        for k, label in ORDERS:
            self.order.addItem(label, k)
        self.order.setToolTip("In which order the fixtures follow each other")
        f.addRow("Order", self.order)
        self.blocks = QSpinBox()
        self.blocks.setRange(1, 32)
        self.blocks.setToolTip("Number of neighbouring fixtures that move together")
        f.addRow("Blocks", self.blocks)
        self.duty = QDoubleSpinBox()
        self.duty.setRange(0.05, 0.95)
        self.duty.setSingleStep(0.05)
        self.duty.setValue(0.5)
        self.duty.setToolTip("On-time for step / chase / strobe shapes")
        f.addRow("Duty", self.duty)
        self.fade = QDoubleSpinBox()
        self.fade.setRange(0, 60)
        self.fade.setSuffix(" s")
        f.addRow("Fade in", self.fade)
        self.reverse = QCheckBox("Reverse direction")
        f.addRow("", self.reverse)
        cr = QHBoxLayout()
        self.b_a, self.b_b, self.b_c = QPushButton("A"), QPushButton("B"), QPushButton("C")
        self.col_c = (0, 255, 0)
        for b, k in ((self.b_a, "a"), (self.b_b, "b"), (self.b_c, "c")):
            b.clicked.connect(lambda _=False, kk=k: self._pick(kk))
            cr.addWidget(b)
        f.addRow("Colours", cr)
        right.addWidget(g)
        br = QHBoxLayout()
        for txt, fn, obj in (("Apply to running", self.update_selected, ""), ("Stop", self.stop_selected, ""),
                             ("Stop all", self.stop_all, "danger")):
            b = QPushButton(txt)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            br.addWidget(b)
        right.addLayout(br)
        right.addWidget(QLabel("Running effects (programmer)"))
        self.list = QListWidget()
        self.list.setMinimumHeight(90)
        self.list.currentRowChanged.connect(self._load_selected)
        right.addWidget(self.list, 1)
        rw = QWidget()
        rw.setLayout(right)
        rw.setMinimumWidth(270)
        rw.setMaximumWidth(380)
        rw.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        root.addWidget(rw, 2)
        self._colours()
        self.choose("circle")

    # ------------------------------------------------------------------ ui
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        w = self.cat_tabs.width() - 24
        cols = max(2, w // 106)
        if cols == self._cols:
            return
        self._cols = cols
        for g, btns in self._grids:
            for b in btns:
                g.removeWidget(b)
            for i, b in enumerate(btns):
                g.addWidget(b, i // cols, i % cols)

    def _colours(self):
        for b, c in ((self.b_a, self.col_a), (self.b_b, self.col_b), (self.b_c, self.col_c)):
            txt = "#111" if sum(c) > 380 else "#fff"
            b.setStyleSheet(f"background: rgb{tuple(c)}; color: {txt};")

    def _pick(self, which):
        cur = {"a": self.col_a, "b": self.col_b, "c": self.col_c}[which]
        c = QColorDialog.getColor(QColor(*cur), self)
        if c.isValid():
            setattr(self, f"col_{which}", (c.red(), c.green(), c.blue()))
            self._colours()

    def choose(self, kind: str) -> None:
        self.kind = kind
        for k, b in self.buttons.items():
            b.setChecked(k == kind)
        label, feat = EFFECT_TYPES[kind]
        self.title.setText(f"{label}   ·   {feat}")
        pr = PRESETS.get(kind, {})
        self.speed.setValue(pr.get("speed", 0.5))
        self.size.setValue(pr.get("size", 40))
        self.spread.setValue(pr.get("spread", 360))
        self.duty.setValue(pr.get("duty", 0.5))
        if feat == "Beam" and kind != "gobo_step" and kind != "prism_flash":
            self.low.setValue(0)
            self.high.setValue(255)
        self.size.setEnabled(feat == "Position")
        self.low.setEnabled(feat in ("Intensity", "Beam"))
        self.high.setEnabled(feat in ("Intensity", "Beam"))
        for b in (self.b_a, self.b_b, self.b_c):
            b.setEnabled(feat == "Color")

    def _make(self, fixtures) -> Effect:
        return Effect(type=self.kind, fixtures=list(fixtures), speed=self.speed.value(), size=self.size.value(),
                      spread=self.spread.value(), wings=self.wings.value(), low=self.low.value(),
                      high=self.high.value(), color_a=self.col_a, color_b=self.col_b,
                      reverse=self.reverse.isChecked(), offset=self.offset.value(), duty=self.duty.value(),
                      fade=self.fade.value(), order=self.order.currentData(), blocks=self.blocks.value(),
                      color_c=self.col_c)

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        for e in self.engine.effects:
            label = EFFECT_TYPES.get(e.type, (e.type, ""))[0]
            self.list.addItem(QListWidgetItem(f"{label}  ·  {len(e.fixtures)} fx  ·  {e.speed * 60:.0f} BPM  ·  "
                                              f"spread {e.spread:g}°  ·  wings {e.wings}"))
        self.list.blockSignals(False)

    def _load_selected(self, row):
        if not (0 <= row < len(self.engine.effects)):
            return
        e = self.engine.effects[row]
        if e.type in self.buttons:
            self.choose(e.type)
            feat = EFFECT_TYPES[e.type][1]
            self.cat_tabs.setCurrentIndex([c for c, _ in CATS].index(feat))
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
        self.order.setCurrentIndex(max(0, self.order.findData(getattr(e, "order", "forward"))))
        self.blocks.setValue(getattr(e, "blocks", 1))
        self.col_a, self.col_b = tuple(e.color_a), tuple(e.color_b)
        self.col_c = tuple(getattr(e, "color_c", (0, 255, 0)))
        self._colours()

    # ------------------------------------------------------------- actions
    def start(self):
        if not self.engine.selection:
            self.title.setText("⚠ Select fixtures first (Fixtures / Groups tab or click in the stage)")
            return
        self.engine.add_effect(self._make(self.engine.selection))
        self.refresh()
        self.list.setCurrentRow(self.list.count() - 1)
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
