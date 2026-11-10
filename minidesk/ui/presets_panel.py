"""Preset pool: store programmer values as Color / Position / Beam / Intensity presets."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..engine import Engine
from ..model import PRESET_CATEGORIES, Preset
from ..vis_state import compute

CAT_ICON = {"Intensity": "💡", "Position": "🎯", "Color": "🎨", "Beam": "🔆", "All": "⭐"}


NAMED = {"white": (245, 245, 245), "red": (230, 30, 30), "green": (30, 200, 60), "blue": (40, 80, 240),
         "yellow": (250, 220, 30), "yelow": (250, 220, 30), "magenta": (230, 40, 200), "cyan": (40, 220, 240),
         "orange": (255, 130, 20), "pink": (255, 150, 190), "purple": (140, 50, 230), "amber": (255, 170, 40),
         "uv": (110, 40, 255), "warm": (255, 200, 140), "cto": (255, 190, 120), "lavender": (190, 150, 255)}


def preset_colour(engine: Engine, pr: Preset) -> QColor | None:
    """Colour for the button swatch: from the name ("LIGHT BLUE") or computed from the values."""
    n = pr.name.lower()
    for key, rgb in sorted(NAMED.items(), key=lambda kv: -len(kv[0])):
        if key in n:
            r, g, b = rgb
            if "light" in n:
                r, g, b = (int(x + (255 - x) * 0.45) for x in (r, g, b))
            return QColor(r, g, b)
    show = engine.show
    for fid, vals in pr.values.items():
        fx = show.fixture(fid)
        if not fx or not fx.patched:
            continue
        ft = show.types[fx.type_key]
        dmx = bytearray(fx.address - 1 + len(ft.channels) + 1)
        for i, c in enumerate(ft.channels):
            dmx[fx.address - 1 + i] = 255 if c.attr == "dimmer" else vals.get(i, c.default)
        st = compute(fx, ft, bytes(dmx), time.time())
        if st.intensity > 0.05:
            return QColor(*st.colour)
    return None


class StorePresetDialog(QDialog):
    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Store preset")
        f = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setMaxLength(16)
        self.cat = QComboBox()
        self.cat.addItems(PRESET_CATEGORIES)
        self.cat.setCurrentText("Color")
        f.addRow(QLabel(f"From the programmer ({len(engine.programmer)} fixtures). Only channels of the "
                        "chosen category are stored."))
        f.addRow("Name", self.name)
        f.addRow("Category", self.cat)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class PresetsPanel(QWidget):
    applied = Signal()
    changed = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        t = QLabel("Presets")
        t.setObjectName("title")
        top.addWidget(t)
        top.addWidget(QLabel("  Show:"))
        self.filter = QComboBox()
        self.filter.addItems(["All categories"] + PRESET_CATEGORIES)
        self.filter.currentTextChanged.connect(lambda _t: self.rebuild())
        top.addWidget(self.filter)
        top.addStretch(1)
        b = QPushButton("＋ Store programmer as preset…")
        b.setObjectName("go")
        b.clicked.connect(self.store)
        top.addWidget(b)
        lay.addLayout(top)
        hint = QLabel("Click a preset to apply it to the selected fixtures (fixtures of the same type get the "
                      "same values). Right-click: rename / update / delete. Presets imported from the console "
                      "are marked ●; their names are saved back into the .SHO.")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.box = QWidget()
        self.grid = QGridLayout(self.box)
        self.grid.setSpacing(6)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.box)
        lay.addWidget(sc, 1)
        self.rebuild()

    def rebuild(self) -> None:
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        cat = self.filter.currentText()
        items = [p for p in self.engine.show.presets if cat == "All categories" or p.category == cat]
        if not items:
            self.grid.addWidget(QLabel("No presets yet – set values in the Programmer, then "
                                       "'Store programmer as preset…'."), 0, 0)
            return
        for i, pr in enumerate(items):
            col = preset_colour(self.engine, pr) if pr.category in ("Color", "All") else None
            mark = "● " if pr.slot >= 0 else ""
            b = QPushButton(f"{CAT_ICON.get(pr.category, '')} {mark}{pr.name}\n{pr.category} · {len(pr.values)} fx")
            b.setFixedSize(150, 58)
            if col is not None:
                txt = "#111" if col.lightness() > 140 else "#eee"
                b.setStyleSheet(f"background: {col.name()}; color: {txt}; border: 1px solid #555;")
            b.clicked.connect(lambda _=False, p=pr: self.apply(p))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, p=pr, btn=b: self.menu(p, btn, pos))
            self.grid.addWidget(b, i // 5, i % 5)

    def apply(self, pr: Preset) -> None:
        n = self.engine.apply_preset(pr)
        if not self.engine.selection:
            self.engine.select(list(pr.values))
        self.applied.emit()
        if n == 0:
            QMessageBox.information(self, "Preset", "The selected fixtures have no values in this preset.")

    def store(self) -> None:
        if not self.engine.programmer:
            QMessageBox.information(self, "Preset", "The programmer is empty.")
            return
        d = StorePresetDialog(self.engine, self)
        if d.exec():
            pr = self.engine.make_preset(d.name.text().strip() or f"Preset {len(self.engine.show.presets) + 1}",
                                         d.cat.currentText())
            if not pr.values:
                QMessageBox.information(self, "Preset", f"No {d.cat.currentText()} values in the programmer.")
                return
            self.engine.show.presets.append(pr)
            self.rebuild()
            self.changed.emit()

    def menu(self, pr: Preset, btn, pos) -> None:
        m = QMenu(self)
        a_ren = m.addAction("Rename…")
        a_upd = m.addAction("Update from programmer")
        a_cat = m.addAction("Change category…")
        a_del = m.addAction("Delete")
        a = m.exec(btn.mapToGlobal(pos))
        if a == a_ren:
            name, ok = QInputDialog.getText(self, "Rename preset", "Name:", text=pr.name)
            if ok and name.strip():
                pr.name = name.strip()[:16]
        elif a == a_upd:
            new = self.engine.make_preset(pr.name, pr.category)
            if new.values:
                pr.values.update(new.values)
        elif a == a_cat:
            c, ok = QInputDialog.getItem(self, "Category", "Category:", PRESET_CATEGORIES,
                                         PRESET_CATEGORIES.index(pr.category), False)
            if ok:
                pr.category = c
        elif a == a_del:
            if pr.slot >= 0:
                QMessageBox.information(self, "Preset", "Presets from the console file cannot be deleted "
                                        "from the .SHO; it is hidden in MiniDesk only.")
            self.engine.show.presets.remove(pr)
        else:
            return
        self.rebuild()
        self.changed.emit()
