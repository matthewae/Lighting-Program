"""Fixture & group selection sheet (like the dot2 fixture/group views)."""
from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QGridLayout, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget, QHBoxLayout)

from ..engine import Engine
from ..model import Group
from ..vis_state import compute
from .fixture_models import draw_icon


class FixtureGrid(QWidget):
    clicked = Signal(int, bool, bool)    # fid, ctrl, shift
    TILE_W, TILE_H = 104, 58

    def __init__(self, engine: Engine, dmx_source: Callable, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.dmx_source = dmx_source
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(100)
        self.setMinimumHeight(120)

    def cols(self) -> int:
        return max(1, self.width() // self.TILE_W)

    def relayout(self) -> None:
        n = len(self.engine.show.fixtures)
        rows = (n + self.cols() - 1) // self.cols()
        self.setMinimumHeight(max(120, rows * self.TILE_H + 4))

    def resizeEvent(self, e):
        self.relayout()
        super().resizeEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        unis = self.dmx_source() or {}
        now = time.time()
        show = self.engine.show
        sel = set(self.engine.selection)
        f1, f2 = QFont(), QFont()
        f1.setPointSize(8)
        f1.setBold(True)
        f2.setPointSize(7)
        cols = self.cols()
        for i, fx in enumerate(show.fixtures):
            r = QRectF((i % cols) * self.TILE_W + 2, (i // cols) * self.TILE_H + 2,
                       self.TILE_W - 4, self.TILE_H - 4)
            ft = show.types.get(fx.type_key)
            st = compute(fx, ft, unis.get(fx.universe, b""), now) if ft else None
            p.setPen(QPen(QColor(255, 200, 0), 2) if fx.fid in sel else QPen(QColor(50, 52, 64), 1))
            p.setBrush(QColor(28, 30, 38) if fx.patched else QColor(40, 22, 22))
            p.drawRoundedRect(r, 4, 4)
            if st and st.intensity > 0.01:
                c = QColor(*st.colour)
                c.setAlpha(int(60 + 195 * st.intensity))
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(r.x() + 3, r.bottom() - 9, r.width() - 6, 6), 2, 2)
            if ft:
                lit = QColor(*st.colour) if st and st.intensity > 0.02 else None
                draw_icon(p, QRectF(r.right() - 30, r.top() + 14, 26, 26), ft.kind, lit)
            prog = fx.fid in self.engine.programmer
            p.setPen(QColor(255, 80, 80) if prog else QColor(140, 145, 160))
            p.setFont(f1)
            p.drawText(r.adjusted(5, 3, -4, 0), Qt.AlignLeft | Qt.AlignTop, str(fx.fid))
            p.setFont(f2)
            p.setPen(QColor(205, 205, 215))
            p.drawText(r.adjusted(5, 18, -32, 0), Qt.AlignLeft | Qt.AlignTop, fx.name[:12])
            p.setPen(QColor(110, 112, 128))
            addr = f"{fx.universe + 1}.{fx.address:03d}" if fx.patched else "--"
            p.drawText(r.adjusted(0, 3, -5, 0), Qt.AlignRight | Qt.AlignTop, addr)
        p.end()

    def mousePressEvent(self, e):
        pos = e.position()
        i = int(pos.y() // self.TILE_H) * self.cols() + int(pos.x() // self.TILE_W)
        if int(pos.x() // self.TILE_W) >= self.cols():
            return
        fixtures = self.engine.show.fixtures
        if 0 <= i < len(fixtures):
            self.clicked.emit(fixtures[i].fid, bool(e.modifiers() & Qt.ControlModifier),
                              bool(e.modifiers() & Qt.ShiftModifier))


class FixtureSheet(QWidget):
    selectionChanged = Signal()

    def __init__(self, engine: Engine, dmx_source: Callable, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._last = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        hdr = QHBoxLayout()
        t = QLabel("Groups")
        t.setObjectName("title")
        hdr.addWidget(t)
        hdr.addStretch(1)
        self.btn_store_group = QPushButton("Store selection as group")
        self.btn_store_group.clicked.connect(self.store_group)
        hdr.addWidget(self.btn_store_group)
        lay.addLayout(hdr)
        self.group_box = QWidget()
        self.group_lay = QGridLayout(self.group_box)
        self.group_lay.setContentsMargins(0, 0, 0, 0)
        self.group_lay.setSpacing(3)
        lay.addWidget(self.group_box)
        t2 = QLabel("Fixtures  (click = select, Ctrl = add/remove, Shift = range)")
        t2.setObjectName("title")
        lay.addWidget(t2)
        self.grid = FixtureGrid(engine, dmx_source)
        self.grid.clicked.connect(self.on_click)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.grid)
        sc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(sc, 1)
        self.rebuild()

    def rebuild(self) -> None:
        while self.group_lay.count():
            w = self.group_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, g in enumerate(self.engine.show.groups):
            num = g.slot + 1 if g.slot >= 0 else i + 1
            b = QPushButton(f"{num}  {g.name}\n({len(g.fixtures)})")
            b.setMinimumHeight(40)
            b.setToolTip("Click: select   Ctrl+click: add   Right-click: rename / update / delete")
            b.clicked.connect(lambda _=False, grp=g: self.select_group(grp))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, grp=g, btn=b: self._group_menu(grp, btn, pos))
            self.group_lay.addWidget(b, i // 6, i % 6)
        self.grid.relayout()
        self.grid.update()

    def select_group(self, g: Group) -> None:
        from PySide6.QtWidgets import QApplication
        add = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if add:
            for f in g.fixtures:
                if f not in self.engine.selection:
                    self.engine.selection.append(f)
        else:
            self.engine.select(list(g.fixtures))
        self.selectionChanged.emit()
        self.grid.update()

    def on_click(self, fid: int, ctrl: bool, shift: bool) -> None:
        fixtures = [f.fid for f in self.engine.show.fixtures]
        if shift and self._last in fixtures:
            a, b = sorted((fixtures.index(self._last), fixtures.index(fid)))
            self.engine.select(fixtures[a:b + 1], add=False)
        else:
            self.engine.select([fid], add=ctrl)
        self._last = fid
        self.selectionChanged.emit()
        self.grid.update()

    groupsChanged = Signal()

    def _group_menu(self, g: Group, btn, pos) -> None:
        m = QMenu(self)
        a_ren = m.addAction("Rename…")
        a_rep = m.addAction("Replace members with current selection")
        a_add = m.addAction("Add current selection")
        a_del = m.addAction("Delete group")
        a = m.exec(btn.mapToGlobal(pos))
        show = self.engine.show
        if a == a_ren:
            name, ok = QInputDialog.getText(self, "Rename group", "Name:", text=g.name)
            if ok and name.strip():
                g.name = name.strip()[:16]
        elif a == a_rep and self.engine.selection:
            g.fixtures = list(self.engine.selection)
        elif a == a_add:
            g.fixtures += [f for f in self.engine.selection if f not in g.fixtures]
        elif a == a_del:
            if QMessageBox.question(self, "Delete", f"Delete group '{g.name}'?") != QMessageBox.Yes:
                return
            show.groups.remove(g)
        else:
            return
        self.rebuild()
        self.groupsChanged.emit()

    def store_group(self) -> None:
        if not self.engine.selection:
            return
        name, ok = QInputDialog.getText(self, "Store group", "Group name (max 16 characters):")
        if ok and name.strip():
            self.engine.show.groups.append(Group(name=name.strip()[:16], fixtures=list(self.engine.selection)))
            self.rebuild()
            self.groupsChanged.emit()
