"""'Effect Select' screen of the CODE MINI 1000T: the console effect library.

Layout follows the console: category list (Intensity / Position / Color / Beam / All),
20 effects per page with UP / DOWN, *Current Loaded Effects*, Direction, Effect Mode,
Fixture Order, Delete Effect / Delete All Effects, the Size / Speed / Spread encoders
and the 20 *User Effects*.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QBoxLayout, QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QMessageBox, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from .. import console_fx as C
from ..engine import Engine
from ..model import Effect

FX_BTN = ("QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #6a64e8, stop:1 #3a2fb8);"
          " border:1px solid #2a2390; color:white; font-size:8.5pt; padding:2px; }"
          "QPushButton:hover { background:#7d78f0; }")
LOADED_BTN = "QPushButton { background:#f3f3f6; color:#222; border:1px solid #9aa; font-size:8.5pt; }"
LOADED_SEL = "QPushButton { background:#f07ad8; color:#111; border:1px solid #c04aa8; font-size:8.5pt; font-weight:600; }"
USER_BTN = "QPushButton { background:#eef0e6; color:#333; border:1px solid #9a9; font-size:8.5pt; }"
USER_SET = "QPushButton { background:#2f7a3c; color:white; border:1px solid #4caf62; font-size:8.5pt; }"
PER_PAGE = 20
LOADED_PER_PAGE = 5
CAT_LABEL = {"Intensity": "Intensity Effects", "Position": "Position Effects", "Color": "Color Effects",
             "Beam": "Beam Effects", "All": "All Effects"}


def _encoder(title: str, lo: float, hi: float, step: float, suffix: str, dec: int = 0):
    box = QGroupBox(title)
    lay = QVBoxLayout(box)
    sp = QDoubleSpinBox()
    sp.setRange(lo, hi)
    sp.setSingleStep(step)
    sp.setDecimals(dec)
    sp.setSuffix(suffix)
    sp.setKeyboardTracking(False)
    sl = QSlider(Qt.Horizontal)
    sl.setRange(int(lo * 10), int(hi * 10))
    sl.valueChanged.connect(lambda v: sp.setValue(v / 10))
    sp.valueChanged.connect(lambda v: (sl.blockSignals(True), sl.setValue(int(v * 10)), sl.blockSignals(False)))
    lay.addWidget(sp)
    lay.addWidget(sl)
    return box, sp


class ConsoleEffectSelect(QWidget):
    changed = Signal()
    storeRequested = Signal()
    manualRequested = Signal()
    userChanged = Signal()          # user effects edited (saved with the show)

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.cat = "Position"
        self.page = 0
        self.loaded_page = 0
        self.current: Effect | None = None
        self.user_sel = 0
        root = QBoxLayout(QBoxLayout.LeftToRight, self)
        root.setContentsMargins(4, 4, 4, 4)
        self._root = root
        left = QVBoxLayout()
        root.addLayout(left, 3)

        head = QHBoxLayout()
        t = QLabel("Effect Select")
        t.setObjectName("title")
        head.addWidget(t)
        self.page_lbl = QLabel()
        head.addWidget(self.page_lbl)
        head.addStretch(1)
        self.sel_lbl = QLabel()
        self.sel_lbl.setStyleSheet("color:#9aa0b3;")
        head.addWidget(self.sel_lbl)
        left.addLayout(head)

        self.grid = QGridLayout()
        self.grid.setSpacing(3)
        self.fx_buttons = []
        for i in range(PER_PAGE):
            b = QPushButton()
            b.setMinimumHeight(44)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            b.setStyleSheet(FX_BTN)
            b.clicked.connect(lambda _=False, k=i: self._pick(k))
            self.grid.addWidget(b, i // 5, i % 5)
            self.fx_buttons.append(b)
        left.addLayout(self.grid)

        nav = QHBoxLayout()
        b_open = QPushButton("Fixture\nOpen/Full")
        b_open.setToolTip("Selected fixtures: intensity full and shutter open")
        b_open.clicked.connect(self._open_full)
        nav.addWidget(b_open)
        self.cat_box = QComboBox()
        for c in ("Intensity", "Position", "Color", "Beam", "All"):
            self.cat_box.addItem(CAT_LABEL[c], c)
        self.cat_box.setCurrentIndex(1)
        self.cat_box.setStyleSheet("QComboBox { background:#b23ad0; color:white; font-weight:600; min-height:32px; }")
        self.cat_box.currentIndexChanged.connect(self._cat)
        nav.addWidget(self.cat_box, 2)
        b_up, b_dn = QPushButton("UP"), QPushButton("DOWN")
        b_up.clicked.connect(lambda: self._page(-1))
        b_dn.clicked.connect(lambda: self._page(1))
        nav.addWidget(b_up)
        nav.addWidget(b_dn)
        left.addLayout(nav)

        lt = QLabel("Current Loaded Effects")
        lt.setStyleSheet("background:#2448c8; color:white; padding:3px 8px; border-radius:4px;")
        lt.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        left.addWidget(lt)
        lg = QGridLayout()
        lg.setSpacing(3)
        self.loaded_buttons = []
        for i in range(LOADED_PER_PAGE):
            b = QPushButton()
            b.setMinimumHeight(40)
            b.setStyleSheet(LOADED_BTN)
            b.clicked.connect(lambda _=False, k=i: self._select_loaded(k))
            lg.addWidget(b, 0, i)
            self.loaded_buttons.append(b)
        b_man = QPushButton("Manual\nEffects")
        b_man.setToolTip("Open the free effect editor (all parameters, colours, wings, blocks…)")
        b_man.clicked.connect(self.manualRequested.emit)
        lg.addWidget(b_man, 1, 1)
        b_pu, b_pd = QPushButton("Page Up"), QPushButton("Page Down")
        b_pu.clicked.connect(lambda: self._loaded_page(-1))
        b_pd.clicked.connect(lambda: self._loaded_page(1))
        lg.addWidget(b_pu, 1, 3)
        lg.addWidget(b_pd, 1, 4)
        self.attr_lbl = QLabel("Effect\nAttribute")
        self.attr_lbl.setAlignment(Qt.AlignCenter)
        self.attr_lbl.setStyleSheet("background:#1b3fd0; color:white; border-radius:4px; padding:4px;")
        lg.addWidget(self.attr_lbl, 2, 0, 2, 1)
        self.b_dir = QPushButton("Direction\n---->")
        self.b_dir.setToolTip("Direction of the phase through the fixtures")
        self.b_dir.clicked.connect(self._direction)
        lg.addWidget(self.b_dir, 2, 1)
        self.b_mode = QPushButton("Effect Mode\n=Absolute")
        self.b_mode.setToolTip("Absolute: around the effect centre / full range\n"
                               "Rel(Center): around the fixture's current value")
        self.b_mode.clicked.connect(self._mode)
        lg.addWidget(self.b_mode, 2, 2)
        self.order = QComboBox()
        for k, v in C.ORDERS.items():
            self.order.addItem(f"Fixture Order: {v}", k)
        self.order.currentIndexChanged.connect(self._order)
        lg.addWidget(self.order, 2, 3)
        b_del = QPushButton("Delete\nEffect")
        b_del.setObjectName("danger")
        b_del.clicked.connect(self._delete)
        b_dall = QPushButton("Delete All\nEffects")
        b_dall.setObjectName("danger")
        b_dall.clicked.connect(self._delete_all)
        lg.addWidget(b_del, 3, 3)
        lg.addWidget(b_dall, 3, 4)
        b_store = QPushButton("Store…")
        b_store.setObjectName("go")
        b_store.setToolTip("Store the programmer (values + loaded effects) into a cue")
        b_store.clicked.connect(self.storeRequested.emit)
        lg.addWidget(b_store, 2, 4)
        left.addLayout(lg)

        enc = QHBoxLayout()
        bx, self.size = _encoder("Effect Size", 0, 100, 5, " %")
        enc.addWidget(bx)
        bx, self.speed = _encoder("Effect Speed", 0.5, 300, 0.5, " BPM", 1)
        enc.addWidget(bx)
        bx, self.spread = _encoder("Effect Spread", 0, 360, 15, " °")
        enc.addWidget(bx)
        self.size.valueChanged.connect(self._param)
        self.speed.valueChanged.connect(self._param)
        self.spread.valueChanged.connect(self._param)
        left.addLayout(enc)

        # ---- user effects
        right = QVBoxLayout()
        root.addLayout(right, 1)
        ut = QLabel("User Effects")
        ut.setStyleSheet("background:#2448c8; color:white; padding:3px 8px; border-radius:4px;")
        ut.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        right.addWidget(ut)
        ug = QGridLayout()
        ug.setSpacing(3)
        self.user_buttons = []
        for i in range(20):
            b = QPushButton(str(i + 1))
            b.setMinimumHeight(30)
            b.setStyleSheet(USER_BTN)
            b.clicked.connect(lambda _=False, k=i: self._user(k))
            ug.addWidget(b, i // 2, i % 2)
            self.user_buttons.append(b)
        right.addLayout(ug)
        for text, fn in (("Save Running\nEffects", self._user_save), ("Edit Label", self._user_label),
                         ("Delete User\nEffect", self._user_delete), ("Delete All\nUser Effects", self._user_clear)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            right.addWidget(b)
        right.addStretch(1)
        self._loading = False
        self.refresh()

    # --------------------------------------------------------------- library
    def _entries(self):
        if self.cat == "All":
            return [(c, n, name) for c, n, name in C.all_entries()]
        return [(self.cat, n, name) for n, name in C.entries(self.cat)]

    def _cat(self, _i):
        self.cat = self.cat_box.currentData()
        self.page = 0
        self.refresh()

    def _page(self, d):
        pages = max(1, (len(self._entries()) + PER_PAGE - 1) // PER_PAGE)
        self.page = max(0, min(pages - 1, self.page + d))
        self.refresh()

    def _pick(self, k):
        ents = self._entries()
        i = self.page * PER_PAGE + k
        if i >= len(ents):
            return
        cat, no, _name = ents[i]
        sel = list(self.engine.selection)
        if not sel:
            QMessageBox.information(self, "Effects", "Select fixtures or a group first (Live / Fixtures tab).")
            return
        eff = C.make(cat, no, sel)
        if self.current is not None and C.category_of(self.current) == cat:   # keep the encoder settings
            C.set_bpm(eff, C.bpm(self.current))
        self.engine.add_effect(eff)
        self.current = eff
        n = len(self.engine.effects)
        self.loaded_page = (n - 1) // LOADED_PER_PAGE
        self.refresh()
        self.changed.emit()

    # ---------------------------------------------------------- loaded list
    def _loaded_page(self, d):
        pages = max(1, (len(self.engine.effects) + LOADED_PER_PAGE - 1) // LOADED_PER_PAGE)
        self.loaded_page = max(0, min(pages - 1, self.loaded_page + d))
        self.refresh()

    def _select_loaded(self, k):
        i = self.loaded_page * LOADED_PER_PAGE + k
        if i < len(self.engine.effects):
            self.current = self.engine.effects[i]
            self.refresh()

    def _direction(self):
        if self.current:
            self.current.reverse = not self.current.reverse
            self.refresh()
            self.changed.emit()

    def _mode(self):
        if self.current:
            cat = C.category_of(self.current)
            cur = self.current.mode or ("rel" if cat == "Position" else "abs")
            self.current.mode = "abs" if cur == "rel" else "rel"
            self.refresh()
            self.changed.emit()

    def _order(self, _i):
        if self.current and not self._loading:
            self.current.order = self.order.currentData()
            self.changed.emit()

    def _param(self, *_):
        if self.current is None or self._loading:
            return
        C.set_size_pct(self.current, self.size.value())
        C.set_bpm(self.current, self.speed.value())
        if abs(self.spread.value() - C.spread_deg(self.current)) > 0.01:
            C.set_spread_deg(self.current, self.spread.value())
        self.changed.emit()

    def _delete(self):
        if self.current in self.engine.effects:
            self.engine.remove_effect(self.current)
        self.current = self.engine.effects[-1] if self.engine.effects else None
        self.refresh()
        self.changed.emit()

    def _delete_all(self):
        for e in list(self.engine.effects):
            self.engine.remove_effect(e)
        self.current = None
        self.refresh()
        self.changed.emit()

    def _open_full(self):
        self.engine.open_full()
        self.changed.emit()

    # ---------------------------------------------------------- user effects
    def _user_entry(self, k):
        for u in self.engine.show.user_effects:
            if u.get("slot") == k:
                return u
        return None

    def _user(self, k):
        self.user_sel = k
        u = self._user_entry(k)
        if u:                                   # load: start the saved effects again
            for d in u.get("effects", []):
                eff = Effect.from_json(d)
                if self.engine.selection:
                    eff.fixtures = list(self.engine.selection) if not eff.fixtures else eff.fixtures
                self.engine.add_effect(eff)
                self.current = eff
            self.changed.emit()
        self.refresh()

    def _user_save(self):
        if not self.engine.effects:
            QMessageBox.information(self, "User Effects", "No effects are running.")
            return
        k = self.user_sel
        if self._user_entry(k) is not None:
            free = [i for i in range(20) if self._user_entry(i) is None]
            if free and QMessageBox.question(self, "User Effects", f"User effect {k + 1} is used. "
                                             f"Save into {free[0] + 1} instead?") == QMessageBox.Yes:
                k = free[0]
        self.engine.show.user_effects = [u for u in self.engine.show.user_effects if u.get("slot") != k]
        name = " + ".join(e.label or e.type for e in self.engine.effects)[:20]
        self.engine.show.user_effects.append({"slot": k, "name": name,
                                              "effects": [copy.deepcopy(e).to_json() for e in self.engine.effects]})
        self.user_sel = k
        self.refresh()
        self.userChanged.emit()

    def _user_label(self):
        u = self._user_entry(self.user_sel)
        if not u:
            return
        name, ok = QInputDialog.getText(self, "Edit Label", "Name:", text=u.get("name", ""))
        if ok:
            u["name"] = name[:20]
            self.refresh()
            self.userChanged.emit()

    def _user_delete(self):
        self.engine.show.user_effects = [u for u in self.engine.show.user_effects if u.get("slot") != self.user_sel]
        self.refresh()
        self.userChanged.emit()

    def _user_clear(self):
        if QMessageBox.question(self, "User Effects", "Delete all user effects?") == QMessageBox.Yes:
            self.engine.show.user_effects = []
            self.refresh()
            self.userChanged.emit()

    # ---------------------------------------------------------------- view
    def refresh(self):
        self._loading = True
        ents = self._entries()
        pages = max(1, (len(ents) + PER_PAGE - 1) // PER_PAGE)
        self.page = min(self.page, pages - 1)
        self.page_lbl.setText(f"Effects - {self.page + 1}  ({pages} pages, {len(ents)} effects)")
        for k, b in enumerate(self.fx_buttons):
            i = self.page * PER_PAGE + k
            if i < len(ents):
                cat, no, name = ents[i]
                b.setText(f"{no}\n{name}" if self.cat != "All" else f"{C.LETTER[cat]}{no}\n{name}")
                kw = C.spec(cat, name)
                b.setToolTip(f"{cat} {no}: {name}\n" + ", ".join(f"{k2}={v}" for k2, v in kw.items()))
                b.setEnabled(True)
                b.setStyleSheet(FX_BTN)
            else:
                b.setText("")
                b.setEnabled(False)
                b.setStyleSheet("QPushButton { background:#e9e9ee; border:1px solid #bbb; }")
        sel = self.engine.selection
        self.sel_lbl.setText(f"{len(sel)} fixtures selected" if sel else "no fixtures selected")
        effs = self.engine.effects
        if self.current not in effs:
            self.current = effs[-1] if effs else None
        for k, b in enumerate(self.loaded_buttons):
            i = self.loaded_page * LOADED_PER_PAGE + k
            if i < len(effs):
                e = effs[i]
                b.setText(f"{len(e.fixtures)}  {C.letter(e)}\n{e.label or e.type}")
                b.setStyleSheet(LOADED_SEL if e is self.current else LOADED_BTN)
                b.setEnabled(True)
            else:
                b.setText("")
                b.setStyleSheet(LOADED_BTN)
                b.setEnabled(False)
        e = self.current
        for w in (self.size, self.speed, self.spread, self.b_dir, self.b_mode, self.order):
            w.setEnabled(e is not None)
        if e is not None:
            self.size.setValue(C.size_pct(e))
            self.speed.setValue(C.bpm(e))
            self.spread.setValue(C.spread_deg(e))
            self.b_dir.setText("Direction\n<----" if e.reverse else "Direction\n---->")
            cat = C.category_of(e)
            mode = e.mode or ("rel" if cat == "Position" else "abs")
            self.b_mode.setText("Effect Mode\n=Rel(Center)" if mode == "rel" else "Effect Mode\n=Absolute")
            i = self.order.findData(e.order)
            self.order.setCurrentIndex(max(0, i))
            self.attr_lbl.setText(f"Effect\n{e.attribute or cat}")
        for k, b in enumerate(self.user_buttons):
            u = self._user_entry(k)
            b.setText(f"{k + 1}  {u.get('name', '')[:12]}" if u else str(k + 1))
            st = USER_SET if u else USER_BTN
            if k == self.user_sel:
                st = st.replace("}", " border:2px solid #f5b331; }", 1)
            b.setStyleSheet(st)
        self._loading = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        want = QBoxLayout.TopToBottom if self.width() < 1060 else QBoxLayout.LeftToRight
        if self._root.direction() != want:
            self._root.setDirection(want)
