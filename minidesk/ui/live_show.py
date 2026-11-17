"""LIVE SHOW page of the CODE MINI 1000T.

Fixtures (20 per page), Groups (15 per page, console slots), Presets (2 x 10),
Fixture Open/Full, Fixture Align, Even/Odd, Find, Locate, the attribute keys
(Dimmer, Tilt/Pan, Colour, Colour Mix, Gobo1, Gobo2, Beam, Effect, Control) and the
encoder wheels A / B / C labelled with the channel names of the console library.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QBoxLayout, QDial, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from .. import console as K
from ..engine import Engine

FIX_BTN = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2f6fd6, stop:1 #123a8c);"
           " color:white; border:1px solid #0d2a66; font-size:8.5pt; padding:2px; }")
FIX_SEL = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #bfe6ff, stop:1 #5fb7f0);"
           " color:#103060; border:1px solid #9fd6ff; font-size:8.5pt; padding:2px; }")
GRP_BTN = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #9a7a18, stop:1 #4d3a08);"
           " color:white; border:1px solid #2d2205; font-size:8.5pt; font-weight:600; padding:2px; }")
GRP_SEL = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fff36a, stop:1 #f2d21a);"
           " color:#6a6a9a; border:1px solid #fff9b0; font-size:8.5pt; padding:2px; }")
PRE_BTN = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2e8a3e, stop:1 #10501d);"
           " color:white; border:1px solid #0b3a14; font-size:8.5pt; font-weight:600; padding:2px; }")
EMPTY = "QPushButton { background:#ececf0; color:#8a8a99; border:1px solid #c5c5cc; font-size:8.5pt; }"
KEY_BTN = "QPushButton { background:#1a1b20; color:#ff5a4a; border:1px solid #3a1010; font-weight:600; }"
KEY_ON = "QPushButton { background:#1a1b20; color:#4cff6a; border:1px solid #1d5a28; font-weight:700; }"


class Encoder(QWidget):
    """One encoder wheel: channel name, '50% (128)', a dial for relative turns and -/+."""

    def __init__(self, live: "LiveShow", wheel: int):
        super().__init__()
        self.live, self.wheel = live, wheel
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.title = QLabel("")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("background:#000; color:white; font-weight:600; padding:3px;")
        self.value = QLabel("")
        self.value.setAlignment(Qt.AlignCenter)
        self.value.setStyleSheet("background:#dde3ee; color:#3a4a8a; padding:3px;")
        self.dial = QDial()
        self.dial.setWrapping(True)
        self.dial.setRange(0, 63)
        self.dial.setFixedHeight(64)
        self.dial.setNotchesVisible(True)
        self._last = 0
        self.dial.valueChanged.connect(self._turn)
        row = QHBoxLayout()
        for txt, d in (("−10", -10), ("−", -1), ("+", 1), ("+10", 10)):
            b = QPushButton(txt)
            b.setFixedHeight(24)
            b.setStyleSheet("padding:1px 4px;")
            b.clicked.connect(lambda _=False, dd=d: self.live.turn(self.wheel, dd))
            row.addWidget(b)
        letter = QLabel("ABC"[wheel])
        letter.setAlignment(Qt.AlignCenter)
        letter.setStyleSheet("color:#c8c8d0; font-size:16pt; font-weight:700;")
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.dial, 0, Qt.AlignHCenter)
        lay.addLayout(row)
        lay.addWidget(letter)

    def _turn(self, v):
        d = v - self._last
        if d > 32:
            d -= 64
        elif d < -32:
            d += 64
        self._last = v
        if d:
            self.live.turn(self.wheel, d * 2)

    def set_info(self, info):
        if info is None:
            self.title.setText(" ")
            self.value.setText(" ")
            self.setEnabled(False)
        else:
            self.setEnabled(True)
            self.title.setText(info[0])
            self.value.setText(K.fmt_value(info[1]))


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
        self.current_label = ""
        root = QBoxLayout(QBoxLayout.LeftToRight, self)
        root.setContentsMargins(4, 4, 4, 4)
        self._root = root
        left = QVBoxLayout()
        root.addLayout(left, 5)

        head = QHBoxLayout()
        t = QLabel("LIVE SHOW")
        t.setObjectName("title")
        head.addWidget(t)
        head.addStretch(1)
        self.cur_lbl = QLabel("")
        self.cur_lbl.setStyleSheet("color:#9ad0ff;")
        head.addWidget(self.cur_lbl)
        left.addLayout(head)

        self.f_title = self._bar("Fixtures - 1")
        left.addWidget(self.f_title)
        fg = QGridLayout()
        fg.setSpacing(3)
        self.f_btns = []
        for i in range(20):
            b = self._btn(lambda _=False, k=i: self._fixture(k))
            fg.addWidget(b, i // 5, i % 5)
            self.f_btns.append(b)
        left.addLayout(fg)
        ctl = QHBoxLayout()
        b = QPushButton("Fixture\nOpen/Full")
        b.setToolTip("Selected fixtures: intensity full, shutter open")
        b.clicked.connect(self._open_full)
        ctl.addWidget(b)
        self.b_align = QPushButton("Fixture Align\n=Off")
        self.b_align.setToolTip("On: the wheels give every selected fixture the same value\n"
                                "Off: the wheels move every fixture relative to its own value")
        self.b_align.clicked.connect(self._align)
        ctl.addWidget(self.b_align)
        b_eo = QPushButton("Even/Odd")
        b_eo.setToolTip("Cycle the selection: all → odd → even → all")
        b_eo.clicked.connect(self._even_odd)
        ctl.addWidget(b_eo)
        self.b_find = QPushButton("Find")
        self.b_find.setCheckable(True)
        self.b_find.setToolTip("Highlight the selected fixtures (open white, full) to find them on stage")
        self.b_find.toggled.connect(self._find)
        ctl.addWidget(self.b_find)
        b_up, b_dn = QPushButton("UP"), QPushButton("DOWN")
        b_up.clicked.connect(lambda: self._fpage(-1))
        b_dn.clicked.connect(lambda: self._fpage(1))
        ctl.addWidget(b_up)
        ctl.addWidget(b_dn)
        left.addLayout(ctl)

        grow = QHBoxLayout()
        self.g_title = self._bar("Groups - 1")
        grow.addWidget(self.g_title, 1)
        for txt, d in (("◀", -1), ("▶", 1)):
            b = QPushButton(txt)
            b.setFixedWidth(34)
            b.clicked.connect(lambda _=False, dd=d: self._gpage(dd))
            grow.addWidget(b)
        left.addLayout(grow)
        gg = QGridLayout()
        gg.setSpacing(3)
        self.g_btns = []
        for i in range(15):
            b = self._btn(lambda _=False, k=i: self._group(k))
            gg.addWidget(b, i // 5, i % 5)
            self.g_btns.append(b)
        left.addLayout(gg)

        # attribute keys + wheels
        keys = QHBoxLayout()
        keys.setSpacing(3)
        self.k_btns = {}
        for k in K.KEYS:
            b = QPushButton(k)
            b.setMinimumHeight(30)
            b.clicked.connect(lambda _=False, kk=k: self._key(kk))
            keys.addWidget(b)
            self.k_btns[k] = b
        b_loc = QPushButton("Locate")
        b_loc.setToolTip("Locate: full, open white, pan/tilt centre for the selection")
        b_loc.setStyleSheet(KEY_BTN)
        b_loc.setMinimumHeight(30)
        b_loc.clicked.connect(self._locate)
        keys.addWidget(b_loc)
        left.addLayout(keys)
        self.page_lbl = QLabel("")
        self.page_lbl.setStyleSheet("color:#9aa0b3;")
        left.addWidget(self.page_lbl)
        wl = QHBoxLayout()
        self.encoders = [Encoder(self, w) for w in range(3)]
        for e in self.encoders:
            wl.addWidget(e)
        left.addLayout(wl)

        # ---- presets + side buttons
        right = QVBoxLayout()
        root.addLayout(right, 2)
        prow = QHBoxLayout()
        self.p_title = self._bar("Presets - 1")
        prow.addWidget(self.p_title, 1)
        for txt, d in (("◀", -1), ("▶", 1)):
            b = QPushButton(txt)
            b.setFixedWidth(30)
            b.clicked.connect(lambda _=False, dd=d: self._ppage(dd))
            prow.addWidget(b)
        right.addLayout(prow)
        pg = QGridLayout()
        pg.setSpacing(3)
        self.p_btns = []
        for i in range(20):
            b = self._btn(lambda _=False, k=i: self._preset(k), h=30)
            pg.addWidget(b, i // 2, i % 2)
            self.p_btns.append(b)
        right.addLayout(pg)
        for text, sig in (("Playback\nParameters", self.paramsRequested), ("Edit Time", self.editTimeRequested),
                          ("Effects", self.effectsRequested), ("Store…", self.storeRequested)):
            b = QPushButton(text)
            b.setMinimumHeight(38)
            b.clicked.connect(sig.emit)
            if text == "Store…":
                b.setObjectName("go")
            right.addWidget(b)
        b_clr = QPushButton("Clear")
        b_clr.setToolTip("Clear the programmer (values, effects and selection)")
        b_clr.clicked.connect(self._clear)
        right.addWidget(b_clr)
        right.addStretch(1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sync_wheels)
        self.timer.start(200)
        self.refresh()

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _bar(text):
        lb = QLabel(text)
        lb.setStyleSheet("background:#2448c8; color:white; padding:3px 8px; border-radius:4px;")
        lb.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        return lb

    @staticmethod
    def _btn(fn, h=42):
        b = QPushButton()
        b.setMinimumHeight(h)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        b.clicked.connect(fn)
        return b

    def _fixtures(self):
        return sorted(self.engine.show.fixtures, key=lambda f: f.fid)

    def _groups_by_slot(self):
        out = {}
        free = 0
        for g in self.engine.show.groups:
            if g.slot >= 0:
                out[g.slot] = g
        for g in self.engine.show.groups:          # groups made here: first free slots
            if g.slot < 0:
                while free in out:
                    free += 1
                out[free] = g
        return out

    def _presets_by_slot(self):
        out = {}
        free = 0
        for p in self.engine.show.presets:
            if p.slot >= 0:
                out[p.slot] = p
        for p in self.engine.show.presets:
            if p.slot < 0:
                while free in out:
                    free += 1
                out[free] = p
        return out

    def set_current_playback(self, pb) -> None:
        self.current_label = f"Current Playback: {pb.console_label}  {pb.name}" if pb else ""
        self.cur_lbl.setText(self.current_label)

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
        base = self.base_selection or list(self.engine.selection)
        if not self.base_selection:
            self.base_selection = base
        self.engine.even_odd(base)
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
        self.f_title.setText(f"Fixtures - {self.fpage + 1}   ({len(fx)} fixtures, {pages} pages)")
        sel = set(self.engine.selection)
        for k, b in enumerate(self.f_btns):
            i = self.fpage * 20 + k
            if i < len(fx):
                f = fx[i]
                b.setText(f"{f.fid}\n{f.name[:12]}")
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
                b.setText(f"{slot + 1}\n{g.name[:12]}")
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
        self.b_align.setText("Fixture Align\n=On" if self.engine.align else "Fixture Align\n=Off")
        fts = self._selected_types()
        for k, b in self.k_btns.items():
            has = any(K.key_has_channels(ft, k) for ft in fts)
            b.setStyleSheet(KEY_ON if k == self.key else KEY_BTN)
            b.setToolTip(("" if has or not fts else "(no channel on this key for the selection)  ")
                         + "Press again for page 2")
        np = K.key_pages(fts, self.key) if fts else 1
        self.page_lbl.setText(f"{self.key}  page {self.kpage + 1}/{np}   –   wheels A / B / C"
                              + ("   (Fixture Align on)" if self.engine.align else ""))
        self._sync_wheels()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        want = QBoxLayout.TopToBottom if self.width() < 1060 else QBoxLayout.LeftToRight
        if self._root.direction() != want:
            self._root.setDirection(want)
