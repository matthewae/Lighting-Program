"""Cue / step editor for one playback (timing, order, values, playback options)."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..engine import Engine, PlaybackState
from ..model import PB_DIRECTIONS, Playback, Step


class StepValuesDialog(QDialog):
    """Edit the raw values of one cue: fixture / channel / value."""

    def __init__(self, engine: Engine, step: Step, parent=None):
        super().__init__(parent)
        self.engine, self.step = engine, step
        self.setWindowTitle(f"Cue values – {step.name}")
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Edit values (0–255). Select rows and press Delete row to remove a channel "
                             "from the cue (it is then not controlled by this cue)."))
        show = engine.show
        self.rows = []
        for fid in sorted(step.values):
            fx = show.fixture(fid)
            ft = show.types.get(fx.type_key) if fx else None
            for ch, v in sorted(step.values[fid].items()):
                cname = ft.channels[ch].name if ft and ch < len(ft.channels) else f"ch {ch + 1}"
                self.rows.append((fid, ch, f"{fid} {fx.name if fx else '?'}", cname, v))
        self.table = QTableWidget(len(self.rows), 3)
        self.table.setHorizontalHeaderLabels(["Fixture", "Channel", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for r, (_f, _c, fname, cname, v) in enumerate(self.rows):
            for c, txt in enumerate((fname, cname, str(v))):
                it = QTableWidgetItem(txt)
                if c < 2:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        lay.addWidget(self.table, 1)
        h = QHBoxLayout()
        bdel = QPushButton("Delete row(s)")
        bdel.clicked.connect(self._del)
        h.addWidget(bdel)
        h.addStretch(1)
        lay.addLayout(h)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _del(self):
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)
            del self.rows[r]

    def apply(self) -> None:
        vals: dict[int, dict[int, int]] = {}
        for r, (fid, ch, *_rest) in enumerate(self.rows):
            try:
                v = max(0, min(255, int(self.table.item(r, 2).text())))
            except (ValueError, AttributeError):
                continue
            vals.setdefault(fid, {})[ch] = v
        self.step.values = vals


class CueEditor(QWidget):
    changed = Signal()
    loadedToProgrammer = Signal()
    COLS = [("#", "Cue number (double-click = go)"), ("Name", "Cue name"),
            ("Delay in", "Seconds before the fade in starts"),
            ("Fade in", "Fade in time (0 = playback default fade)"),
            ("Delay out", "Seconds before intensity going down starts (-1 = same as delay in)"),
            ("Fade out", "Fade time for intensity going down (-1 = same as fade in)"),
            ("Hold", "Chase / follow: time on this cue before the next (-1 = playback speed)"),
            ("Follow", "Cuelist: go to the next cue automatically after fade + hold"),
            ("Fixtures", "Number of fixtures in the cue"), ("FX", "Effects in the cue")]
    FIELDS = {2: "delay", 3: "fade", 4: "delay_out", 5: "fade_out", 6: "hold"}

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.st: PlaybackState | None = None
        self.clip: list[Step] = []
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        head = QHBoxLayout()
        self.title = QLabel("No playback selected – click a playback name in the fader bar")
        self.title.setObjectName("title")
        head.addWidget(self.title, 1)
        self.now = QLabel("")
        self.now.setStyleSheet("color:#8fd18f;")
        head.addWidget(self.now)
        lay.addLayout(head)

        # transport
        tr = QHBoxLayout()
        for txt, fn, obj in (("◀ Back", lambda: self.st and self.engine.back(self.st), ""),
                             ("GO ▶", lambda: self.st and self.engine.go(self.st), "go"),
                             ("❚❚ Pause", lambda: self.st and self.engine.pause(self.st), ""),
                             ("■ Stop", lambda: self.st and self.engine.stop(self.st, fade=True), "danger")):
            b = QPushButton(txt)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            tr.addWidget(b)
        lay.addLayout(tr)

        g = QGroupBox("Playback options")
        grid = QGridLayout(g)
        self.e_name = QLineEdit()
        self.e_name.setMaxLength(16)
        self.e_name.editingFinished.connect(self._props)
        self.e_mode = QComboBox()
        self.e_mode.addItem("Chase (runs by itself)", "chase")
        self.e_mode.addItem("Cue list (GO for each cue)", "cuelist")
        self.e_mode.currentIndexChanged.connect(self._props)
        self.e_dir = QComboBox()
        self.e_dir.addItems(PB_DIRECTIONS)
        self.e_dir.currentTextChanged.connect(self._props)
        self.e_loop = QCheckBox("Loop at the end")
        self.e_loop.toggled.connect(self._props)
        self.e_speed = QDoubleSpinBox()
        self.e_speed.setRange(0.02, 600)
        self.e_speed.setSuffix(" s / step")
        self.e_speed.setDecimals(2)
        self.e_speed.valueChanged.connect(self._props)
        self.bpm = QLabel()
        self.b_tap = QPushButton("TAP")
        self.b_tap.setToolTip("Tap the beat 3–4 times to set the chase speed")
        self.b_tap.clicked.connect(self._tap)
        self.e_fade = QDoubleSpinBox()
        self.e_fade.setRange(0, 600)
        self.e_fade.setSuffix(" s")
        self.e_fade.setDecimals(2)
        self.e_fade.valueChanged.connect(self._props)
        self.e_xfade = QDoubleSpinBox()
        self.e_xfade.setRange(0, 100)
        self.e_xfade.setSuffix(" %")
        self.e_xfade.setToolTip("Chase crossfade as a percentage of the step time (0 = use cue fade times)")
        self.e_xfade.valueChanged.connect(self._props)
        self.e_release = QDoubleSpinBox()
        self.e_release.setRange(0, 600)
        self.e_release.setSuffix(" s")
        self.e_release.setToolTip("Fade out time when the playback is stopped with ■")
        self.e_release.valueChanged.connect(self._props)
        self.e_num = QLabel("")
        rows = [("Name", self.e_name, "Mode", self.e_mode),
                ("Direction", self.e_dir, "", self.e_loop),
                ("Chase speed", self.e_speed, "", self._hbox(self.b_tap, self.bpm)),
                ("Default fade", self.e_fade, "Chase crossfade", self.e_xfade),
                ("Release (stop fade)", self.e_release, "Origin", self.e_num)]
        for r, (l1, w1, l2, w2) in enumerate(rows):
            grid.addWidget(QLabel(l1), r, 0)
            grid.addWidget(w1, r, 1)
            grid.addWidget(QLabel(l2), r, 2)
            grid.addWidget(w2, r, 3)
        lay.addWidget(g)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLS])
        for i, c in enumerate(self.COLS):
            self.table.horizontalHeaderItem(i).setToolTip(c[1])
        hh = self.table.horizontalHeader()
        for c in range(len(self.COLS)):
            hh.setSectionResizeMode(c, QHeaderView.Stretch if c == 1 else QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellDoubleClicked.connect(lambda r, c: self._goto(r) if c in (0, 8, 9) else None)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.table, 1)

        b = QHBoxLayout()
        for text, fn, tip in (
                ("Go to cue", self._goto_sel, "Play the selected cue"),
                ("Load → programmer", self._load, "Copy the cue values/effects into the programmer"),
                ("Update from programmer", self._update, "Merge the programmer into the selected cue"),
                ("Edit values…", self._edit_values, "Edit fixture/channel values of the cue"),
                ("Insert empty", self._insert, "Insert an empty cue after the selected one"),
                ("Duplicate", self._duplicate, "Copy the selected cue(s)")):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        lay.addLayout(b)
        b2 = QHBoxLayout()
        for text, fn in (("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1)),
                         ("Copy", self._copy), ("Paste", self._paste), ("Delete cue", self._delete),
                         ("Merge cues → 1 scene", self._merge)):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b2.addWidget(btn)
        b2.addStretch(1)
        bn = QPushButton("New playback")
        bn.clicked.connect(self.new_playback)
        bd = QPushButton("Delete playback")
        bd.setObjectName("danger")
        bd.clicked.connect(self.delete_playback)
        b2.addWidget(bn)
        b2.addWidget(bd)
        lay.addLayout(b2)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._highlight_current)
        self.timer.start(200)
        self._enable(False)

    @staticmethod
    def _hbox(*ws):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for x in ws:
            h.addWidget(x)
        return w

    def _enable(self, on: bool):
        for w in (self.e_name, self.e_mode, self.e_dir, self.e_loop, self.e_speed, self.b_tap,
                  self.e_fade, self.e_xfade, self.e_release):
            w.setEnabled(on)

    # ------------------------------------------------------------------ bind
    def bind(self, st: PlaybackState | None) -> None:
        self.st = st
        self._loading = True
        pb = st.pb if st else None
        self._enable(pb is not None)
        if pb:
            self.title.setText(f"Playback {pb.number}: {pb.name}")
            self.e_name.setText(pb.name)
            self.e_mode.setCurrentIndex(0 if pb.mode == "chase" else 1)
            self.e_dir.setCurrentText(pb.direction)
            self.e_loop.setChecked(pb.loop)
            self.e_speed.setValue(pb.speed)
            self.e_fade.setValue(pb.fade)
            self.e_xfade.setValue(pb.xfade)
            self.e_release.setValue(pb.release)
            self.e_num.setText(f"{pb.bank}  {pb.source}")
            self.bpm.setText(f"{60 / max(pb.speed, 0.01):.0f} BPM")
        else:
            self.title.setText("No playback selected – click a playback name in the fader bar")
        self._fill()
        self._loading = False

    def _fill(self) -> None:
        self._loading = True
        pb = self.st.pb if self.st else None
        steps = pb.steps if pb else []
        self.table.setRowCount(len(steps))
        for r, s in enumerate(steps):
            fx = ", ".join(e.type for e in s.effects)
            vals = [str(r + 1), s.name, f"{s.delay:g}", f"{s.fade:g}", f"{s.delay_out:g}", f"{s.fade_out:g}",
                    f"{s.hold:g}", "", str(len(s.values)), fx or "–"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 7:
                    it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setCheckState(Qt.Checked if s.follow else Qt.Unchecked)
                elif c in (0, 8, 9):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        self._loading = False

    def _highlight_current(self) -> None:
        if not self.st:
            self.now.setText("")
            return
        st = self.st
        cur = st.index if st.running else -1
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                txt = ("▶ " if r == cur else "") + str(r + 1)
                if it.text() != txt:
                    it.setText(txt)
        self.table.blockSignals(False)
        if st.running:
            self.now.setText(f"{'❚❚ paused' if st.paused else '▶ running'}  cue {st.index + 1}/{len(st.pb.steps)}"
                             f"  level {round(st.effective_level * 100)}%")
        else:
            self.now.setText("stopped")

    # --------------------------------------------------------------- editing
    def _props(self, *_):
        if self._loading or not self.st:
            return
        pb = self.st.pb
        pb.name = self.e_name.text().strip() or pb.name
        pb.mode = self.e_mode.currentData()
        pb.direction = self.e_dir.currentText()
        pb.loop = self.e_loop.isChecked()
        pb.speed = self.e_speed.value()
        pb.fade = self.e_fade.value()
        pb.xfade = self.e_xfade.value()
        pb.release = self.e_release.value()
        self.bpm.setText(f"{60 / max(pb.speed, 0.01):.0f} BPM")
        self.title.setText(f"Playback {pb.number}: {pb.name}")
        self.changed.emit()

    def _tap(self):
        if self.st:
            sp = self.engine.tap(self.st)
            self._loading = True
            self.e_speed.setValue(sp)
            self._loading = False
            self.bpm.setText(f"{60 / max(sp, 0.01):.0f} BPM")
            self.changed.emit()

    def _item_changed(self, it: QTableWidgetItem) -> None:
        if self._loading or not self.st or it.column() in (0, 8, 9):
            return
        s = self.st.pb.steps[it.row()]
        try:
            if it.column() == 1:
                s.name = it.text()
            elif it.column() == 7:
                s.follow = it.checkState() == Qt.Checked
            elif it.column() in self.FIELDS:
                v = float(it.text())
                field = self.FIELDS[it.column()]
                if field in ("delay", "fade"):
                    v = max(0.0, v)
                setattr(s, field, v)
        except ValueError:
            pass
        self.changed.emit()

    def _rows(self) -> list[int]:
        if not self.st:
            return []
        return sorted({i.row() for i in self.table.selectedIndexes() if 0 <= i.row() < len(self.st.pb.steps)})

    def _sel(self) -> int:
        r = self.table.currentRow()
        return r if self.st and 0 <= r < len(self.st.pb.steps) else -1

    def _goto(self, r: int) -> None:
        if self.st and 0 <= r < len(self.st.pb.steps):
            self.engine.goto(self.st, r)

    def _goto_sel(self):
        self._goto(self._sel())

    def _load(self):
        r = self._sel()
        if r < 0:
            return
        s = self.st.pb.steps[r]
        with self.engine.lock:
            for f, chans in s.values.items():
                self.engine.programmer.setdefault(f, {}).update(chans)
            for e in s.effects:
                self.engine.add_effect(copy.deepcopy(e))
            self.engine.select(list(s.values) or sorted({f for e in s.effects for f in e.fixtures}))
        self.loadedToProgrammer.emit()

    def _update(self):
        r = self._sel()
        if r < 0:
            return
        if self.engine.programmer_empty:
            QMessageBox.information(self, "Update", "The programmer is empty.")
            return
        mode = QMessageBox.question(self, "Update cue", "Merge the programmer into this cue?\n"
                                    "Yes = merge (keep other values)   No = replace the cue completely",
                                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if mode == QMessageBox.Cancel:
            return
        self.engine.store(self.st.pb, "merge" if mode == QMessageBox.Yes else "overwrite", index=r)
        self._fill()
        self.changed.emit()

    def _edit_values(self):
        r = self._sel()
        if r < 0:
            return
        d = StepValuesDialog(self.engine, self.st.pb.steps[r], self)
        if d.exec():
            with self.engine.lock:
                d.apply()
            self._fill()
            self.changed.emit()

    def _insert(self):
        if not self.st:
            return
        r = self._sel()
        steps = self.st.pb.steps
        steps.insert(r + 1 if r >= 0 else len(steps), Step(name=f"Cue {len(steps) + 1}"))
        self._fill()
        self.table.selectRow(r + 1 if r >= 0 else len(steps) - 1)
        self.changed.emit()

    def _duplicate(self):
        rows = self._rows()
        if not rows:
            return
        steps = self.st.pb.steps
        for i, r in enumerate(rows):
            c = copy.deepcopy(steps[r + i])
            c.name = (c.name or "Cue") + " copy"
            steps.insert(r + i + 1, c)
        self._fill()
        self.changed.emit()

    def _copy(self):
        self.clip = [copy.deepcopy(self.st.pb.steps[r]) for r in self._rows()]

    def _paste(self):
        if not self.st or not self.clip:
            return
        r = self._sel()
        pos = r + 1 if r >= 0 else len(self.st.pb.steps)
        for i, s in enumerate(self.clip):
            self.st.pb.steps.insert(pos + i, copy.deepcopy(s))
        self._fill()
        self.changed.emit()

    def _delete(self):
        rows = self._rows()
        if not rows:
            return
        for r in reversed(rows):
            del self.st.pb.steps[r]
        if self.st.index >= len(self.st.pb.steps):
            self.engine.stop(self.st)
        self._fill()
        self.changed.emit()

    def _move(self, d: int):
        r = self._sel()
        steps = self.st.pb.steps if self.st else []
        if r < 0 or not (0 <= r + d < len(steps)):
            return
        steps[r], steps[r + d] = steps[r + d], steps[r]
        self._fill()
        self.table.selectRow(r + d)
        self.changed.emit()

    def _merge(self):
        if not self.st or len(self.st.pb.steps) < 2:
            return
        merged = Step(name="Scene")
        for s in self.st.pb.steps:
            for f, chans in s.values.items():
                merged.values.setdefault(f, {}).update(chans)
            merged.fade = max(merged.fade, s.fade)
            merged.effects += s.effects
        self.engine.stop(self.st)
        self.st.pb.steps = [merged]
        self.st.pb.mode = "cuelist"
        self.bind(self.st)
        self.changed.emit()

    def _menu(self, pos):
        m = QMenu(self)
        for text, fn in (("Go to cue", self._goto_sel), ("Load → programmer", self._load),
                         ("Update from programmer", self._update), ("Edit values…", self._edit_values),
                         ("Insert empty", self._insert), ("Duplicate", self._duplicate), ("Copy", self._copy),
                         ("Paste", self._paste), ("Delete", self._delete)):
            m.addAction(text, fn)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def new_playback(self):
        show = self.engine.show
        name, ok = QInputDialog.getText(self, "New playback", "Name:")
        if not ok:
            return
        num = max((p.number for p in show.playbacks), default=0) + 1
        pb = Playback(name=(name or f"Playback {num}")[:16], number=num, bank="User", mode="cuelist")
        show.playbacks.append(pb)
        self.engine.rebuild_patch()
        self.bind(self.engine.state_for(pb))
        self.changed.emit()

    def delete_playback(self):
        if not self.st:
            return
        if self.st.pb.slot >= 0:
            QMessageBox.information(self, "Delete", "This playback comes from the console file and cannot be "
                                    "deleted there. Delete its cues instead, or rename it.")
            return
        if QMessageBox.question(self, "Delete", f"Delete playback '{self.st.pb.name}'?") != QMessageBox.Yes:
            return
        self.engine.stop(self.st)
        self.engine.show.playbacks.remove(self.st.pb)
        self.engine.rebuild_patch()
        self.bind(None)
        self.changed.emit()
