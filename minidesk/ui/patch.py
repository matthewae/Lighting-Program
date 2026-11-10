"""Patch table + fixture inspector, add-fixture dialog and fixture type editor."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..attributes import FEATURE_OF
from ..engine import Engine
from ..model import MODEL_KINDS, Fixture, FixtureType, Show, builtin_types
from .fixture_models import model_icon

COLS = ["ID", "Name", "Type", "Model", "Univ", "Addr", "Ch"]
NAME_MAX = 16


def is_console_show(show: Show) -> bool:
    return bool(show.source_path)


def allowed_types(show: Show) -> list[FixtureType]:
    if is_console_show(show):
        return sorted((t for t in show.types.values() if t.lib_index >= 0), key=lambda t: t.lib_index)
    return sorted(show.types.values(), key=lambda t: t.key)


def free_address(show: Show, n: int, universe: int = 0, ignore: int | None = None) -> int:
    used = set()
    for fx in show.fixtures:
        if fx.patched and fx.universe == universe and fx.fid != ignore:
            used.update(range(fx.address, fx.address + len(show.ftype(fx).channels)))
    for a in range(1, 514 - n):
        if not used & set(range(a, a + n)):
            return a
    return 0


class AddFixtureDialog(QDialog):
    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add fixtures")
        self.engine = engine
        show = engine.show
        if not is_console_show(show):
            for t in builtin_types():
                if t.key not in show.types:
                    show.add_type(t)
        f = QFormLayout(self)
        if is_console_show(show):
            note = QLabel("Console file: only fixture types from the console library can be saved into "
                          "the .SHO. (New profiles must be created on the console first.)")
            note.setWordWrap(True)
            f.addRow(note)
        self.type = QComboBox()
        for t in allowed_types(show):
            self.type.addItem(model_icon(t.kind), f"{t.name}  ({t.manufacturer}, {len(t.channels)} ch)", t.key)
        self.count = QSpinBox()
        self.count.setRange(1, 128)
        self.name = QLineEdit()
        self.name.setMaxLength(NAME_MAX)
        self.fid = QSpinBox()
        self.fid.setRange(1, 512)
        self.fid.setValue(show.next_fid())
        self.uni = QSpinBox()
        self.uni.setRange(1, 4 if is_console_show(show) else 64)
        self.addr = QSpinBox()
        self.addr.setRange(1, 512)
        self.type.currentIndexChanged.connect(self._auto_addr)
        self.uni.valueChanged.connect(self._auto_addr)
        f.addRow("Fixture type", self.type)
        f.addRow("Quantity", self.count)
        f.addRow("Name (empty = type)", self.name)
        f.addRow("First fixture number", self.fid)
        f.addRow("Universe", self.uni)
        f.addRow("Start address (auto = first free)", self.addr)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._auto_addr()

    def _ft(self) -> FixtureType:
        return self.engine.show.types[self.type.currentData()]

    def _auto_addr(self, *_):
        if self.type.count():
            self.addr.setValue(max(1, free_address(self.engine.show, len(self._ft().channels),
                                                   self.uni.value() - 1)))

    def apply(self) -> list[int]:
        show = self.engine.show
        ft = self._ft()
        addr, fid = self.addr.value(), self.fid.value()
        made = []
        for i in range(self.count.value()):
            while show.fixture(fid):
                fid += 1
            nm = self.name.text() or ft.name
            if self.count.value() > 1:
                nm = f"{nm[:NAME_MAX - 3]} {i + 1}"
            ok = addr + len(ft.channels) - 1 <= 512
            fx = Fixture(fid=fid, name=nm, type_key=ft.key, universe=self.uni.value() - 1,
                         address=addr if ok else 0, x=-5 + (i % 11), y=3.0, z=5.0)
            show.fixtures.append(fx)
            made.append(fid)
            addr += len(ft.channels)
            fid += 1
        show.fixtures.sort(key=lambda f: f.fid)
        return made


class RangesDialog(QDialog):
    """Edit the DMX ranges ("functions") of one channel."""

    def __init__(self, ch, moving: bool, parent=None):
        super().__init__(parent)
        self.ch = ch
        self.setWindowTitle(f"Functions – {ch.name}")
        self.resize(460, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("DMX ranges of this channel (from – to – label). Used by the programmer buttons "
                             "and the visualizer (gobo numbers, prism on/off, shutter open/strobe…)."))
        rows = ch.ranges or ch.functions(moving)
        self.table = QTableWidget(len(rows), 3)
        self.table.setHorizontalHeaderLabels(["From", "To", "Label"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for r, (lo, hi, lab) in enumerate(rows):
            for c, v in enumerate((lo, hi, lab)):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))
        lay.addWidget(self.table, 1)
        h = QHBoxLayout()
        for text, fn in (("Add row", self._add), ("Delete row", self._del),
                         ("Reset to generic", self._generic)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            h.addWidget(b)
        lay.addLayout(h)
        self.moving = moving
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._reset = False

    def _add(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, v in enumerate(("0", "255", "Function")):
            self.table.setItem(r, c, QTableWidgetItem(v))

    def _del(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def _generic(self):
        self._reset = True
        self.accept()

    def apply(self) -> None:
        if self._reset:
            self.ch.ranges = []
            return
        out = []
        for r in range(self.table.rowCount()):
            try:
                lo = max(0, min(255, int(self.table.item(r, 0).text())))
                hi = max(lo, min(255, int(self.table.item(r, 1).text())))
                out.append([lo, hi, self.table.item(r, 2).text().strip() or f"{lo}-{hi}"])
            except (ValueError, AttributeError):
                continue
        self.ch.ranges = sorted(out)


class ReaddressDialog(QDialog):
    def __init__(self, show: Show, fixtures: list[Fixture], parent=None):
        super().__init__(parent)
        self.show, self.fixtures = show, sorted(fixtures, key=lambda f: f.fid)
        self.setWindowTitle(f"Re-address {len(fixtures)} fixture(s)")
        f = QFormLayout(self)
        self.uni = QSpinBox()
        self.uni.setRange(1, 4 if is_console_show(show) else 64)
        self.uni.setValue(self.fixtures[0].universe + 1)
        self.start = QSpinBox()
        self.start.setRange(1, 512)
        self.start.setValue(self.fixtures[0].address or 1)
        self.gap = QSpinBox()
        self.gap.setRange(0, 100)
        self.gap.setToolTip("Free channels left between fixtures")
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        for w in (self.uni, self.start, self.gap):
            w.valueChanged.connect(self._preview)
        f.addRow("Universe", self.uni)
        f.addRow("Start address", self.start)
        f.addRow("Gap between fixtures", self.gap)
        f.addRow(self.preview)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._preview()

    def plan(self) -> list[tuple[Fixture, int]]:
        a = self.start.value()
        out = []
        for fx in self.fixtures:
            out.append((fx, a))
            a += len(self.show.ftype(fx).channels) + self.gap.value()
        return out

    def problems(self) -> list[str]:
        u = self.uni.value() - 1
        sel = {fx.fid for fx in self.fixtures}
        used = {}
        for fx in self.show.fixtures:
            if fx.fid not in sel and fx.patched and fx.universe == u:
                for c in range(fx.address, fx.address + len(self.show.ftype(fx).channels)):
                    used[c] = fx.fid
        errs = []
        for fx, a in self.plan():
            n = len(self.show.ftype(fx).channels)
            if a + n - 1 > 512:
                errs.append(f"#{fx.fid} does not fit (ends at {a + n - 1})")
            hit = {used[c] for c in range(a, a + n) if c in used}
            if hit:
                errs.append(f"#{fx.fid} overlaps {sorted(hit)}")
        return errs

    def _preview(self, *_):
        pl = self.plan()
        txt = ", ".join(f"#{fx.fid}→{a}" for fx, a in pl[:12]) + (" …" if len(pl) > 12 else "")
        errs = self.problems()
        self.preview.setText(txt + ("<br><span style='color:#f66'>" + "; ".join(errs[:4]) + "</span>" if errs else
                                    "<br><span style='color:#7f7'>✔ no conflicts</span>"))

    def apply(self) -> bool:
        if self.problems():
            return False
        for fx, a in self.plan():
            fx.universe, fx.address = self.uni.value() - 1, a
        return True


class TypeEditor(QDialog):
    ATTRS = sorted(FEATURE_OF)

    def __init__(self, ft: FixtureType, parent=None):
        super().__init__(parent)
        self.ft = ft
        self.setWindowTitle(f"Fixture type: {ft.key}")
        self.resize(600, 640)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        for k, label in MODEL_KINDS.items():
            self.kind.addItem(model_icon(k), label, k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(ft.kind)))
        self.beam = QDoubleSpinBox()
        self.beam.setRange(1, 120)
        self.beam.setValue(ft.beam_angle)
        self.pan = QDoubleSpinBox()
        self.pan.setRange(0, 720)
        self.pan.setValue(ft.pan_range)
        self.tilt = QDoubleSpinBox()
        self.tilt.setRange(0, 360)
        self.tilt.setValue(ft.tilt_range)
        form.addRow("3D model", self.kind)
        form.addRow("Beam angle (°)", self.beam)
        form.addRow("Pan range (°)", self.pan)
        form.addRow("Tilt range (°)", self.tilt)
        lay.addLayout(form)
        lab = QLabel("Channels – the attribute tells the visualizer/programmer what a channel does. "
                     "These are MiniDesk settings; the console's own profile is not changed.")
        lab.setWordWrap(True)
        lay.addWidget(lab)
        self.table = QTableWidget(len(ft.channels), 4)
        self.table.setHorizontalHeaderLabels(["Name", "Attribute", "Default", "Functions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.combos = []
        for r, ch in enumerate(ft.channels):
            it = QTableWidgetItem(ch.name)
            if ft.lib_index >= 0:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 0, it)
            cb = QComboBox()
            cb.addItems(self.ATTRS)
            cb.setCurrentText(ch.attr)
            self.table.setCellWidget(r, 1, cb)
            self.combos.append(cb)
            self.table.setItem(r, 2, QTableWidgetItem(str(ch.default)))
            fb = QPushButton(f"Edit ({len(ch.functions(ft.is_moving))})" + (" ✎" if ch.ranges else ""))
            fb.clicked.connect(lambda _=False, c=ch, b=fb: self._ranges(c, b))
            self.table.setCellWidget(r, 3, fb)
            self.table.setVerticalHeaderItem(r, QTableWidgetItem(str(r + 1)))
        lay.addWidget(self.table, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ranges(self, ch, btn) -> None:
        ch.attr = self.combos[self.ft.channels.index(ch)].currentText()
        d = RangesDialog(ch, self.ft.is_moving, self)
        if d.exec():
            d.apply()
            btn.setText(f"Edit ({len(ch.functions(self.ft.is_moving))})" + (" ✎" if ch.ranges else ""))

    def apply(self) -> None:
        ft = self.ft
        ft.kind, ft.beam_angle = self.kind.currentData(), self.beam.value()
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
    selectFixtures = Signal(list)

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        hh = self.table.horizontalHeader()
        for c in range(len(COLS)):
            hh.setSectionResizeMode(c, QHeaderView.Stretch if c == 1 else QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._row_selected)
        split.addWidget(self.table)

        insp = QGroupBox("Fixture")
        f = QFormLayout(insp)
        self.e_name = QLineEdit()
        self.e_name.setMaxLength(NAME_MAX)
        self.e_type = QComboBox()
        self.e_uni = QSpinBox()
        self.e_uni.setRange(1, 64)
        self.e_addr = QSpinBox()
        self.e_addr.setRange(0, 512)
        self.e_addr.setSpecialValueText("not patched")
        self.l_end = QLabel("")
        b_free = QPushButton("Next free address")
        b_free.clicked.connect(self._next_free)
        b_unpatch = QPushButton("Unpatch")
        b_unpatch.clicked.connect(lambda: self.e_addr.setValue(0))
        self.b_apply = QPushButton("Apply")
        self.b_apply.setObjectName("go")
        self.b_apply.clicked.connect(self._apply_inspector)
        f.addRow("Name", self.e_name)
        f.addRow("Type", self.e_type)
        f.addRow("Universe", self.e_uni)
        f.addRow("Address", self.e_addr)
        f.addRow("", self.l_end)
        r = QHBoxLayout()
        r.addWidget(b_free)
        r.addWidget(b_unpatch)
        f.addRow(r)
        f.addRow(self.b_apply)
        tip = QLabel("Position & aim: use the <b>Stage Layout</b> tab.")
        tip.setWordWrap(True)
        f.addRow(tip)
        self.e_addr.valueChanged.connect(self._end_label)
        self.e_type.currentIndexChanged.connect(self._end_label)
        split.addWidget(insp)
        split.setSizes([620, 280])
        lay.addWidget(split, 1)

        b = QHBoxLayout()
        for text, fn in (("Add fixtures…", self.add), ("Re-address selected…", self.readdress),
                         ("Remove / unpatch", self.remove),
                         ("Edit fixture type && 3D model…", self.edit_type)):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        b.addStretch(1)
        lay.addLayout(b)
        self.rebuild()

    # ----------------------------------------------------------------- table
    def rebuild(self) -> None:
        self._loading = True
        show = self.engine.show
        self.table.setRowCount(len(show.fixtures))
        for r, fx in enumerate(show.fixtures):
            ft = show.ftype(fx)
            vals = [fx.fid, fx.name, ft.name, ft.model_label, fx.universe + 1,
                    fx.address if fx.patched else "—", len(ft.channels)]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 3:
                    it.setIcon(model_icon(ft.kind, 20))
                if c == 5 and not fx.patched:
                    it.setForeground(Qt.red)
                self.table.setItem(r, c, it)
        self.e_type.blockSignals(True)
        self.e_type.clear()
        for t in allowed_types(show):
            self.e_type.addItem(model_icon(t.kind), t.name, t.key)
        self.e_type.blockSignals(False)
        conf = show.patch_conflicts()
        ci = show.console_info
        txt = f"{len(show.fixtures)} fixtures, {len(show.types)} types."
        if is_console_show(show):
            txt += (f"  Console file <b>{show.source_path.replace(chr(92), '/').split('/')[-1]}</b> "
                    f"({ci.get('console', '')}, IP {ci.get('ip', '?')}): names, types and addresses are "
                    f"saved directly into the .SHO.")
        if conf:
            txt += f"  <span style='color:#f66'>⚠ address overlap between fixtures {conf[:5]}</span>"
        self.info.setText(txt)
        self._loading = False
        self._row_selected()

    def _current(self) -> Fixture | None:
        r = self.table.currentRow()
        fx = self.engine.show.fixtures
        return fx[r] if 0 <= r < len(fx) else None

    def _row_selected(self) -> None:
        if self._loading:
            return
        fx = self._current()
        for w in (self.e_name, self.e_type, self.e_uni, self.e_addr, self.b_apply):
            w.setEnabled(fx is not None)
        if not fx:
            return
        self.e_name.setText(fx.name)
        self.e_type.setCurrentIndex(max(0, self.e_type.findData(fx.type_key)))
        self.e_uni.setRange(1, 4 if is_console_show(self.engine.show) else 64)
        self.e_uni.setValue(fx.universe + 1)
        self.e_addr.setValue(fx.address)
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        fids = [self.engine.show.fixtures[r].fid for r in rows]
        if fids:
            self.selectFixtures.emit(fids)

    def _end_label(self, *_):
        key = self.e_type.currentData()
        if not key:
            return
        n = len(self.engine.show.types[key].channels)
        a = self.e_addr.value()
        self.l_end.setText(f"uses {n} channels: {a}–{a + n - 1}" if a else f"{n} channels, not patched")

    def _next_free(self):
        fx = self._current()
        key = self.e_type.currentData()
        if fx and key:
            n = len(self.engine.show.types[key].channels)
            self.e_addr.setValue(free_address(self.engine.show, n, self.e_uni.value() - 1, fx.fid))

    def _apply_inspector(self):
        fx = self._current()
        if not fx:
            return
        show = self.engine.show
        ft = show.types[self.e_type.currentData()]
        a = self.e_addr.value()
        if a and a + len(ft.channels) - 1 > 512:
            QMessageBox.warning(self, "Patch", "The fixture does not fit in the universe at this address.")
            return
        old = (fx.name, fx.type_key, fx.universe, fx.address)
        fx.name = self.e_name.text().strip() or ft.name
        fx.type_key, fx.universe, fx.address = ft.key, self.e_uni.value() - 1, a
        conf = [c for c in show.patch_conflicts() if fx.fid in c]
        if conf:
            fx.name, fx.type_key, fx.universe, fx.address = old
            QMessageBox.warning(self, "Patch", f"Address overlaps another fixture: {conf[:3]}")
            return
        r = self.table.currentRow()
        self.engine.rebuild_patch()
        self.rebuild()
        self.table.selectRow(r)
        self.changed.emit()

    # --------------------------------------------------------------- actions
    def add(self) -> None:
        d = AddFixtureDialog(self.engine, self)
        if d.exec():
            made = d.apply()
            self.engine.rebuild_patch()
            self.rebuild()
            self.selectFixtures.emit(made)
            self.changed.emit()

    def readdress(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        show = self.engine.show
        fx = [show.fixtures[r] for r in rows]
        if not fx:
            QMessageBox.information(self, "Re-address", "Select one or more fixtures (Shift/Ctrl-click rows).")
            return
        d = ReaddressDialog(show, fx, self)
        if d.exec():
            if not d.apply():
                QMessageBox.warning(self, "Re-address", "Not applied – conflicts:\n" + "\n".join(d.problems()))
                return
            self.engine.rebuild_patch()
            self.rebuild()
            self.changed.emit()

    def remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        show = self.engine.show
        if is_console_show(show):
            olds = [r for r in rows if show.fixtures[r].slot >= 0]
            if olds and QMessageBox.question(
                    self, "Unpatch",
                    f"{len(olds)} fixture(s) come from the console file. Deleting them is not supported "
                    "(cues in the console may use them) – unpatch them instead (address = none)?") \
                    != QMessageBox.Yes:
                return
            for r in olds:
                show.fixtures[r].address = 0
            rows = [r for r in rows if show.fixtures[r].slot < 0]
        elif QMessageBox.question(self, "Remove", f"Remove {len(rows)} fixture(s)?") != QMessageBox.Yes:
            return
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
        fx = self._current()
        if not fx:
            QMessageBox.information(self, "Fixture type", "Select a fixture row first.")
            return
        d = TypeEditor(self.engine.show.ftype(fx), self)
        if d.exec():
            d.apply()
            self.engine.rebuild_patch()
            self.rebuild()
            self.changed.emit()
