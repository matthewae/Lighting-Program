"""Sidebar navigation (icon + label) with a stacked page area – replaces a crowded tab bar."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QListView, QListWidget, QListWidgetItem, QStackedWidget, QWidget

from .icons import icon


class NavTabs(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.list = QListWidget()
        self.list.setObjectName("nav")
        self.list.setViewMode(QListView.IconMode)
        self.list.setFlow(QListView.TopToBottom)
        self.list.setMovement(QListView.Static)
        self.list.setIconSize(QSize(24, 24))
        self.list.setGridSize(QSize(96, 64))
        self.list.setFixedWidth(102)
        self.list.setSpacing(0)
        self.list.setWrapping(False)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.stack = QStackedWidget()
        lay.addWidget(self.list)
        lay.addWidget(self.stack, 1)
        self.list.currentRowChanged.connect(self._changed)

    def _changed(self, i: int) -> None:
        if 0 <= i < self.stack.count():
            self.stack.setCurrentIndex(i)
            self.currentChanged.emit(i)

    def addTab(self, w: QWidget, label: str, icon_name: str = "help") -> int:
        it = QListWidgetItem(icon(icon_name, "#c9ccd6"), label)
        it.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        it.setSizeHint(QSize(96, 64))
        self.list.addItem(it)
        self.stack.addWidget(w)
        if self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        return self.stack.count() - 1

    def setCurrentIndex(self, i: int) -> None:
        self.list.setCurrentRow(i)

    def currentIndex(self) -> int:
        return self.list.currentRow()

    def count(self) -> int:
        return self.stack.count()
