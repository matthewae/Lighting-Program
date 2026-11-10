"""Patch table, add-fixture dialog and fixture type editor."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..attributes import FEATURE_OF
from ..engine import Engine
from ..layout import auto_layout
from ..model import Fixture, FixtureType, builtin_types

COLS = ["ID", "Name", "Type", "Univ", "Addr", "Ch", "X (m)", "Y (m)", "Z (m)", "Mount", "Yaw°", "Aim°"]


class AddFixtureDialog(QDialog):
    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add fixtures")
        self.engine = engine
        show = engine.show
        for t in builtin_types():
            if t.key not in show.types:
                show.add_type(t)
        f = QFormLayout(self)
        self.type = QComboBox()
        self.type.addItems(sorted(show.types))
        self.count = QSpinBox()
        self.count.setRange(1, 128)
        self.name = QLineEdit()
        self.fid = QSpinBox()
        self.fid.setRange(1, 9999)
        self.fid.setValue(show.next_fid())
        self.uni = QSpinBox()
        self.uni.setRange(1, 64)
        self.addr = QSpinBox()
        self.addr.setRange(1, 512)
        self.addr.setValue(self._free_address())
        f.addRow("Fixture type", self.type)
        f.addRow("Quantity", self.count)
        f.addRow("Name (empty = type)", self.name)
        f.addRow("First fixture ID", self.fid)
        f.addRow("Universe", self.uni)
        f.addRow("Start address", self.addr)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _free_address(self) -> int:
        end = 0
        for fx in self.engine.show.fixtures:
            if fx.patched and fx.universe == 0:
                end = max(end, fx.address + len(self.engine.show.ftype(fx).channels) - 1)
        return min(512, end + 1)

    def apply(self) -> None:
        show = self.engine.show
        ft = show.types[self.type.currentText()]
        addr, fid = self.addr.value(), self.fid.value()
        for i in range(self.count.value()):
            while show.fixture(fid):
                fid += 1
            nm = self.name.text() or ft.name
            if self.count.value() > 1:
                nm = f"{nm} {i + 1}"
            fx = Fixture(fid=fid, name=nm, type_key=ft.key, universe=self.uni.value() - 1,
                         address=addr if addr + len(ft.channels) - 1 <= 512 else 0,
                         x=-5 + (i % 11), y=3.0, z=5.0)
            show.fixtures.append(fx)
            addr += len(ft.channels)
            fid += 1
        show.fixtures.sort(key=lambda f: f.fid)


class TypeEditor(QDialog):
    ATTRS = sorted(FEATURE_OF)

    def __init__(self, ft: FixtureType, parent=None):
        super().__init__(parent)
        self.ft = ft
        self.setWindowTitle(f"Fixture type: {ft.key}")
        self.resize(560, 600)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItems(["par", "moving", "strobe", "fresnel", "fog", "generic"])
        self.kind.setCurrentText(ft.kind)
        self.beam = QDoubleSpinBox()
        self.beam.setRange(1, 120)
        self.beam.setValue(ft.beam_angle)
        self.pan = QDoubleSpinBox()
        self.pan.setRange(0, 720)
        self.pan.setValue(ft.pan_range)
        self.tilt = QDoubleSpinBox()
        self.tilt.setRange(0, 360)
        self.tilt.setValue(ft.tilt_range)
        form.addRow("Kind", self.kind)
        form.addRow("Beam angle (°)", self.beam)
        form.addRow("Pan range (°)", self.pan)
        form.addRow("Tilt range (°)", self.tilt)
        lay.addLayout(form)
        lay.addWidget(QLabel("Channels – the attribute tells the visualizer/programmer what a channel does"))
        self.table = QTableWidget(len(ft.channels), 3)
        self.table.setHorizontalHeaderLabels(["Name", "Attribute", "Default"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.combos = []
        for r, ch in enumerate(ft.channels):
            self.table.setItem(r, 0, QTableWidgetItem(ch.name))
            cb = QComboBox()
            cb.addItems(self.ATTRS)
            cb.setCurrentText(ch.attr)
            self.table.setCellWidget(r, 1, cb)
            self.combos.append(cb)
            self.table.setItem(r, 2, QTableWidgetItem(str(ch.default)))
            self.table.setVerticalHeaderItem(r, QTableWidgetItem(str(r + 1)))
        lay.addWidget(self.table, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def apply(self) -> None:
        ft = self.ft
        ft.kind, ft.beam_angle = self.kind.currentText(), self.beam.value()
        ft.pan_range, ft.tilt_range = self.pan.value(), self.tilt.value()
        for r, ch in enumerate(ft.channels):
            ch.name = self.table.item(r, 0).text()
            ch.attr = self.combos[r].currentText()
            try:
                ch.default = max(0, min(255, int(self.table.item(r, 2).text())))
            except ValueError:
                pass


class PatchPanel(QWidget):
    changed = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.info = QLabel("")
        lay.addWidget(self.info)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._edited)
        lay.addWidget(self.table, 1)
        b = QHBoxLayout()
        for text, fn in (("Add fixtures…", self.add), ("Remove selected", self.remove),
                         ("Edit fixture type…", self.edit_type), ("Auto layout stage", self.layout_stage)):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        b.addStretch(1)
        lay.addLayout(b)
        self._loading = False
        self.rebuild()

    def rebuild(self) -> None:
        self._loading = True
        show = self.engine.show
        self.table.setRowCount(len(show.fixtures))
        for r, fx in enumerate(show.fixtures):
            ft = show.ftype(fx)
            vals = [fx.fid, fx.name, ft.key, fx.universe + 1, fx.address, len(ft.channels),
                    f"{fx.x:.2f}", f"{fx.y:.2f}", f"{fx.z:.2f}", fx.mount, f"{fx.rot:g}", f"{fx.aim:g}"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c in (0, 2, 5):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c == 4 and not fx.patched:
                    it.setText("0")
                    it.setForeground(Qt.red)
                self.table.setItem(r, c, it)
        conf = show.patch_conflicts()
        ci = show.console_info
        txt = f"{len(show.fixtures)} fixtures, {len(show.types)} types"
        if ci:
            txt += f"   |   imported from {ci.get('console', '')}  (console IP {ci.get('ip', '?')})"
        if conf:
            txt += f"   |   ⚠ address overlap: {conf[:5]}"
        self.info.setText(txt + "   |   address 0 = not patched")
        self._loading = False

    def _edited(self, it: QTableWidgetItem) -> None:
        if self._loading:
            return
        fx = self.engine.show.fixtures[it.row()]
        t = it.text().strip()
        try:
            c = it.column()
            if c == 1:
                fx.name = t
            elif c == 3:
                fx.universe = max(0, int(t) - 1)
            elif c == 4:
                fx.address = max(0, min(512, int(t)))
            elif c == 6:
                fx.x = float(t)
            elif c == 7:
                fx.y = float(t)
            elif c == 8:
                fx.z = float(t)
            elif c == 9:
                fx.mount = "floor" if t.lower().startswith("f") else "hang"
            elif c == 10:
                fx.rot = float(t)
            elif c == 11:
                fx.aim = float(t)
        except ValueError:
            pass
        self.engine.rebuild_patch()
        self.changed.emit()

    def add(self) -> None:
        d = AddFixtureDialog(self.engine, self)
        if d.exec():
            d.apply()
            self.engine.rebuild_patch()
            self.rebuild()
            self.changed.emit()

    def remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        if QMessageBox.question(self, "Remove", f"Remove {len(rows)} fixture(s)?") != QMessageBox.Yes:
            return
        show = self.engine.show
        for r in rows:
            fid = show.fixtures[r].fid
            del show.fixtures[r]
            for g in show.groups:
                if fid in g.fixtures:
                    g.fixtures.remove(fid)
            for pb in show.playbacks:
                for s in pb.steps:
                    s.values.pop(fid, None)
            self.engine.programmer.pop(fid, None)
            if fid in self.engine.selection:
                self.engine.selection.remove(fid)
        self.engine.rebuild_patch()
        self.rebuild()
        self.changed.emit()

    def edit_type(self) -> None:
        r = self.table.currentRow()
        show = self.engine.show
        if r < 0:
            QMessageBox.information(self, "Fixture type", "Select a fixture row first.")
            return
        ft = show.ftype(show.fixtures[r])
        d = TypeEditor(ft, self)
        if d.exec():
            d.apply()
            self.engine.rebuild_patch()
            self.rebuild()
            self.changed.emit()

    def layout_stage(self) -> None:
        auto_layout(self.engine.show)
        self.rebuild()
        self.changed.emit()
