"""Stage layout editor: stage size, fixture positions/aim and alignment tools."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..engine import Engine
from ..layout import auto_layout
from .visualizer import StageView


def _spin(lo, hi, step=0.25, suffix=" m", dec=2):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(dec)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


class StageEditor(QWidget):
    changed = Signal()

    def __init__(self, engine: Engine, view: StageView, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.view = view
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        info = QLabel("<b>Edit the stage here.</b> Choose <b>Top</b> (move left/right + front/back) or "
                      "<b>Front</b> (move left/right + height) and drag fixtures in the stage view. "
                      "Select several fixtures (Ctrl-click or drag a box) to move or align them together. "
                      "The layout is saved with your show.")
        info.setWordWrap(True)
        lay.addWidget(info)

        gv = QGroupBox("Stage view")
        hv = QHBoxLayout(gv)
        self.view_group = QButtonGroup(self)
        for i, (label, mode) in enumerate((("3D", "3d"), ("Top – edit X/Y", "top"), ("Front – edit X/Z", "front"))):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(mode == view.mode)
            b.clicked.connect(lambda _=False, m=mode: self._mode(m))
            self.view_group.addButton(b, i)
            hv.addWidget(b)
        hv.addWidget(QLabel("Snap"))
        self.snap = QComboBox()
        for v in ("off", "0.1", "0.25", "0.5", "1.0"):
            self.snap.addItem(v)
        self.snap.setCurrentText("0.25")
        self.snap.currentTextChanged.connect(lambda t: setattr(self.view, "snap", 0 if t == "off" else float(t)))
        hv.addWidget(self.snap)
        self.cb_models = QCheckBox("3D models")
        self.cb_models.setChecked(True)
        self.cb_models.toggled.connect(lambda v: (setattr(self.view, "show_models", v), self.view._sync_overlay()))
        self.cb_labels = QCheckBox("Labels")
        self.cb_labels.setChecked(True)
        self.cb_labels.toggled.connect(lambda v: (setattr(self.view, "show_labels", v), self.view._sync_overlay()))
        hv.addWidget(self.cb_models)
        hv.addWidget(self.cb_labels)
        lay.addWidget(gv)

        gt0 = QGroupBox("Rigging / truss model")
        ht = QHBoxLayout(gt0)
        self.truss = QComboBox()
        self.truss.currentIndexChanged.connect(self._truss_changed)
        b_imp = QPushButton("Import truss model (OBJ)…")
        b_imp.clicked.connect(self._import_truss)
        ht.addWidget(self.truss, 1)
        ht.addWidget(b_imp)
        lay.addWidget(gt0)

        gs = QGroupBox("Stage size")
        fs = QHBoxLayout(gs)
        self.w, self.d, self.h = _spin(2, 60), _spin(2, 60), _spin(2, 30)
        for lab, sp in (("Width", self.w), ("Depth", self.d), ("Height", self.h)):
            fs.addWidget(QLabel(lab))
            fs.addWidget(sp)
            sp.valueChanged.connect(self._stage)
        lay.addWidget(gs)

        gf = QGroupBox("Selected fixtures – position & aim")
        ff = QFormLayout(gf)
        self.sel_label = QLabel("nothing selected")
        ff.addRow(self.sel_label)
        self.x, self.y, self.z = _spin(-40, 40), _spin(-10, 60), _spin(0, 30)
        self.mount = QComboBox()
        self.mount.addItems(["hang", "floor"])
        self.rot = _spin(-360, 360, 15, " °", 0)
        self.aim = _spin(0, 180, 5, " °", 0)
        self.x.setToolTip("Left (–) / right (+) of the stage centre")
        self.y.setToolTip("Distance from the stage front edge (0) towards upstage")
        self.z.setToolTip("Height above the floor")
        self.rot.setToolTip("Which way the fixture faces: 0 = audience, 180 = upstage, ±90 = sideways")
        self.aim.setToolTip("Fixed fixtures: tilt from straight down (hanging) / straight up (floor)")
        ff.addRow("X  (left/right)", self.x)
        ff.addRow("Y  (front/back)", self.y)
        ff.addRow("Z  (height)", self.z)
        ff.addRow("Mount", self.mount)
        ff.addRow("Facing (yaw)", self.rot)
        ff.addRow("Tilt / aim", self.aim)
        for w, attr in ((self.x, "x"), (self.y, "y"), (self.z, "z"), (self.rot, "rot"), (self.aim, "aim")):
            w.valueChanged.connect(lambda v, a=attr: self._set(a, v))
        self.mount.currentTextChanged.connect(lambda v: self._set("mount", v))
        lay.addWidget(gf)

        gt = QGroupBox("Align tools (selected fixtures)")
        gl = QGridLayout(gt)
        tools = [
            ("Line up in a row", self.line_up, "Same Y and Z as the first selected fixture"),
            ("Distribute along X", self.distribute, "Spread evenly between the leftmost and rightmost"),
            ("Same height", lambda: self._copy("z"), "Copy the height of the first selected fixture"),
            ("Mirror left ↔ right", self.mirror, "Mirror X positions and facing around the centre"),
            ("Centre on stage", self.centre, "Move the selection so it is centred left/right"),
            ("Turn 180°", self.turn, "Face the other way (audience ↔ upstage)"),
            ("Auto layout (all)", self.auto, "Place every fixture from its group names"),
        ]
        for i, (t, fn, tip) in enumerate(tools):
            b = QPushButton(t)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            gl.addWidget(b, i // 3, i % 3)
        lay.addWidget(gt)
        lay.addStretch(1)
        self.refresh()

    # ----------------------------------------------------------------- sync
    def _mode(self, m: str) -> None:
        self.view.set_mode(m)
        self.sync_mode()

    def sync_mode(self) -> None:
        idx = {"3d": 0, "top": 1, "front": 2}[self.view.mode]
        self.view_group.button(idx).setChecked(True)

    def _sel(self):
        return [f for f in (self.engine.show.fixture(i) for i in self.engine.selection) if f]

    def refresh(self) -> None:
        self._loading = True
        show = self.engine.show
        self._fill_truss()
        self.w.setValue(show.stage_width)
        self.d.setValue(show.stage_depth)
        self.h.setValue(show.stage_height)
        sel = self._sel()
        for w in (self.x, self.y, self.z, self.mount, self.rot, self.aim):
            w.setEnabled(bool(sel))
        if sel:
            f = sel[0]
            self.sel_label.setText(f"{len(sel)} selected – showing #{f.fid} {f.name}"
                                   + ("   (changes apply to all selected)" if len(sel) > 1 else ""))
            self.x.setValue(f.x)
            self.y.setValue(f.y)
            self.z.setValue(f.z)
            self.mount.setCurrentText(f.mount)
            self.rot.setValue(f.rot)
            self.aim.setValue(f.aim)
        else:
            self.sel_label.setText("Nothing selected – click fixtures in the stage view or the Fixtures tab")
        self.sync_mode()
        self._loading = False

    def _fill_truss(self) -> None:
        from .. import meshes
        self.truss.blockSignals(True)
        self.truss.clear()
        self.truss.addItem("Default" + (" (bundled 12\" box truss)" if meshes.truss_default() != "builtin" else ""), "")
        self.truss.addItem("Simple box truss (built-in)", "builtin")
        cur = self.engine.show.truss_model
        if cur and cur != "builtin":
            import os
            self.truss.addItem(f"File: {os.path.basename(meshes.resolve(cur))}", cur)
        self.truss.setCurrentIndex(max(0, self.truss.findData(cur)))
        self.truss.blockSignals(False)

    def _truss_changed(self, *_):
        if self._loading:
            return
        self.engine.show.truss_model = self.truss.currentData() or ""
        self.changed.emit()

    def _import_truss(self):
        import os
        import shutil
        from PySide6.QtWidgets import QFileDialog
        from .. import truss_model
        path, _ = QFileDialog.getOpenFileName(self, "Import truss model", "",
                                              "Truss model (*.obj *.glb *.gltf *.fbx);;All files (*)")
        if not path:
            return
        try:
            data = truss_model.analyse(path)
        except Exception as e:
            QMessageBox.warning(self, "Truss model", f"Could not use this model:\n{e}")
            return
        dst_dir = os.path.join(os.path.expanduser("~"), ".minidesk", "models")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(path))
        if os.path.abspath(dst) != os.path.abspath(path):
            shutil.copy2(path, dst)
        self.engine.show.truss_model = dst
        self._fill_truss()
        segs = ", ".join(f"{s['length']:.2f} m" for s in data["segments"])
        QMessageBox.information(self, "Truss model", f"Truss width {data['width'] * 100:.1f} cm, segments: {segs}")
        self.changed.emit()

    def _stage(self, *_):
        if self._loading:
            return
        s = self.engine.show
        s.stage_width, s.stage_depth, s.stage_height = self.w.value(), self.d.value(), self.h.value()
        self.changed.emit()

    def _set(self, attr, value):
        if self._loading:
            return
        sel = self._sel()
        if not sel:
            return
        if attr in ("x", "y", "z") and len(sel) > 1:
            delta = value - getattr(sel[0], attr)      # move the group, keep spacing
            for f in sel:
                setattr(f, attr, getattr(f, attr) + delta)
        else:
            for f in sel:
                setattr(f, attr, value)
        self.changed.emit()

    def _done(self):
        self.refresh()
        self.changed.emit()

    # ---------------------------------------------------------------- tools
    def _need(self, n=1):
        sel = self._sel()
        if len(sel) < n:
            QMessageBox.information(self, "Stage", f"Select at least {n} fixture(s) first.")
            return None
        return sel

    def line_up(self):
        sel = self._need(2)
        if sel:
            for f in sel[1:]:
                f.y, f.z = sel[0].y, sel[0].z
            self._done()

    def distribute(self):
        sel = self._need(3)
        if sel:
            xs = sorted(sel, key=lambda f: f.x)
            lo, hi = xs[0].x, xs[-1].x
            if hi - lo < 0.01:
                lo, hi = -self.engine.show.stage_width * 0.4, self.engine.show.stage_width * 0.4
            for i, f in enumerate(sorted(sel, key=lambda f: f.fid)):
                f.x = round(lo + (hi - lo) * i / (len(sel) - 1), 3)
            self._done()

    def _copy(self, attr):
        sel = self._need(2)
        if sel:
            for f in sel[1:]:
                setattr(f, attr, getattr(sel[0], attr))
            self._done()

    def mirror(self):
        sel = self._need(1)
        if sel:
            for f in sel:
                f.x, f.rot = -f.x, -f.rot
            self._done()

    def centre(self):
        sel = self._need(1)
        if sel:
            mid = (min(f.x for f in sel) + max(f.x for f in sel)) / 2
            for f in sel:
                f.x -= mid
            self._done()

    def turn(self):
        sel = self._need(1)
        if sel:
            for f in sel:
                f.rot = (f.rot + 180) % 360
                if f.rot > 180:
                    f.rot -= 360
            self._done()

    def auto(self):
        if QMessageBox.question(self, "Auto layout", "Re-place ALL fixtures from their group names?") \
                == QMessageBox.Yes:
            auto_layout(self.engine.show)
            self._done()
