"""LIVE SHOW page of the CODE MINI 1000T (compact layout, fits without scrolling).

Fixtures (20 per page), Groups (15 per page, console slots), Presets (20 per page),
Fixture Open/Full, Fixture Align, Even/Odd, Find, Locate, the attribute keys
(Dimmer, Tilt/Pan, Colour, Colour Mix, Gobo1, Gobo2, Beam, Effect, Control) and the
encoder wheels A / B / C labelled with the channel names of the console library.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QBoxLayout, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)

from .. import console as K
from ..engine import Engine

_T = "font-size:8pt; padding:0px 2px;"
FIX_BTN = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2f6fd6, stop:1 #123a8c);"
           " color:white; border:1px solid #0d2a66; %s }" % _T)
FIX_SEL = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #bfe6ff, stop:1 #5fb7f0);"
           " color:#103060; border:1px solid #9fd6ff; font-weight:600; %s }" % _T)
GRP_BTN = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #9a7a18, stop:1 #4d3a08);"
           " color:white; border:1px solid #2d2205; font-weight:600; %s }" % _T)
GRP_SEL = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fff36a, stop:1 #f2d21a);"
           " color:#4a4a7a; border:1px solid #fff9b0; font-weight:600; %s }" % _T)
PRE_BTN = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2e8a3e, stop:1 #10501d);"
           " color:white; border:1px solid #0b3a14; font-weight:600; %s }" % _T)
EMPTY = "QPushButton { background:#24262e; color:#5d6070; border:1px solid #2c2f3a; %s }" % _T
KEY_BTN = "QPushButton { background:#1a1b20; color:#ff6a5a; border:1px solid #3a1515; font-weight:600; %s }" % _T
KEY_ON = "QPushButton { background:#16301c; color:#5cff7a; border:1px solid #2f7a3c; font-weight:700; %s }" % _T
TILE_H = 26


def _bar(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("bar")
    lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return lb


def _small(text: str, fn, tip: str = "", w: int = 0) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(22)
    b.setStyleSheet("padding:1px 6px;")
    if w:
        b.setFixedWidth(w)
    if tip:
        b.setToolTip(tip)
    b.clicked.connect(fn)
    return b


def _regrid(grid: QGridLayout, widgets: list, cols: int) -> None:
    for w in widgets:
        grid.removeWidget(w)
    for i, w in enumerate(widgets):
        grid.addWidget(w, i // cols, i % cols)


class Encoder(QWidget):
    """Encoder wheel: '<name>  50% (128)', a slider (turn = relative move) and -/+ buttons."""

    def __init__(self, live: "LiveShow", wheel: int):
        super().__init__()
        self.live, self.wheel = live, wheel
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.title = QLabel("")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("background:#000; color:white; font-weight:600; padding:1px; border-radius:3px;")
        lay.addWidget(self.title)
        row = QHBoxLayout()
        row.setSpacing(2)
        row.addWidget(_small("−", lambda: self.live.turn(self.wheel, -1), "−1", 24))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 255)
        self._last = 0
        self.slider.valueChanged.connect(self._moved)
        row.addWidget(self.slider, 1)
        row.addWidget(_small("+", lambda: self.live.turn(self.wheel, 1), "+1", 24))
        lay.addLayout(row)

    def _moved(self, v):
        d, self._last = v - self._last, v
        if d:
            self.live.turn(self.wheel, d)

    def set_info(self, info):
        letter = "ABC"[self.wheel]
        if info is None:
            self.title.setText(f"{letter}  –")
            self.slider.setEnabled(False)
            return
        self.slider.setEnabled(True)
        self.title.setText(f"{letter}  {info[0]}   {K.fmt_value(info[1])}")
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(info[1])
            self.slider.blockSignals(False)
            self._last = info[1]


class LiveShow(QWidget):
    selectionChanged = Signal()
    programmerChanged = Signal()
    storeRequested = Signal()
    effectsRequested = Signal()
    editTimeRequested = Signal()
    paramsRequested = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.fpage = self.gpage = self.ppage = 0
        self.key = "Dimmer"
        self.kpage = 0
        self.group_sel = None
        self.base_selection: list[int] = []
        self._wide = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 2)
        outer.setSpacing(4)

        # header: title, current playback, actions
        head = QHBoxLayout()
        t = QLabel("LIVE SHOW")
        t.setObjectName("title")
        head.addWidget(t)
        self.cur_lbl = QLabel("")
        self.cur_lbl.setStyleSheet("color:#9ad0ff;")
        head.addWidget(self.cur_lbl)
        self.info_lbl = QLabel("")
        self.info_lbl.setStyleSheet("color:#9aa0b3; font-size:8pt;")
        head.addWidget(self.info_lbl, 1)
        for text, sig, tip in (("Playback Param.", self.paramsRequested, "Playback Parameters of the current playback"),
                               ("Edit Time", self.editTimeRequested, "Edit Time of the current playback"),
                               ("Effects", self.effectsRequested, "Effect Select (console effect library)")):
            head.addWidget(_small(text, sig.emit, tip))
        b_store = _small("Store…", self.storeRequested.emit, "Store the programmer into a cue")
        b_store.setObjectName("go")
        head.addWidget(b_store)
        b_clr = _small("Clear", self._clear, "Clear the programmer (values, effects and selection)")
        b_clr.setObjectName("danger")
        head.addWidget(b_clr)
        outer.addLayout(head)

        body = QBoxLayout(QBoxLayout.LeftToRight)
        body.setSpacing(6)
        self._body = body
        outer.addLayout(body, 1)
        left = QVBoxLayout()
        left.setSpacing(2)
        body.addLayout(left, 5)

        # fixtures
        frow = QHBoxLayout()
        self.f_title = _bar("Fixtures - 1")
        frow.addWidget(self.f_title, 1)
        frow.addWidget(_small("UP", lambda: self._fpage(-1), "Previous fixture page", 46))
        frow.addWidget(_small("DOWN", lambda: self._fpage(1), "Next fixture page", 56))
        left.addLayout(frow)
        fg = QGridLayout()
        fg.setSpacing(2)
        self.f_btns = []
        for i in range(20):
            b = self._tile(lambda _=False, k=i: self._fixture(k))
            fg.addWidget(b, i // 5, i % 5)
            self.f_btns.append(b)
        left.addLayout(fg)
        ctl = QHBoxLayout()
        ctl.setSpacing(3)
        ctl.addWidget(_small("Fixture Open/Full", self._open_full, "Selected fixtures: intensity full, shutter open"))
        self.b_align = _small("Fixture Align =Off", self._align,
                              "On: the wheels give every selected fixture the same value\n"
                              "Off: the wheels move every fixture relative to its own value")
        ctl.addWidget(self.b_align)
        ctl.addWidget(_small("Even/Odd", self._even_odd, "Cycle the selection: all → odd → even → all"))
        self.b_find = _small("Find", lambda: None, "Highlight the selected fixtures (open white, full)")
        self.b_find.setCheckable(True)
        self.b_find.toggled.connect(self._find)
        ctl.addWidget(self.b_find)
        ctl.addWidget(_small("Locate", self._locate, "Locate: full, open white, pan/tilt centre"))
        left.addLayout(ctl)

        # groups
        grow = QHBoxLayout()
        self.g_title = _bar("Groups - 1")
        grow.addWidget(self.g_title, 1)
        grow.addWidget(_small("◀", lambda: self._gpage(-1), "Previous group page", 30))
        grow.addWidget(_small("▶", lambda: self._gpage(1), "Next group page", 30))
        left.addLayout(grow)
        gg = QGridLayout()
        gg.setSpacing(2)
        self.g_btns = []
        for i in range(15):
            b = self._tile(lambda _=False, k=i: self._group(k))
            gg.addWidget(b, i // 5, i % 5)
            self.g_btns.append(b)
        left.addLayout(gg)

        # attribute keys + wheels
        keys = QHBoxLayout()
        keys.setSpacing(2)
        self.k_btns = {}
        for k in K.KEYS:
            b = QPushButton(k)
            b.setFixedHeight(22)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, kk=k: self._key(kk))
            keys.addWidget(b)
            self.k_btns[k] = b
        left.addLayout(keys)
        wl = QHBoxLayout()
        wl.setSpacing(6)
        self.encoders = [Encoder(self, w) for w in range(3)]
        for e in self.encoders:
            wl.addWidget(e)
        left.addLayout(wl)
        left.addStretch(1)

        # presets
        right = QVBoxLayout()
        right.setSpacing(3)
        body.addLayout(right, 2)
        prow = QHBoxLayout()
        self.p_title = _bar("Presets - 1")
        prow.addWidget(self.p_title, 1)
        prow.addWidget(_small("◀", lambda: self._ppage(-1), "Previous preset page", 30))
        prow.addWidget(_small("▶", lambda: self._ppage(1), "Next preset page", 30))
        right.addLayout(prow)
        self.p_grid = QGridLayout()
        self.p_grid.setSpacing(2)
        self.p_btns = []
        for i in range(20):
            b = self._tile(lambda _=False, k=i: self._preset(k), h=20)
            self.p_btns.append(b)
        right.addLayout(self.p_grid)
        right.addStretch(1)
        self._relayout()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sync_wheels)
        self.timer.start(200)
        self.refresh()

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _tile(fn, h=TILE_H):
        b = QPushButton()
        b.setFixedHeight(h)
        b.setMinimumWidth(40)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        b.clicked.connect(fn)
        return b

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        wide = self.width() >= 980
        if wide == self._wide:
            return
        self._wide = wide
        self._body.setDirection(QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom)
        _regrid(self.p_grid, self.p_btns, 2 if wide else 10)

    def _fixtures(self):
        return sorted(self.engine.show.fixtures, key=lambda f: f.fid)

    def _groups_by_slot(self):
        out = {g.slot: g for g in self.engine.show.groups if g.slot >= 0}
        free = 0
        for g in self.engine.show.groups:          # groups made here: first free slots
            if g.slot < 0:
                while free in out:
                    free += 1
                out[free] = g
        return out

    def _presets_by_slot(self):
        out = {p.slot: p for p in self.engine.show.presets if p.slot >= 0}
        free = 0
        for p in self.engine.show.presets:
            if p.slot < 0:
                while free in out:
                    free += 1
                out[free] = p
        return out

    def set_current_playback(self, pb) -> None:
        self.cur_lbl.setText(f"  Current Playback: {pb.console_label}  {pb.name}" if pb else "")

    # ------------------------------------------------------------- actions
    def _changed_sel(self):
        self.base_selection = list(self.engine.selection)
        self.engine.even_odd_state = 0
        self.refresh()
        self.selectionChanged.emit()

    def _fixture(self, k):
        fx = self._fixtures()
        i = self.fpage * 20 + k
        if i < len(fx):
            self.engine.select([fx[i].fid], add=True)
            self.group_sel = None
            self._changed_sel()

    def _group(self, k):
        g = self._groups_by_slot().get(self.gpage * 15 + k)
        if g:
            self.engine.select(list(g.fixtures))
            self.group_sel = g
            self._changed_sel()

    def _preset(self, k):
        p = self._presets_by_slot().get(self.ppage * 20 + k)
        if p:
            self.engine.apply_preset(p)
            self.programmerChanged.emit()

    def _fpage(self, d):
        pages = max(1, (len(self._fixtures()) + 19) // 20)
        self.fpage = max(0, min(pages - 1, self.fpage + d))
        self.refresh()

    def _gpage(self, d):
        self.gpage = max(0, min(400 // 15, self.gpage + d))
        self.refresh()

    def _ppage(self, d):
        self.ppage = max(0, min(39, self.ppage + d))
        self.refresh()

    def _open_full(self):
        self.engine.open_full()
        self.programmerChanged.emit()

    def _align(self):
        self.engine.align = not self.engine.align
        self.refresh()

    def _even_odd(self):
        if not self.base_selection:
            self.base_selection = list(self.engine.selection)
        self.engine.even_odd(self.base_selection)
        self.refresh()
        self.selectionChanged.emit()

    def _find(self, on):
        self.engine.highlight = on
        self.programmerChanged.emit()

    def _locate(self):
        self.engine.locate()
        self.programmerChanged.emit()

    def _clear(self):
        self.engine.clear_programmer()
        self.base_selection = []
        self.group_sel = None
        self.refresh()
        self.selectionChanged.emit()
        self.programmerChanged.emit()

    def _key(self, key):
        fts = self._selected_types()
        if key == self.key:
            self.kpage = (self.kpage + 1) % K.key_pages(fts, key)
        else:
            self.key, self.kpage = key, 0
        self.refresh()

    def turn(self, wheel: int, delta: int) -> None:
        self.engine.wheel_move(self.key, self.kpage, wheel, delta=delta)
        self._sync_wheels()
        self.programmerChanged.emit()

    def _selected_types(self):
        out = []
        for fid in self.engine.selection:
            f = self.engine.show.fixture(fid)
            if f:
                out.append(self.engine.show.ftype(f))
        return out

    # ---------------------------------------------------------------- view
    def _sync_wheels(self):
        if not self.isVisible():
            return
        for w, e in enumerate(self.encoders):
            e.set_info(self.engine.wheel_value(self.key, self.kpage, w))

    def refresh(self):
        fx = self._fixtures()
        pages = max(1, (len(fx) + 19) // 20)
        self.fpage = min(self.fpage, pages - 1)
        self.f_title.setText(f"Fixtures - {self.fpage + 1}   ({len(fx)} fixtures, page {self.fpage + 1}/{pages})")
        sel = set(self.engine.selection)
        for k, b in enumerate(self.f_btns):
            i = self.fpage * 20 + k
            if i < len(fx):
                f = fx[i]
                b.setText(f"{f.fid}  {f.name[:11]}")
                b.setStyleSheet(FIX_SEL if f.fid in sel else FIX_BTN)
                b.setToolTip(f"#{f.fid} {f.name} – {f.type_key}" + ("" if f.patched else "  (not patched)"))
                b.setEnabled(True)
            else:
                b.setText("")
                b.setStyleSheet(EMPTY)
                b.setEnabled(False)
        groups = self._groups_by_slot()
        self.g_title.setText(f"Groups - {self.gpage + 1}")
        for k, b in enumerate(self.g_btns):
            slot = self.gpage * 15 + k
            g = groups.get(slot)
            if g:
                b.setText(f"{slot + 1}  {g.name[:12]}")
                b.setStyleSheet(GRP_SEL if g is self.group_sel else GRP_BTN)
                b.setToolTip(f"Group {slot + 1}: {g.name} – {len(g.fixtures)} fixtures")
                b.setEnabled(True)
            else:
                b.setText(str(slot + 1))
                b.setStyleSheet(EMPTY)
                b.setEnabled(False)
        presets = self._presets_by_slot()
        self.p_title.setText(f"Presets - {self.ppage + 1}")
        for k, b in enumerate(self.p_btns):
            slot = self.ppage * 20 + k
            p = presets.get(slot)
            if p:
                b.setText(f"{slot + 1}  {p.name[:10]}")
                b.setStyleSheet(PRE_BTN)
                b.setToolTip(f"Preset {slot + 1}: {p.name} ({p.category})")
                b.setEnabled(True)
            else:
                b.setText(str(slot + 1))
                b.setStyleSheet(EMPTY)
                b.setEnabled(False)
        self.b_align.setText("Fixture Align =On" if self.engine.align else "Fixture Align =Off")
        fts = self._selected_types()
        for k, b in self.k_btns.items():
            has = any(K.key_has_channels(ft, k) for ft in fts)
            b.setStyleSheet(KEY_ON if k == self.key else KEY_BTN)
            b.setToolTip(("(no channel on this key for the selection)  " if fts and not has else "")
                         + "Press again for page 2")
        np = K.key_pages(fts, self.key) if fts else 1
        n = len(self.engine.selection)
        self.info_lbl.setText(f"  {n} sel • {self.key} p{self.kpage + 1}/{np}"
                              + (" • Align" if self.engine.align else ""))
        self._sync_wheels()
