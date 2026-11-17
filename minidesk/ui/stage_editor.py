"""Stage layout editor: stage size, fixture positions/aim and alignment tools."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
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
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)
        self.setToolTip("Choose Top (left/right + front/back) or Front (left/right + height) and drag fixtures "
                        "in the stage view. Ctrl-click or drag a box to select several fixtures. "
                        "The layout is saved with your show.")

        # stage view row
        hv = QHBoxLayout()
        hv.setSpacing(3)
        t = QLabel("Stage")
        t.setObjectName("title")
        hv.addWidget(t)
        self.view_group = QButtonGroup(self)
        for i, (label, mode, tip) in enumerate((("3D", "3d", "3D view"), ("Top", "top", "Top view: drag = move X/Y"),
                                                ("Front", "front", "Front view: drag = move X/height"))):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(mode == view.mode)
            b.setToolTip(tip)
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
        self.cb_models = QCheckBox("Models")
        self.cb_models.setChecked(True)
        self.cb_models.toggled.connect(lambda v: (setattr(self.view, "show_models", v), self.view._sync_overlay()))
        self.cb_labels = QCheckBox("Labels")
        self.cb_labels.setChecked(True)
        self.cb_labels.toggled.connect(lambda v: (setattr(self.view, "show_labels", v), self.view._sync_overlay()))
        hv.addWidget(self.cb_models)
        hv.addWidget(self.cb_labels)
        hv.addStretch(1)
        lay.addLayout(hv)

        # venue + stage
        gvn = QGroupBox("Venue and stage")
        gvl = QGridLayout(gvn)
        gvl.setVerticalSpacing(3)
        self.venue_label = QLabel()
        gvl.addWidget(self.venue_label, 0, 0, 1, 4)
        b_venue = QPushButton("Apply GMS hall layout")
        b_venue.setToolTip("From the venue photos: back bar near the wall, front bar, two black truss towers, "
                           "FOH fresnel bar and the projection screen – fixtures numbered left → right")
        b_venue.clicked.connect(self.apply_venue)
        gvl.addWidget(b_venue, 0, 4, 1, 2)
        self.cb_screen = QCheckBox("Screen")
        self.cb_screen.setToolTip("Projection screen on the back wall")
        self.cb_screen.toggled.connect(self._screen)
        self.sw, self.sh = _spin(1, 40), _spin(0.5, 20)
        self.sw.valueChanged.connect(self._screen)
        self.sh.valueChanged.connect(self._screen)
        self.w, self.d, self.h = _spin(2, 60), _spin(2, 60), _spin(2, 30)
        gvl.addWidget(QLabel("Stage W / D / H"), 1, 0)
        gvl.addWidget(self.w, 1, 1)
        gvl.addWidget(self.d, 1, 2)
        gvl.addWidget(self.h, 1, 3)
        for sp in (self.w, self.d, self.h):
            sp.valueChanged.connect(self._stage)
        gvl.addWidget(self.cb_screen, 2, 0)
        gvl.addWidget(self.sw, 2, 1)
        gvl.addWidget(self.sh, 2, 2)
        self.cb_rig = QCheckBox("Venue rigging (pipes + towers)")
        self.cb_rig.setToolTip("Use the venue rigging instead of trusses along the fixture rows")
        self.cb_rig.toggled.connect(self._rig_toggled)
        gvl.addWidget(self.cb_rig, 1, 4, 1, 2)
        self.cb_hidden = QCheckBox("Show hidden fixtures")
        self.cb_hidden.setToolTip("Hidden fixtures are not part of the rig (e.g. unpatched entries). "
                                  "They stay patched and are still output – only the stage view skips them.")
        self.cb_hidden.toggled.connect(lambda v: (setattr(self.view, "show_hidden", v), self.view.update()))
        gvl.addWidget(self.cb_hidden, 2, 4, 1, 2)
        self.truss = QComboBox()
        self.truss.currentIndexChanged.connect(self._truss_changed)
        b_imp = QPushButton("Import truss…")
        b_imp.setToolTip("Import a truss model (OBJ / GLB / FBX)")
        b_imp.clicked.connect(self._import_truss)
        gvl.addWidget(QLabel("Truss model"), 3, 0)
        gvl.addWidget(self.truss, 3, 1, 1, 3)
        gvl.addWidget(b_imp, 3, 4, 1, 2)
        lay.addWidget(gvn)

        # selected fixtures
        gf = QGroupBox("Selected fixtures – position and aim")
        ff = QGridLayout(gf)
        ff.setVerticalSpacing(3)
        self.sel_label = QLabel("nothing selected")
        ff.addWidget(self.sel_label, 0, 0, 1, 6)
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
        for c, (lab, w) in enumerate((("X", self.x), ("Y", self.y), ("Z", self.z))):
            ff.addWidget(QLabel(lab), 1, 2 * c)
            ff.addWidget(w, 1, 2 * c + 1)
        for c, (lab, w) in enumerate((("Mount", self.mount), ("Yaw", self.rot), ("Tilt", self.aim))):
            ff.addWidget(QLabel(lab), 2, 2 * c)
            ff.addWidget(w, 2, 2 * c + 1)
        for w, attr in ((self.x, "x"), (self.y, "y"), (self.z, "z"), (self.rot, "rot"), (self.aim, "aim")):
            w.valueChanged.connect(lambda v, a=attr: self._set(a, v))
        self.mount.currentTextChanged.connect(lambda v: self._set("mount", v))
        lay.addWidget(gf)

        gt = QGroupBox("Align tools (selected fixtures)")
        gl = QGridLayout(gt)
        gl.setSpacing(3)
        tools = [
            ("Line up", self.line_up, "Same Y and Z as the first selected fixture"),
            ("Distribute X", self.distribute, "Spread evenly between the leftmost and rightmost"),
            ("Same height", lambda: self._copy("z"), "Copy the height of the first selected fixture"),
            ("Mirror ↔", self.mirror, "Mirror X positions and facing around the centre"),
            ("Centre", self.centre, "Move the selection so it is centred left/right"),
            ("Turn 180°", self.turn, "Face the other way (audience ↔ upstage)"),
            ("Hide", lambda: self._hide(True), "Do not draw the selected fixtures in the stage view"),
            ("Unhide", lambda: self._hide(False), "Draw the selected fixtures again "
                                                  "(tick 'Show hidden fixtures' to select them)"),
            ("Auto layout", self.auto, "Place every fixture from its group names"),
        ]
        for i, (t, fn, tip) in enumerate(tools):
            b = QPushButton(t)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            gl.addWidget(b, i // 5, i % 5)
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
        self.venue_label.setText(f"Layout: <b>{show.venue}</b> ({len(show.rigging)} rigging pieces)"
                                 if show.venue else "Layout: automatic (from the group names)")
        self.cb_screen.setChecked(bool(show.screen))
        self.sw.setValue(show.screen.get("width", 10.0) if show.screen else 10.0)
        self.sh.setValue(show.screen.get("height", 3.8) if show.screen else 3.8)
        self.sw.setEnabled(bool(show.screen))
        self.sh.setEnabled(bool(show.screen))
        n_hidden = sum(1 for f in show.fixtures if f.hidden)
        self.cb_hidden.setText(f"Show hidden fixtures ({n_hidden})")
        self.cb_hidden.setEnabled(n_hidden > 0 or self.cb_hidden.isChecked())
        self.cb_rig.setChecked(bool(show.rigging))
        self.cb_rig.setEnabled(bool(show.rigging) or bool(show.venue))
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

    def apply_venue(self):
        from .. import venue
        show = self.engine.show
        if not venue.matches_gms(show) and QMessageBox.question(
                self, "Venue layout", "This show's groups do not fully match the GMS hall rig "
                "(PAR BELAKANG, PAR DEPAN, BEAM BEL, BEAM ATAS, STRB ATAS, STRB TOWER, PAR TOWER).\n"
                "Apply anyway? Fixtures that do not match are placed by type.") != QMessageBox.Yes:
            return
        notes = venue.apply_gms(show)
        self._done()
        if notes:
            QMessageBox.information(self, "Venue layout", "GMS hall layout applied.\n\n" + "\n".join(notes))

    def _screen(self, *_):
        if self._loading:
            return
        s = self.engine.show
        if self.cb_screen.isChecked():
            y = s.screen.get("y", s.stage_depth + 0.46) if s.screen else s.stage_depth + 0.46
            s.screen = {"width": self.sw.value(), "height": self.sh.value(), "z": 0.0, "y": y}
        else:
            s.screen = {}
        self.sw.setEnabled(bool(s.screen))
        self.sh.setEnabled(bool(s.screen))
        self.changed.emit()

    def _rig_toggled(self, on: bool):
        if self._loading:
            return
        s = self.engine.show
        if on and not s.rigging and s.venue:
            from .. import venue
            s.rigging = venue.rigging_gms()
        elif not on:
            s.rigging = []
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

    def _hide(self, on: bool):
        sel = self._need(1)
        if sel:
            for f in sel:
                f.hidden = on
            self._done()

    def auto(self):
        if QMessageBox.question(self, "Auto layout", "Re-place ALL fixtures from their group names?") \
                == QMessageBox.Yes:
            auto_layout(self.engine.show)
            self._done()
