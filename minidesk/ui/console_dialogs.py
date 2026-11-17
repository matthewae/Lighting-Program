"""Console style 'Edit Time' and 'Playback Parameters' dialogs (CODE MINI 1000T)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from ..engine import TIME_GROUPS
from ..model import FX_MODES, PB_DIRECTIONS, PRIORITIES, RELEASE_MODES, RUN_MODES, Playback

ORDER_DIRS = ["forward", "backward", "center_out", "outside_in", "random"]
ORDER_LABEL = {"forward": "Forward", "backward": "Backward", "center_out": "Centre Out",
               "outside_in": "Outside In", "random": "Random"}
BASE_COLS = ["Cue", "Delay In", "Fade In", "Out Delay", "Out Fade", "Trigger", "MIB", "Fixture Overlap",
             "Snap Percent", "Order Direction"]


def _fmt(v: float) -> str:
    return "-" if v is None or v < 0 else f"{v:.1f}s"


def _parse(txt: str, allow_unset=True) -> float | None:
    t = txt.strip().lower().rstrip("s%").strip()
    if t in ("", "-"):
        return None if allow_unset else 0.0
    try:
        return max(0.0, float(t.replace(",", ".")))
    except ValueError:
        return None if allow_unset else 0.0


class EditTimeDialog(QDialog):
    """Per cue timing like the console's Edit Time table. '-' = not set (uses the cue / global time)."""

    def __init__(self, pb: Playback, parent=None):
        super().__init__(parent)
        self.pb = pb
        self.setWindowTitle(f"Edit Time – Current Playback: {pb.console_label}  {pb.name}")
        self.resize(1180, 460)
        lay = QVBoxLayout(self)
        title = QLabel(f"Current Playback: {pb.console_label}   {pb.name}")
        title.setStyleSheet("background:#5fb7f0; color:#103060; font-weight:700; padding:6px;")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        cols = BASE_COLS + [f"{g} {k}" for g in TIME_GROUPS for k in ("Delay", "Fade")]
        self.table = QTableWidget(len(pb.steps), len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for r, st in enumerate(pb.steps):
            self._row(r, st)
        lay.addWidget(self.table, 1)
        hint = QLabel("Type seconds (e.g. 2.5) – '-' = not set.  Trigger: Go or Follow.  Fixture Overlap 100 % = "
                      "all fixtures together, lower = one after another in the Order Direction.  Snap Percent: when "
                      "gobo / colour wheel / prism jump during the fade.  Attribute times override the cue times "
                      "for that attribute (Dimmer, Shutter, Position, Colour, Gobo, Beam).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9aa0b3;")
        lay.addWidget(hint)
        tools = QHBoxLayout()
        b_glob = QPushButton("Attribute Time\nUse Global")
        b_glob.setToolTip("Clear the attribute times of the selected cues (use the cue times)")
        b_glob.clicked.connect(self._use_global)
        b_all = QPushButton("Copy selected cue\nto all cues")
        b_all.clicked.connect(self._copy_all)
        b_dir = QPushButton("Fixture Order\nDirection")
        b_dir.setToolTip("Cycle the order direction of the selected cues")
        b_dir.clicked.connect(self._cycle_dir)
        for b in (b_glob, b_dir, b_all):
            tools.addWidget(b)
        tools.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        tools.addWidget(bb)
        lay.addLayout(tools)

    def _row(self, r, st):
        t = self.table
        it = QTableWidgetItem(str(r + 1))
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        t.setItem(r, 0, it)
        do = st.delay_out if st.delay_out >= 0 else None
        fo = st.fade_out if st.fade_out >= 0 else st.fade
        for c, v in ((1, st.delay), (2, st.fade), (3, do), (4, fo)):
            t.setItem(r, c, QTableWidgetItem(_fmt(v)))
        trig = QComboBox()
        trig.addItems(["Go", "Follow"])
        trig.setCurrentIndex(1 if st.follow else 0)
        t.setCellWidget(r, 5, trig)
        mib = QCheckBox()
        mib.setChecked(st.mib)
        t.setCellWidget(r, 6, mib)
        t.setItem(r, 7, QTableWidgetItem(f"{st.overlap:.0f}%"))
        t.setItem(r, 8, QTableWidgetItem(f"{st.snap:.0f}"))
        od = QComboBox()
        for k in ORDER_DIRS:
            od.addItem(ORDER_LABEL[k], k)
        od.setCurrentIndex(max(0, ORDER_DIRS.index(st.order_dir) if st.order_dir in ORDER_DIRS else 0))
        t.setCellWidget(r, 9, od)
        for gi, g in enumerate(TIME_GROUPS):
            d, f = st.attr_times.get(g, (None, None))
            t.setItem(r, 10 + 2 * gi, QTableWidgetItem(_fmt(d)))
            t.setItem(r, 11 + 2 * gi, QTableWidgetItem(_fmt(f)))

    def _rows(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return rows or list(range(self.table.rowCount()))

    def _use_global(self):
        for r in self._rows():
            for c in range(10, self.table.columnCount()):
                self.table.item(r, c).setText("-")

    def _cycle_dir(self):
        for r in self._rows():
            w = self.table.cellWidget(r, 9)
            w.setCurrentIndex((w.currentIndex() + 1) % w.count())

    def _copy_all(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Edit Time", "Select a cue (row) first.")
            return
        src = rows[0]
        for r in range(self.table.rowCount()):
            if r == src:
                continue
            for c in range(1, self.table.columnCount()):
                if c in (5, 6, 9):
                    a, b = self.table.cellWidget(src, c), self.table.cellWidget(r, c)
                    if isinstance(a, QCheckBox):
                        b.setChecked(a.isChecked())
                    else:
                        b.setCurrentIndex(a.currentIndex())
                else:
                    self.table.item(r, c).setText(self.table.item(src, c).text())

    def _ok(self):
        t = self.table
        for r, st in enumerate(self.pb.steps):
            st.delay = _parse(t.item(r, 1).text(), False)
            st.fade = _parse(t.item(r, 2).text(), False)
            do = _parse(t.item(r, 3).text())
            st.delay_out = -1.0 if do is None else do
            fo = _parse(t.item(r, 4).text())
            st.fade_out = -1.0 if fo is None else fo
            st.follow = t.cellWidget(r, 5).currentIndex() == 1
            st.mib = t.cellWidget(r, 6).isChecked()
            st.overlap = min(100.0, _parse(t.item(r, 7).text(), False))
            st.snap = min(100.0, _parse(t.item(r, 8).text(), False))
            st.order_dir = t.cellWidget(r, 9).currentData()
            at = {}
            for gi, g in enumerate(TIME_GROUPS):
                d = _parse(t.item(r, 10 + 2 * gi).text())
                f = _parse(t.item(r, 11 + 2 * gi).text())
                if d is not None or f is not None:
                    at[g] = [d or 0.0, f or 0.0]
            st.attr_times = at
        self.accept()


class PlaybackParamsDialog(QDialog):
    """Console 'Playback Parameters' + the playback options of MiniDesk."""

    def __init__(self, pb: Playback, parent=None):
        super().__init__(parent)
        self.pb = pb
        self.setWindowTitle(f"Playback Parameters – {pb.console_label}  {pb.name}")
        f = QFormLayout(self)

        def combo(items: dict, cur: str):
            c = QComboBox()
            for k, v in items.items():
                c.addItem(v, k)
            c.setCurrentIndex(max(0, c.findData(cur)))
            return c

        self.release_mode = combo(RELEASE_MODES, pb.release_mode)
        self.fx_mode = combo(FX_MODES, pb.fx_mode)
        self.run_mode = combo(RUN_MODES, pb.run_mode)
        self.priority = combo(PRIORITIES, pb.priority)
        self.use_times = QCheckBox("Use Delay and Fade time")
        self.use_times.setChecked(pb.use_times)
        self.mode = combo({"chase": "Chase (steps run automatically)", "cuelist": "Cue list (GO for each cue)"},
                          pb.mode)
        self.direction = combo({d: d.capitalize() for d in PB_DIRECTIONS}, pb.direction)
        self.loop = QCheckBox("Loop at the end")
        self.loop.setChecked(pb.loop)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.02, 600)
        self.speed.setDecimals(2)
        self.speed.setSuffix(" s / step")
        self.speed.setValue(pb.speed)
        self.release = QDoubleSpinBox()
        self.release.setRange(0, 60)
        self.release.setDecimals(1)
        self.release.setSuffix(" s")
        self.release.setValue(pb.release)
        tips = {
            "Release Mode": "Release All Attribute: when the playback goes off everything is released.\n"
                            "Release Dimmer Only: the intensity goes, position / colour / beam stay.",
            "FX Size Speed": "What the fader does with the effects of this playback.",
            "Run Mode": "Time: steps follow their times.  Manual: only GO steps.  Beat: one step per TAP beat.",
            "Priority": "Higher priority playbacks win the LTP attributes over lower ones.",
        }
        for label, w in (("Release Mode", self.release_mode), ("FX Size Speed", self.fx_mode),
                         ("Run Mode", self.run_mode), ("Priority", self.priority), ("", self.use_times),
                         ("Playback type", self.mode), ("Direction", self.direction), ("", self.loop),
                         ("Chase speed", self.speed), ("Release fade", self.release)):
            if label in tips:
                w.setToolTip(tips[label])
            f.addRow(label, w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _ok(self):
        pb = self.pb
        pb.release_mode = self.release_mode.currentData()
        pb.fx_mode = self.fx_mode.currentData()
        pb.run_mode = self.run_mode.currentData()
        pb.priority = self.priority.currentData()
        pb.use_times = self.use_times.isChecked()
        pb.mode = self.mode.currentData()
        pb.direction = self.direction.currentData()
        pb.loop = self.loop.isChecked()
        pb.speed = self.speed.value()
        pb.release = self.release.value()
        self.accept()
