"""DMX channel monitor (512 values of one universe)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget


class DmxGrid(QWidget):
    COLS = 32

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = bytes(512)
        self.owner: dict[int, int] = {}
        self.setMinimumSize(32 * 28, 16 * 26)

    def paintEvent(self, e):
        p = QPainter(self)
        cw = self.width() / self.COLS
        ch = self.height() / (512 / self.COLS)
        f = QFont()
        f.setPointSize(7)
        p.setFont(f)
        for i in range(512):
            r = QRectF((i % self.COLS) * cw, (i // self.COLS) * ch, cw - 1, ch - 1)
            v = self.data[i] if i < len(self.data) else 0
            base = QColor(30, 34, 46) if self.owner.get(i, 0) % 2 else QColor(22, 24, 32)
            if i not in self.owner:
                base = QColor(14, 14, 18)
            p.fillRect(r, base)
            if v:
                h = r.height() * v / 255
                p.fillRect(QRectF(r.x(), r.bottom() - h, r.width(), h), QColor(180, 130, 20, 160))
            p.setPen(QColor(90, 92, 105))
            p.drawText(r.adjusted(2, 1, 0, 0), Qt.AlignLeft | Qt.AlignTop, str(i + 1))
            p.setPen(QColor(230, 230, 235) if v else QColor(70, 70, 80))
            p.drawText(r.adjusted(0, 0, -2, -1), Qt.AlignRight | Qt.AlignBottom, str(v))
        p.end()


class DmxMonitor(QWidget):
    def __init__(self, sources: dict[str, Callable[[], dict[int, bytes]]], show_getter, parent=None):
        super().__init__(parent)
        self.sources = sources
        self.show_getter = show_getter
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        top.addWidget(QLabel("Source"))
        self.src = QComboBox()
        self.src.addItems(list(sources))
        top.addWidget(self.src)
        top.addWidget(QLabel("Universe"))
        self.uni = QSpinBox()
        self.uni.setRange(1, 64)
        top.addWidget(self.uni)
        top.addStretch(1)
        lay.addLayout(top)
        self.grid = DmxGrid()
        lay.addWidget(self.grid, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)

    def refresh(self) -> None:
        if not self.isVisible():
            return
        unis = self.sources[self.src.currentText()]() or {}
        u = self.uni.value() - 1
        self.grid.data = bytes(unis.get(u, bytes(512)))
        show = self.show_getter()
        owner = {}
        for fx in show.fixtures:
            if fx.patched and fx.universe == u:
                for i in range(len(show.ftype(fx).channels)):
                    owner[fx.address - 1 + i] = fx.fid
        self.grid.owner = owner
        self.grid.update()
