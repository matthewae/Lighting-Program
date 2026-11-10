"""Programmer: attribute faders, colour picker and pan/tilt pad for the selection."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QColorDialog, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QTabWidget, QVBoxLayout,
                               QWidget)

from ..attributes import FEATURE_OF, FEATURES, WHEEL_COLOURS
from ..engine import Engine
from .effects_panel import EffectsPanel

QUICK_COLOURS = [
    ("Red", (255, 0, 0)), ("Orange", (255, 110, 0)), ("Yellow", (255, 220, 0)),
    ("Green", (0, 255, 0)), ("Cyan", (0, 255, 255)), ("Blue", (0, 0, 255)),
    ("Purple", (140, 0, 255)), ("Magenta", (255, 0, 200)), ("White", (255, 255, 255)),
    ("Warm", (255, 190, 120)),
]


class XYPad(QWidget):
    moved = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(170, 170)
        self.x, self.y = 128, 128

    def set_pos(self, x: int, y: int) -> None:
        self.x, self.y = x, y
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        p.fillRect(r, QColor(12, 13, 18))
        p.setPen(QPen(QColor(50, 52, 64), 1))
        for i in range(1, 4):
            p.drawLine(r.left() + r.width() * i // 4, r.top(), r.left() + r.width() * i // 4, r.bottom())
            p.drawLine(r.left(), r.top() + r.height() * i // 4, r.right(), r.top() + r.height() * i // 4)
        pt = QPointF(r.left() + self.x / 255 * r.width(), r.top() + (255 - self.y) / 255 * r.height())
        p.setPen(QPen(QColor(255, 200, 0), 2))
        p.drawEllipse(pt, 7, 7)
        p.setPen(QColor(120, 120, 140))
        p.drawText(r.adjusted(4, 2, 0, 0), Qt.AlignLeft | Qt.AlignTop, f"Pan {self.x}  Tilt {self.y}")

    def _set(self, pos):
        r = self.rect().adjusted(2, 2, -2, -2)
        x = int(max(0, min(255, (pos.x() - r.left()) / max(1, r.width()) * 255)))
        y = int(max(0, min(255, 255 - (pos.y() - r.top()) / max(1, r.height()) * 255)))
        self.set_pos(x, y)
        self.moved.emit(x, y)

    def mousePressEvent(self, e):
        self._set(e.position())

    def mouseMoveEvent(self, e):
        self._set(e.position())


class ChannelRow(QWidget):
    changed = Signal(str, int)
    released = Signal(str)

    def __init__(self, name: str, attr: str, value: int, active: bool, functions=None, parent=None):
        super().__init__(parent)
        self.name = name
        self.functions = functions or []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        self.lbl = QLabel(f"{name}")
        self.lbl.setMinimumWidth(110)
        self.lbl.setToolTip(attr)
        self.func = QComboBox()
        self.func.setMinimumWidth(150)
        self.func.setToolTip("Channel function – choose to jump to that DMX range")
        if self.functions:
            for lo, hi, label in self.functions:
                self.func.addItem(f"{label}  ({lo}–{hi})", (lo + hi) // 2 if hi - lo < 40 else lo + (hi - lo) // 4)
            self.func.activated.connect(lambda i: self.spin.setValue(self.func.itemData(i)))
        else:
            self.func.setVisible(False)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 255)
        self.spin = QSpinBox()
        self.spin.setRange(0, 255)
        self.btn = QPushButton("×")
        self.btn.setFixedWidth(26)
        self.btn.setToolTip("Release this attribute from the programmer")
        for w in (self.lbl, self.func, self.slider, self.spin, self.btn):
            lay.addWidget(w)
        lay.setStretch(2, 1)
        self.set_value(value, active)
        self.slider.valueChanged.connect(self._slider)
        self.spin.valueChanged.connect(self._spin)
        self.btn.clicked.connect(lambda: self.released.emit(self.name))

    def _sync_func(self, v: int) -> None:
        for i, (lo, hi, _l) in enumerate(self.functions):
            if lo <= v <= hi:
                self.func.blockSignals(True)
                self.func.setCurrentIndex(i)
                self.func.blockSignals(False)
                return

    def set_value(self, v: int, active: bool) -> None:
        for w in (self.slider, self.spin):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self._sync_func(v)
        self.lbl.setStyleSheet("color:#ff6060;" if active else "")

    def _slider(self, v):
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self._sync_func(v)
        self.lbl.setStyleSheet("color:#ff6060;")
        self.changed.emit(self.name, v)

    def _spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self._sync_func(v)
        self.lbl.setStyleSheet("color:#ff6060;")
        self.changed.emit(self.name, v)


class BeamQuick(QGroupBox):
    """Big buttons for the usual moving-head beam functions."""
    applied = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__("Beam quick (moving heads)", parent)
        self.engine = engine
        g = QGridLayout(self)
        rows = [
            ("Gobo", "gobo", [("Open", "open"), *[(str(i), f"gobo {i}") for i in range(1, 9)], ("Shake", "shake")]),
            ("Gobo rot", "gobo_rot", [("Stop", "index"), ("⟳ CW", "rotate cw"), ("⟲ CCW", "rotate ccw")]),
            ("Prism", "prism", [("Off", "off"), ("On", "prism on"), ("Macro", "macro")]),
            ("Prism rot", "prism_rot", [("Stop", "index"), ("⟳ CW", "rotate cw"), ("⟲ CCW", "rotate ccw")]),
            ("Frost", "frost", [("Off", 0), ("50%", 132), ("100%", 255)]),
            ("Zoom", "zoom", [("Narrow", 0), ("Mid", 128), ("Wide", 255)]),
            ("Focus", "focus", [("Near", 0), ("Mid", 128), ("Far", 255)]),
            ("Iris", "iris", [("Open", 0), ("Half", 128), ("Small", 230)]),
            ("Shutter", "shutter", [("Open", "open"), ("Strobe", "strobe"), ("Closed", "closed")]),
            ("Lamp/Reset", "control", [("Lamp on", "lamp"), ("Reset", "reset")]),
        ]
        for r, (label, attr, btns) in enumerate(rows):
            g.addWidget(QLabel(label), r, 0)
            for c, (txt, what) in enumerate(btns):
                b = QPushButton(txt)
                b.setMinimumWidth(42)
                b.clicked.connect(lambda _=False, a=attr, w=what: self.apply(a, w))
                g.addWidget(b, r, c + 1)

    def apply(self, attr: str, what) -> None:
        show = self.engine.show
        for fid in self.engine.selection:
            fx = show.fixture(fid)
            if not fx:
                continue
            ft = show.types[fx.type_key]
            for ch in ft.channels:
                if ch.attr != attr:
                    continue
                if isinstance(what, int):
                    v = what
                else:
                    v = None
                    for lo, hi, lab in ch.functions(ft.is_moving):
                        if what in lab.lower():
                            v = lo if what in ("rotate cw", "rotate ccw", "strobe") else (lo + hi) // 2
                            if what in ("rotate cw", "rotate ccw"):
                                v = lo + (hi - lo) // 3
                            break
                    if v is None:
                        continue
                self.engine.set_attr(ch.name, v, [fid], by_name=True)
        self.applied.emit()


class ProgrammerPanel(QWidget):
    storeRequested = Signal()
    programmerChanged = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.rows: dict[str, ChannelRow] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.info = QLabel("No fixtures selected")
        self.info.setObjectName("title")
        lay.addWidget(self.info)

        top = QHBoxLayout()
        # intensity
        gi = QGroupBox("Intensity")
        gl = QGridLayout(gi)
        for i, pct in enumerate((0, 10, 25, 50, 75, 100)):
            b = QPushButton("Full" if pct == 100 else f"{pct}%")
            b.clicked.connect(lambda _=False, v=pct: self._intensity(v))
            gl.addWidget(b, i // 3, i % 3)
        self.btn_hl = QPushButton("Highlight")
        self.btn_hl.setCheckable(True)
        self.btn_hl.toggled.connect(self._highlight)
        gl.addWidget(self.btn_hl, 2, 0, 1, 3)
        top.addWidget(gi)
        # colour
        gc = QGroupBox("Color")
        cl = QGridLayout(gc)
        for i, (n, rgb) in enumerate(QUICK_COLOURS):
            b = QPushButton()
            b.setToolTip(n)
            b.setFixedSize(30, 26)
            b.setStyleSheet(f"background: rgb{rgb}; border: 1px solid #444;")
            b.clicked.connect(lambda _=False, c=rgb, nm=n: self.apply_colour(c, nm == "White"))
            cl.addWidget(b, i // 5, i % 5)
        bp = QPushButton("Picker…")
        bp.clicked.connect(self.pick_colour)
        cl.addWidget(bp, 2, 0, 1, 5)
        top.addWidget(gc)
        # position
        gp = QGroupBox("Position")
        pl = QVBoxLayout(gp)
        self.pad = XYPad()
        self.pad.moved.connect(self._pantilt)
        pl.addWidget(self.pad)
        bc = QPushButton("Center")
        bc.clicked.connect(lambda: (self.pad.set_pos(128, 128), self._pantilt(128, 128)))
        pl.addWidget(bc)
        top.addWidget(gp)
        lay.addLayout(top)

        self.tabs = QTabWidget()
        self.pages: dict[str, QVBoxLayout] = {}
        for feat in FEATURES:
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(2, 2, 2, 2)
            v.addStretch(1)
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setWidget(w)
            self.tabs.addTab(sc, feat)
            self.pages[feat] = v
        self.beam_quick = BeamQuick(engine)
        self.beam_quick.applied.connect(lambda: (self.refresh(), self.programmerChanged.emit()))
        self.pages["Beam"].insertWidget(0, self.beam_quick)
        self.fx = EffectsPanel(engine)
        self.fx.changed.connect(self.programmerChanged.emit)
        fx_scroll = QScrollArea()
        fx_scroll.setWidgetResizable(True)
        fx_scroll.setWidget(self.fx)
        self.tabs.addTab(fx_scroll, "Effects ✦")
        lay.addWidget(self.tabs, 1)

        bl = QHBoxLayout()
        b_store = QPushButton("Store…")
        b_store.clicked.connect(self.storeRequested.emit)
        b_clear = QPushButton("Clear")
        b_clear.setObjectName("danger")
        b_clear.clicked.connect(self.clear)
        b_sel = QPushButton("Clear values (keep selection)")
        b_sel.clicked.connect(lambda: (self.engine.clear_programmer(False), self.refresh(),
                                       self.fx.refresh(), self.programmerChanged.emit()))
        for b in (b_store, b_sel, b_clear):
            bl.addWidget(b)
        lay.addLayout(bl)

    # ----------------------------------------------------------------- build
    def rebuild(self) -> None:
        for row in self.rows.values():
            row.setParent(None)
            row.deleteLater()
        self.rows.clear()
        sel = self.engine.selection
        show = self.engine.show
        self.beam_quick.setVisible(any(show.fixture(f) and show.types[show.fixture(f).type_key].is_moving
                                       for f in sel))
        if not sel:
            self.info.setText("No fixtures selected  –  select fixtures or a group")
            return
        types = []
        for fid in sel:
            fx = show.fixture(fid)
            if fx and fx.type_key not in types:
                types.append(fx.type_key)
        self.info.setText(f"{len(sel)} fixture(s) selected: "
                          + ", ".join(show.types[t].name for t in types[:4]))
        seen = set()
        for tk in types:
            for ch in show.types[tk].channels:
                if ch.name in seen or ch.attr.endswith("_fine"):
                    continue
                seen.add(ch.name)
                val, active = self._current(ch.name)
                row = ChannelRow(ch.name, ch.attr, val, active, ch.functions(show.types[tk].is_moving))
                row.changed.connect(self._changed)
                row.released.connect(self._release)
                page = self.pages[FEATURE_OF.get(ch.attr, "Other")]
                page.insertWidget(page.count() - 1, row)
                self.rows[ch.name] = row
        self.pad.set_pos(self._attr_value("pan"), self._attr_value("tilt"))

    def _current(self, name: str) -> tuple[int, bool]:
        show = self.engine.show
        for fid in self.engine.selection:
            fx = show.fixture(fid)
            if not fx:
                continue
            for i, ch in enumerate(show.types[fx.type_key].channels):
                if ch.name == name:
                    v = self.engine.programmer_value(fid, i)
                    if v is not None:
                        return v, True
                    return ch.default, False
        return 0, False

    def _attr_value(self, attr: str) -> int:
        show = self.engine.show
        for fid in self.engine.selection:
            fx = show.fixture(fid)
            if not fx:
                continue
            for i, ch in enumerate(show.types[fx.type_key].channels):
                if ch.attr == attr:
                    v = self.engine.programmer_value(fid, i)
                    return ch.default if v is None else v
        return 128

    def refresh(self) -> None:
        for name, row in self.rows.items():
            v, active = self._current(name)
            row.set_value(v, active)
        self.pad.set_pos(self._attr_value("pan"), self._attr_value("tilt"))

    # --------------------------------------------------------------- actions
    def _changed(self, name: str, v: int) -> None:
        self.engine.set_attr(name, v, by_name=True)
        self.programmerChanged.emit()

    def _release(self, name: str) -> None:
        show = self.engine.show
        with self.engine.lock:
            for fid in self.engine.selection:
                fx = show.fixture(fid)
                for i, ch in enumerate(show.types[fx.type_key].channels):
                    if ch.name == name:
                        self.engine.programmer.get(fid, {}).pop(i, None)
        self.refresh()
        self.programmerChanged.emit()

    def _intensity(self, pct: int) -> None:
        self.engine.set_intensity(pct)
        self.refresh()
        self.programmerChanged.emit()

    def _highlight(self, on: bool) -> None:
        self.engine.highlight = on

    def _pantilt(self, x: int, y: int) -> None:
        self.engine.set_attr("pan", x)
        self.engine.set_attr("tilt", y)
        for name, row in self.rows.items():
            v, active = self._current(name)
            row.set_value(v, active)
        self.programmerChanged.emit()

    def pick_colour(self) -> None:
        c = QColorDialog.getColor(QColor(255, 255, 255), self, "Fixture colour")
        if c.isValid():
            self.apply_colour((c.red(), c.green(), c.blue()))

    def apply_colour(self, rgb: tuple[int, int, int], is_white: bool = False) -> None:
        show = self.engine.show
        r, g, b = rgb
        for fid in self.engine.selection:
            fx = show.fixture(fid)
            ft = show.types[fx.type_key]
            attrs = {c.attr for c in ft.channels}
            if attrs & {"red", "green", "blue"}:
                w = 0
                if "white" in attrs:
                    w = min(r, g, b)
                    if is_white:
                        r = g = b = 0
                        w = 255
                    else:
                        r, g, b = r - w, g - w, b - w
                for a, v in (("red", r), ("green", g), ("blue", b), ("white", w), ("amber", 0), ("uv", 0)):
                    self.engine.set_attr(a, v, [fid])
                r, g, b = rgb
            elif attrs & {"cyan", "magenta", "yellow"}:
                for a, v in (("cyan", 255 - r), ("magenta", 255 - g), ("yellow", 255 - b)):
                    self.engine.set_attr(a, v, [fid])
            elif "color" in attrs:
                best = min(range(len(WHEEL_COLOURS)),
                           key=lambda i: sum((x - y) ** 2 for x, y in zip(WHEEL_COLOURS[i], rgb)))
                self.engine.set_attr("color", int(best * 192 / len(WHEEL_COLOURS)) + 2, [fid])
        self.refresh()
        self.programmerChanged.emit()

    def clear(self) -> None:
        self.engine.clear_programmer(True)
        self.btn_hl.setChecked(False)
        self.fx.refresh()
        self.rebuild()
        self.programmerChanged.emit()
