"""Cue / step editor for one playback."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
                               QInputDialog)

from ..engine import Engine, PlaybackState
from ..model import Playback, Step


class CueEditor(QWidget):
    changed = Signal()
    loadedToProgrammer = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.st: PlaybackState | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.title = QLabel("No playback selected – click an executor name")
        self.title.setObjectName("title")
        lay.addWidget(self.title)
        form = QFormLayout()
        self.e_name = QLineEdit()
        self.e_name.editingFinished.connect(self._props)
        self.e_mode = QComboBox()
        self.e_mode.addItems(["chase", "cuelist"])
        self.e_mode.currentTextChanged.connect(self._props)
        self.e_speed = QDoubleSpinBox()
        self.e_speed.setRange(0.02, 600)
        self.e_speed.setSuffix(" s / step")
        self.e_speed.setDecimals(2)
        self.e_speed.valueChanged.connect(self._props)
        self.e_fade = QDoubleSpinBox()
        self.e_fade.setRange(0, 600)
        self.e_fade.setSuffix(" s")
        self.e_fade.setDecimals(2)
        self.e_fade.valueChanged.connect(self._props)
        self.e_num = QLabel("")
        form.addRow("Name", self.e_name)
        form.addRow("Mode", self.e_mode)
        form.addRow("Chase speed", self.e_speed)
        form.addRow("Default fade", self.e_fade)
        form.addRow("Origin", self.e_num)
        lay.addLayout(form)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Name", "Fade (s)", "Hold (s, -1=speed)", "Fixtures"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellDoubleClicked.connect(lambda r, c: self._goto(r) if c in (0, 4) else None)
        lay.addWidget(self.table, 1)

        b = QHBoxLayout()
        for text, fn in (("Go to step", self._goto_sel), ("Load → programmer", self._load),
                         ("Delete step", self._delete), ("▲", lambda: self._move(-1)),
                         ("▼", lambda: self._move(1)), ("Merge steps → 1 scene", self._merge)):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        lay.addLayout(b)
        b2 = QHBoxLayout()
        bn = QPushButton("New playback")
        bn.clicked.connect(self.new_playback)
        bd = QPushButton("Delete playback")
        bd.setObjectName("danger")
        bd.clicked.connect(self.delete_playback)
        b2.addWidget(bn)
        b2.addWidget(bd)
        b2.addStretch(1)
        lay.addLayout(b2)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._highlight_current)
        self.timer.start(200)
        self._loading = False

    # ------------------------------------------------------------------ bind
    def bind(self, st: PlaybackState | None) -> None:
        self.st = st
        self._loading = True
        pb = st.pb if st else None
        for w in (self.e_name, self.e_mode, self.e_speed, self.e_fade):
            w.setEnabled(pb is not None)
        if pb:
            self.title.setText(f"Executor {pb.number}: {pb.name}")
            self.e_name.setText(pb.name)
            self.e_mode.setCurrentText(pb.mode)
            self.e_speed.setValue(pb.speed)
            self.e_fade.setValue(pb.fade)
            self.e_num.setText(f"{pb.bank}  {pb.source}")
        self._fill()
        self._loading = False

    def _fill(self) -> None:
        self._loading = True
        pb = self.st.pb if self.st else None
        steps = pb.steps if pb else []
        self.table.setRowCount(len(steps))
        for r, s in enumerate(steps):
            vals = [str(r + 1), s.name, f"{s.fade:g}", f"{s.hold:g}", str(len(s.values))]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (0, 4):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        self._loading = False

    def _highlight_current(self) -> None:
        if not self.st:
            return
        cur = self.st.index if self.st.running else -1
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setText(("▶ " if r == cur else "") + str(r + 1))

    # --------------------------------------------------------------- editing
    def _props(self, *_):
        if self._loading or not self.st:
            return
        pb = self.st.pb
        pb.name = self.e_name.text() or pb.name
        pb.mode = self.e_mode.currentText()
        pb.speed = self.e_speed.value()
        pb.fade = self.e_fade.value()
        self.title.setText(f"Executor {pb.number}: {pb.name}")
        self.changed.emit()

    def _item_changed(self, it: QTableWidgetItem) -> None:
        if self._loading or not self.st:
            return
        s = self.st.pb.steps[it.row()]
        try:
            if it.column() == 1:
                s.name = it.text()
            elif it.column() == 2:
                s.fade = max(0.0, float(it.text()))
            elif it.column() == 3:
                s.hold = float(it.text())
        except ValueError:
            pass
        self.changed.emit()

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
            self.engine.select(list(s.values))
        self.loadedToProgrammer.emit()

    def _delete(self):
        r = self._sel()
        if r < 0:
            return
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
        self.engine.stop(self.st)
        self.st.pb.steps = [merged]
        self.st.pb.mode = "cuelist"
        self.bind(self.st)
        self.changed.emit()

    def new_playback(self):
        show = self.engine.show
        name, ok = QInputDialog.getText(self, "New playback", "Name:")
        if not ok:
            return
        num = max((p.number for p in show.playbacks), default=0) + 1
        pb = Playback(name=name or f"Playback {num}", number=num, bank="User", mode="cuelist")
        show.playbacks.append(pb)
        self.engine.rebuild_patch()
        self.bind(self.engine.state_for(pb))
        self.changed.emit()

    def delete_playback(self):
        if not self.st:
            return
        if QMessageBox.question(self, "Delete", f"Delete playback '{self.st.pb.name}'?") != QMessageBox.Yes:
            return
        self.engine.stop(self.st)
        self.engine.show.playbacks.remove(self.st.pb)
        self.engine.rebuild_patch()
        self.bind(None)
        self.changed.emit()
