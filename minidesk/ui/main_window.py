"""Main window: ties engine, visualizer, programmer, playbacks, stage editor and I/O together."""
from __future__ import annotations

import os
import traceback

from PySide6.QtCore import QObject, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMessageBox, QPushButton, QSizePolicy, QSlider, QSpinBox,
                               QSplitter, QToolBar, QVBoxLayout, QWidget)

from .. import companion
from ..commands import CommandLine
from ..dmx_io import (ArtNetInput, ArtNetOutput, EnttecProInput, EnttecProOutput, OpenDmxOutput,
                      SacnOutput, describe_serial_ports, local_ips)
from ..midi import MidiManager
from ..engine import Engine, EngineRunner
from ..model import Playback, Show, builtin_types
from ..sho_file import ShoDocument, step_signature
from ..sho_import import ShoFormatError, import_sho
from . import preferences as prefs
from .connect import ConnectDialog
from .cue_editor import CueEditor
from .dmx_monitor import DmxMonitor
from .executors import ExecutorBar
from .fixture_sheet import FixtureSheet
from .patch import PatchPanel
from .presets_panel import PresetsPanel
from .programmer import ProgrammerPanel
from .settings import IOSettingsDialog
from .stage_editor import StageEditor
from .theme import DARK_QSS
from .visualizer import StageView

APP_NAME = "MiniDesk"

GUIDE = """<h3>Panduan singkat MiniDesk (CODE MINI 1000T)</h3>
<ol>
<li><b>Buka file console</b>: File → Open console file (.SHO). Fixture, patch, group dan playback dari
console langsung muncul.</li>
<li><b>Stage Layout</b> (tab): atur ukuran panggung lalu pilih <i>Top</i> atau <i>Front</i> dan drag fixture
ke posisinya. Pilih banyak fixture (Ctrl+klik / tarik kotak) lalu pakai tombol align.</li>
<li><b>Patch</b> (tab): ganti nama, tipe, universe, address. <i>Edit fixture type &amp; 3D model</i> untuk
memilih model 3D (beam, hybrid, spot, wash, PAR, fresnel, strobe, LED bar, blinder, hazer, fog) atau
<b>import model sendiri</b> (OBJ, GLB/glTF, STL) – lengkap dengan preview yang berputar.</li>
<li><b>Fixtures / Groups</b>: klik group/fixture untuk memilih. Klik kanan group: rename / update / delete.</li>
<li><b>Programmer</b>: halaman Intensity (dimmer, strobe), Position (pan, tilt, home), Color, Beam, Other.</li>
<li><b>✦ Effects</b>: 41 effect – Position (circle, diamond, square, triangle, figure 8, S, cross, star, spiral,
pan saw, tilt saw, sine, swing, step, ballyhoo, random), Intensity (sine, saw, ramp, chase/step, soft chase,
random, sparkle, strobe), Colour (rainbow, chase, fade, RGB step, random), Beam (gobo step, zoom/focus/iris/
frost wave, prism). Parameter: speed/BPM, size, low/high, spread, offset, wings, duty, fade-in.</li>
<li><b>Store…</b> menyimpan programmer (nilai + effect) sebagai cue di sebuah playback.
Timing per cue (delay in, fade in, delay out, fade out, hold) diatur di tab <b>Cues</b>.</li>
<li><b>Programmer → Beam</b>: tombol cepat gobo (open, 1–8, shake), gobo rotation, prism (on / macro /
rotate), frost, zoom, focus, iris, shutter, lamp/reset. Setiap channel juga punya daftar fungsi (rentang DMX)
yang bisa diedit di <i>Patch → Edit fixture type</i>.</li>
<li><b>Presets</b>: simpan programmer sebagai preset Color / Position / Beam / Intensity, klik untuk memakai.
Preset dari console ikut terbaca.</li>
<li>Mainkan dengan fader <b>Playbacks</b> di bawah (15 playback per bank, bisa diubah di Preferences).
Tab <b>Cues</b>: mode chase / cue list, arah (forward, backward, bounce, random), loop, speed + TAP,
crossfade %, release, follow, edit nilai cue, duplicate, copy/paste.</li>
<li><b>Console → Connect console (Ctrl+K)</b>: plug &amp; play – scan Art-Net, pilih interface USB DMX
(otomatis tersambung lagi bila dicabut/dicolok), MIDI in/out dengan MIDI Learn.</li>
<li><b>Save (Ctrl+S)</b>: jika show berasal dari file .SHO, nama fixture, tipe, address, group dan nama playback
<b>ditulis langsung ke file .SHO</b>, lalu file dibaca ulang untuk verifikasi. Salin file ke USB,
colokkan ke console dan load.</li>
<li>Untuk melihat console secara live: Console → DMX I/O → Input = artnet / enttec.</li>
</ol>
<p>Yang <b>tidak</b> bisa masuk ke file console (formatnya tidak menyediakan tempat): posisi stage, model 3D,
effect, perubahan isi/timing cue dan playback buatan MiniDesk. Semua itu tersimpan otomatis di project
MiniDesk dan muncul lagi saat file .SHO yang sama dibuka.</p>
"""

SHORTCUTS = """Ctrl+O  open   ·   Ctrl+S  save   ·   Ctrl+I  import .SHO
Tab (in stage view)  3D → Top → Front
Ctrl+click  add to selection   ·   drag box (Top/Front)  select several
Ctrl+Space  GO on the playback shown in the Cues tab
Esc  clear the command line
Command line:  fixture 1 thru 8 at 50  |  group 2 at full  |  go 3  |  store 5  |  clear"""


class MidiBridge(QObject):
    """Moves MIDI callbacks (driver thread) onto the GUI thread."""
    action = Signal(str, int, float, bool)


class StoreDialog(QDialog):
    def __init__(self, engine: Engine, current: Playback | None, parent=None, default_fade: float = 0.0):
        super().__init__(parent)
        self.setWindowTitle("Store programmer as cue")
        self.engine = engine
        f = QFormLayout(self)
        self.num = QSpinBox()
        self.num.setRange(1, 9999)
        nums = [p.number for p in engine.show.playbacks]
        self.num.setValue(current.number if current else (max(nums, default=0) + 1))
        self.name = QLineEdit()
        self.mode = QComboBox()
        self.mode.addItems(["add as new cue", "merge into last cue", "overwrite last cue"])
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 600)
        self.delay.setSuffix(" s")
        self.fade = QDoubleSpinBox()
        self.fade.setRange(0, 600)
        self.fade.setSuffix(" s")
        self.fade.setValue(default_fade)
        self.lbl = QLabel()
        self.num.valueChanged.connect(self._upd)
        n_fx = len(engine.effects)
        f.addRow(QLabel(f"Programmer: {len(engine.programmer)} fixture(s), {n_fx} effect(s)"))
        f.addRow("Playback number", self.num)
        f.addRow("", self.lbl)
        f.addRow("Name (new playback)", self.name)
        f.addRow("Mode", self.mode)
        f.addRow("Delay in", self.delay)
        f.addRow("Fade in", self.fade)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._upd()

    def _pb(self):
        for p in self.engine.show.playbacks:
            if p.number == self.num.value():
                return p
        return None

    def _upd(self):
        p = self._pb()
        self.lbl.setText(f"existing: {p.name} ({len(p.steps)} cues)" if p else "a new playback will be created")

    def apply(self) -> Playback:
        pb = self._pb()
        if pb is None:
            pb = Playback(name=self.name.text() or f"Playback {self.num.value()}", number=self.num.value(),
                          bank="User", mode="cuelist")
            self.engine.show.playbacks.append(pb)
            self.engine.rebuild_patch()
        mode = {0: "add", 1: "merge", 2: "overwrite"}[self.mode.currentIndex()]
        st = self.engine.store(pb, mode, fade=self.fade.value())
        if mode == "add":
            st.delay = self.delay.value()
        return pb


class WelcomeDialog(QDialog):
    def __init__(self, recent: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to MiniDesk")
        self.choice: tuple[str, str] | None = None
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        t = QLabel("<h2>MiniDesk</h2>Lighting programmer &amp; 3D visualizer for "
                   "<b>CODE MINI 1000T / MINI 1000T PRO</b>")
        lay.addWidget(t)
        for text, key in (("📂  Open console file (.SHO) – edit and save back for the console", "sho"),
                          ("🗂  Open MiniDesk project (.mdshow)", "mdshow"),
                          ("✨  New empty show", "new")):
            b = QPushButton(text)
            b.setMinimumHeight(46)
            b.setStyleSheet("text-align:left; padding-left:14px; font-size:11pt;")
            b.clicked.connect(lambda _=False, k=key: self._pick(k, ""))
            lay.addWidget(b)
        if recent:
            lay.addWidget(QLabel("Recent files (double-click)"))
            self.list = QListWidget()
            self.list.addItems(recent)
            self.list.itemDoubleClicked.connect(lambda it: self._pick("path", it.text()))
            lay.addWidget(self.list, 1)
        else:
            lay.addStretch(1)

    def _pick(self, k, p):
        self.choice = (k, p)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None, welcome: bool = True, splash=None):
        super().__init__()
        self.resize(1680, 1000)
        self.setStyleSheet(DARK_QSS)
        self.settings = QSettings("MiniDesk", "MiniDesk")
        self.path: str | None = None
        self.doc: ShoDocument | None = None
        self.dirty = False
        show = Show()
        for t in builtin_types():
            show.add_type(t)
        self.engine = Engine(show)
        self.outputs = []
        self.dmx_input = None
        self.cmd = CommandLine(self.engine)
        self.vis_source = "auto"
        self.bridge = MidiBridge()
        self.bridge.action.connect(self._midi_action)
        self.midi = MidiManager(lambda a, t, v, on: self.bridge.action.emit(a, t, v, on))
        self._ports_seen: set[str] = set()
        if splash:
            splash.step("Creating stage view…")
        self._build()
        self._apply_prefs()
        self.runner = EngineRunner(self.engine, self._send)
        self.runner.start()
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._status)
        self.status_timer.start(500)
        self.usb_timer = QTimer(self)
        self.usb_timer.timeout.connect(self._usb_watch)
        self.usb_timer.start(2000)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave)
        self._apply_prefs()
        self._update_title()
        if path:
            if splash:
                splash.step(f"Opening {os.path.basename(path)}…")
            self.open_path(path)
        elif welcome and prefs.get(self.settings, "welcome"):
            QTimer.singleShot(300, self.show_welcome)

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        mb = self.menuBar()

        def action(menu, text, fn, shortcut=None, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(fn)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setCheckable(checkable)
            menu.addAction(a)
            return a

        m = mb.addMenu("&File")
        action(m, "New show", self.new_show, "Ctrl+N")
        action(m, "Open console file (.SHO)…", self.import_dialog, "Ctrl+I")
        action(m, "Open…", self.open_dialog, "Ctrl+O")
        self.m_recent = m.addMenu("Open recent")
        m.addSeparator()
        action(m, "Save", self.save, "Ctrl+S")
        action(m, "Save as…", self.save_as, "Ctrl+Shift+S")
        action(m, "Export MiniDesk project (.mdshow)…", self.export_project)
        m.addSeparator()
        action(m, "Exit", self.close, "Ctrl+Q")
        m = mb.addMenu("&Edit")
        action(m, "Store programmer as cue…", self.store_dialog, "Ctrl+Return")
        action(m, "Store programmer as preset…", lambda: (self.show_tab(self.presets),
                                                           self.presets.store()), "Ctrl+P")
        action(m, "Clear programmer", lambda: self.prog.clear())
        m.addSeparator()
        action(m, "Preferences…", self.preferences, "Ctrl+,")
        m = mb.addMenu("&View")
        action(m, "3D view", lambda: self._view("3d"), "F5")
        action(m, "Top view (edit X/Y)", lambda: self._view("top"), "F6")
        action(m, "Front view (edit X/Z)", lambda: self._view("front"), "F7")
        action(m, "Reset camera", lambda: self.view.reset_camera())
        m = mb.addMenu("&Console")
        action(m, "Connect console (DMX / Art-Net / MIDI)…", self.connect_wizard, "Ctrl+K")
        action(m, "Advanced DMX input / output…", self.io_settings)
        action(m, "Console file info & check…", self.file_info)
        m = mb.addMenu("&Help")
        action(m, "Quick guide (Bahasa Indonesia)", self.show_guide, "F1")
        action(m, "Keyboard shortcuts", lambda: QMessageBox.information(self, "Shortcuts", SHORTCUTS))
        self._refresh_recent()

        from .icons import icon
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)
        logo = QLabel("  ◉ MiniDesk  ")
        logo.setStyleSheet("color:#f5b331; font-weight:800; font-size:12pt; padding-right:8px;")
        tb.addWidget(logo)
        for text, fn, tip, ic in (("Open .SHO", self.import_dialog, "Open a CODE MINI 1000T show file", "open"),
                                  ("Save", self.save, "Save (writes into the console file when opened from .SHO)",
                                   "save"),
                                  ("Connect", self.connect_wizard, "Plug & play: Art-Net, USB DMX, MIDI", "connect"),
                                  ("Settings", self.preferences, "Preferences", "settings")):
            a = QAction(icon(ic), text, self)
            a.setToolTip(tip)
            a.triggered.connect(fn)
            tb.addAction(a)
        tb.addSeparator()
        self.a_bo = QAction(icon("blackout", "#ff7a7a"), "BLACKOUT", self)
        self.a_bo.setCheckable(True)
        self.a_bo.setToolTip("Blackout: all intensity to zero (B)")
        self.a_bo.toggled.connect(self._blackout)
        tb.addAction(self.a_bo)
        tb.addWidget(QLabel("  GM "))
        self.gm = QSlider(Qt.Horizontal)
        self.gm.setRange(0, 100)
        self.gm.setValue(100)
        self.gm.setFixedWidth(110)
        self.gm.setToolTip("Grand master")
        self.gm_lbl = QLabel("100%")
        self.gm_lbl.setMinimumWidth(40)
        self.gm.valueChanged.connect(self._gm)
        tb.addWidget(self.gm)
        tb.addWidget(self.gm_lbl)
        tb.addSeparator()
        tb.addWidget(QLabel(" View "))
        self.src = QComboBox()
        self.src.addItems(["auto", "program (PC)", "console input", "mix (HTP)"])
        self.src.setToolTip("What the stage view shows: auto = console input when it is received, "
                            "otherwise this program")
        self.src.currentTextChanged.connect(lambda t: setattr(self, "vis_source", t))
        tb.addWidget(self.src)
        tb.addWidget(QLabel("  Haze "))
        haze = QSlider(Qt.Horizontal)
        haze.setRange(0, 100)
        haze.setValue(35)
        haze.setFixedWidth(80)
        haze.valueChanged.connect(lambda v: setattr(self.view, "haze", v / 100))
        self.haze_slider = haze
        tb.addWidget(haze)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.led_net, self.led_usb, self.led_midi = QLabel("● Art-Net"), QLabel("● USB"), QLabel("● MIDI")
        for led in (self.led_net, self.led_usb, self.led_midi):
            led.setToolTip("grey = off, orange = waiting / unplugged, green = connected – click Connect")
            led.setObjectName("chip")
            tb.addWidget(led)

        # banner
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setTextFormat(Qt.RichText)
        self.banner.setStyleSheet("padding:7px 12px; background:#171b26; border-bottom:1px solid #262c3d; "
                                  "border-radius:0px;")

        self.view = StageView(self.engine.show, self.vis_dmx)
        self.view.fixtureClicked.connect(self._vis_click)
        self.view.layoutEdited.connect(self._layout_edited)
        self.view.modeChanged.connect(lambda _m: hasattr(self, "stage") and self.stage.sync_mode())

        self.sheet = FixtureSheet(self.engine, self.vis_dmx)
        self.sheet.selectionChanged.connect(self._selection_changed)
        self.sheet.groupsChanged.connect(self.mark_dirty)
        self.prog = ProgrammerPanel(self.engine)
        self.prog.storeRequested.connect(self.store_dialog)
        self.prog.programmerChanged.connect(self.sheet.grid.update)
        self.cues = CueEditor(self.engine)
        self.cues.changed.connect(lambda: (self.execs.rebind(), self.mark_dirty()))
        self.cues.loadedToProgrammer.connect(self._selection_changed)
        self.patch = PatchPanel(self.engine)
        self.patch.changed.connect(self._patch_changed)
        self.patch.selectFixtures.connect(self._select_from_patch)
        self.presets = PresetsPanel(self.engine)
        self.presets.applied.connect(self._selection_changed)
        self.presets.changed.connect(self.mark_dirty)
        self.stage = StageEditor(self.engine, self.view)
        self.stage.changed.connect(self._layout_edited)
        self.monitor = DmxMonitor({"program output": self.prog_dmx, "console input": self.input_dmx,
                                   "stage view": self.vis_dmx}, lambda: self.engine.show)

        self.fx = self.prog.fx
        self.fx.storeRequested.connect(self.store_dialog)
        self.fx.changed.connect(self.sheet.grid.update)
        from .nav import NavTabs
        self.tabs = NavTabs()
        self._tab_pages = {}
        for w, label, ic in ((self.sheet, "Fixtures", "fixtures"), (self.prog, "Programmer", "programmer"),
                             (self.fx, "Effects", "effects"), (self.presets, "Presets", "presets"),
                             (self.cues, "Cues", "cues"), (self.stage, "Stage", "stage"),
                             (self.patch, "Patch", "patch"), (self.monitor, "DMX", "dmx")):
            self._tab_pages[w] = self.tabs.addTab(self._scroll(w), label, ic)

        top = QSplitter(Qt.Horizontal)
        top.setChildrenCollapsible(False)
        top.addWidget(self.view)
        top.addWidget(self.tabs)
        top.setStretchFactor(0, 5)
        top.setStretchFactor(1, 4)
        top.setSizes([900, 760])
        self.execs = ExecutorBar(self.engine)
        self.execs.playbackSelected.connect(self._edit_playback)
        self.execs.playbackTriggered.connect(self._feedback)
        vs = QSplitter(Qt.Vertical)
        vs.setChildrenCollapsible(False)
        vs.addWidget(top)
        from PySide6.QtWidgets import QFrame, QScrollArea
        ex_sc = QScrollArea()
        ex_sc.setWidgetResizable(True)
        ex_sc.setFrameShape(QFrame.NoFrame)
        ex_sc.setWidget(self.execs)
        ex_sc.setMinimumHeight(252)
        vs.addWidget(ex_sc)
        vs.setStretchFactor(0, 3)
        vs.setStretchFactor(1, 1)
        vs.setSizes([700, 260])

        self.cmdline = QLineEdit()
        self.cmdline.setObjectName("cmd")
        self.cmdline.setPlaceholderText("Command:  fixture 1 thru 8 at 50  |  group 2 at full  |  go 3  |  "
                                        "store 5  |  clear  |  blackout      (F1 = guide)")
        self.cmdline.returnPressed.connect(self._run_cmd)
        self.cmd_out = QLabel("")
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(2, 0, 2, 2)
        cl.addWidget(self.banner)
        cl.addWidget(vs, 1)
        row = QHBoxLayout()
        row.addWidget(self.cmdline, 1)
        cl.addLayout(row)
        cl.addWidget(self.cmd_out)
        self.setCentralWidget(central)

        self.st_out = QLabel("Output: off")
        self.st_in = QLabel("Input: off")
        self.st_show = QLabel("")
        for w in (self.st_show, self.st_out, self.st_in):
            self.statusBar().addPermanentWidget(w)
        QShortcut(QKeySequence("Escape"), self, activated=self.cmdline.clear)
        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self._go_current)
        self._update_banner()

    @staticmethod
    def _scroll(w: QWidget) -> QWidget:
        """Tab pages scroll instead of being squeezed on small / scaled screens."""
        from PySide6.QtWidgets import QFrame, QScrollArea
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(w)
        return sc

    def show_tab(self, w: QWidget) -> None:
        if w in self._tab_pages:
            self.tabs.setCurrentIndex(self._tab_pages[w])

    # ------------------------------------------------------------ DMX sources
    def prog_dmx(self) -> dict[int, bytes]:
        with self.engine.lock:
            return {u: bytes(b) for u, b in self.engine.universes.items()}

    def input_dmx(self) -> dict[int, bytes]:
        if not self.dmx_input:
            return {}
        return {0: bytes(self.dmx_input.snapshot())}

    def vis_dmx(self) -> dict[int, bytes]:
        src = self.vis_source
        cfg = self.engine.show.output
        alive = bool(self.dmx_input and self.dmx_input.alive)
        if src == "auto":
            src = ("console input" if cfg.input_merge == "replace" else "mix (HTP)") if alive else "program (PC)"
        if src == "console input":
            return self.input_dmx()
        prog = self.prog_dmx()
        if src.startswith("mix") and self.dmx_input:
            inp = self.dmx_input.snapshot()
            u0 = bytearray(prog.get(0, bytes(512)))
            for i in range(512):
                if inp[i] > u0[i]:
                    u0[i] = inp[i]
            prog[0] = bytes(u0)
        return prog

    def _send(self, frame) -> None:
        for o in list(self.outputs):
            o.send(frame)

    # -------------------------------------------------------------------- I/O
    def restart_io(self) -> None:
        for o in self.outputs:
            try:
                o.close()
            except Exception:
                pass
        self.outputs = []
        if self.dmx_input:
            self.dmx_input.stop()
            self.dmx_input = None
        cfg = self.engine.show.output
        errors = []
        try:
            if cfg.artnet_enabled:
                self.outputs.append(ArtNetOutput(cfg.artnet_target, cfg.artnet_universe_offset))
            if cfg.sacn_enabled:
                self.outputs.append(SacnOutput(cfg.sacn_universe_offset))
            if cfg.enttec_enabled and cfg.enttec_port:
                self.outputs.append(EnttecProOutput(cfg.enttec_port))
            if cfg.opendmx_enabled and cfg.opendmx_port:
                self.outputs.append(OpenDmxOutput(cfg.opendmx_port))
        except Exception as e:
            errors.append(f"Output: {e}")
        try:
            if cfg.input_mode == "artnet":
                ignore = local_ips() if cfg.artnet_enabled else set()
                self.dmx_input = ArtNetInput(cfg.input_universe, cfg.input_bind, ignore)
                self.dmx_input.start()
            elif cfg.input_mode == "enttec" and cfg.input_enttec_port:
                self.dmx_input = EnttecProInput(cfg.input_enttec_port)
                self.dmx_input.start()
        except Exception as e:
            errors.append(f"Input: {e}")
        self.midi.mapping = list(cfg.midi_map)
        if cfg.midi_in or cfg.midi_out:
            errors += [f"MIDI: {e}" for e in self.midi.open(cfg.midi_in, cfg.midi_out)]
        else:
            self.midi.close()
        if errors and not getattr(self, "_quiet_io", False):
            QMessageBox.warning(self, "Connections", "\n".join(errors))

    def stop_input(self) -> None:
        if self.dmx_input:
            self.dmx_input.stop()
            self.dmx_input = None

    def connect_wizard(self) -> None:
        d = ConnectDialog(self.engine.show.output, self.midi, self.engine.show.console_info.get("ip", ""),
                          self.stop_input, self)
        if d.exec():
            d.apply()
            self.mark_dirty()
        self.restart_io()

    def preferences(self) -> None:
        d = prefs.PreferencesDialog(self.settings, self.connect_wizard, self.io_settings, self)
        if d.exec():
            d.apply()
            self._apply_prefs()

    def _apply_prefs(self) -> None:
        s = self.settings
        self.execs.set_per_page(prefs.get(s, "per_page"))
        self.view.haze = prefs.get(s, "haze") / 100
        self.view.show_models = prefs.get(s, "models")
        self.view.show_labels = prefs.get(s, "labels")
        self.view._sync_overlay()
        self.haze_slider.setValue(prefs.get(s, "haze"))
        m = prefs.get(s, "autosave_min")
        if m > 0:
            self.autosave_timer.start(m * 60000) if hasattr(self, "autosave_timer") else None
        elif hasattr(self, "autosave_timer"):
            self.autosave_timer.stop()

    def _autosave(self) -> None:
        if not self.dirty:
            return
        try:
            if self.doc:
                companion.save(self.engine.show)
                self.statusBar().showMessage("Autosaved MiniDesk project (console file not touched)", 4000)
            elif self.path:
                self.engine.show.save(self.path)
                self.dirty = False
                self._update_title()
                self._update_banner()
        except OSError:
            pass

    def _usb_watch(self) -> None:
        """Plug & play: notice USB DMX interfaces being plugged in / out."""
        ports = {p["port"]: p for p in describe_serial_ports() if p["dmx"]}
        cfg = self.engine.show.output
        wanted = {x for x in ((cfg.enttec_port if cfg.enttec_enabled else ""),
                              (cfg.opendmx_port if cfg.opendmx_enabled else ""),
                              (cfg.input_enttec_port if cfg.input_mode == "enttec" else "")) if x}
        new = set(ports) - self._ports_seen
        gone = self._ports_seen - set(ports)
        self._ports_seen = set(ports)
        if gone & wanted:
            self.statusBar().showMessage(f"USB DMX interface unplugged: {', '.join(gone & wanted)}", 8000)
        if new & wanted and cfg.auto_reconnect:
            self._quiet_io = True
            self.restart_io()
            self._quiet_io = False
            self.statusBar().showMessage(f"USB DMX interface reconnected: {', '.join(new & wanted)}", 8000)
        elif new and not wanted:
            p = ports[sorted(new)[0]]
            self.statusBar().showMessage(f"{p['kind']} detected on {p['port']} – Console → Connect console to "
                                         "use it", 12000)
        self._usb_present = bool(wanted & set(ports)) if wanted else None

    def _feedback(self, st) -> None:
        if self.engine.show.output.midi_feedback:
            self.midi.send_note((st.pb.number - 1) % 128)

    def _midi_action(self, action: str, target: int, value: float, on: bool) -> None:
        e = self.engine
        st = next((x for x in e.states if x.pb.number == target), None)
        if action.startswith("exec_") and st is None:
            return
        if action == "exec_go" and on:
            e.go(st)
        elif action == "exec_back" and on:
            e.back(st)
        elif action == "exec_flash":
            e.set_flash(st, on)
        elif action == "exec_fader":
            e.set_level(st, value)
        elif action == "exec_stop" and on:
            e.stop(st, fade=True)
        elif action == "gm":
            self.gm.setValue(round(value * 100))
        elif action == "blackout" and on:
            self.a_bo.setChecked(not self.a_bo.isChecked())
        elif action == "bank_next" and on:
            self.execs.bank_step(1)
        elif action == "bank_prev" and on:
            self.execs.bank_step(-1)
        elif action == "release_all" and on:
            e.release_all()
        self.execs.sync()

    def io_settings(self) -> None:
        d = IOSettingsDialog(self.engine.show.output, self.engine.show.console_info.get("ip", ""), self)
        if d.exec():
            d.apply()
            self.restart_io()
            self.mark_dirty()

    def _status(self) -> None:
        cfg = self.engine.show.output
        outs = []
        if cfg.artnet_enabled:
            outs.append(f"Art-Net→{cfg.artnet_target}")
        if cfg.sacn_enabled:
            outs.append("sACN")
        if cfg.enttec_enabled:
            outs.append(f"USB {cfg.enttec_port}")
        self.st_out.setText("Output: " + (", ".join(outs) if outs else "off"))
        if self.dmx_input:
            di = self.dmx_input
            state = f"LIVE from {di.source}" if di.alive else "waiting for console…"
            self.st_in.setText(f"Input ({cfg.input_mode}): {state}  [{di.packets} pkts]")
            self.st_in.setStyleSheet("color:#7f7;" if di.alive else "color:#fa5;")
        else:
            self.st_in.setText("Input: off")
            self.st_in.setStyleSheet("")
        def led(w, state):
            w.setStyleSheet({"on": "color:#6fe08a; background:#16301f; border:1px solid #2a5a39;",
                             "wait": "color:#ffb45a; background:#33261a; border:1px solid #5c4326;",
                             "off": "color:#6b7080; background:#1a1c23; border:1px solid #262935;"}[state]
                            + "border-radius:10px; padding:2px 10px; margin:0 3px;")
        net = cfg.artnet_enabled or cfg.sacn_enabled or cfg.input_mode == "artnet"
        led(self.led_net, "off" if not net else
            ("on" if (cfg.input_mode != "artnet" or (self.dmx_input and self.dmx_input.alive)) else "wait"))
        usb = getattr(self, "_usb_present", None)
        led(self.led_usb, "off" if usb is None else ("on" if usb else "wait"))
        led(self.led_midi, "on" if (self.midi.inp or self.midi.out) else
            ("wait" if (cfg.midi_in or cfg.midi_out) else "off"))
        running = sum(1 for s in self.engine.states if s.running)
        self.st_show.setText(f"{len(self.engine.show.fixtures)} fixtures  |  {running} playback(s) running  |  "
                             f"{len(self.engine.effects)} effect(s) in programmer"
                             + ("  |  BLACKOUT" if self.engine.blackout else ""))

    # ---------------------------------------------------------------- state
    def mark_dirty(self, *_):
        if not self.dirty:
            self.dirty = True
            self._update_title()
            self._update_banner()

    def _update_title(self):
        name = self.engine.show.name
        src = os.path.basename(self.doc.path) if self.doc else (os.path.basename(self.path) if self.path else "")
        self.setWindowTitle(f"{'● ' if self.dirty else ''}{APP_NAME} – {src or name}")

    def _update_banner(self):
        if self.doc:
            state = ("<span style='color:#ffb347'>● unsaved changes – press <b>Ctrl+S</b></span>"
                     if self.dirty else "<span style='color:#7fdf7f'>✔ saved</span>")
            self.banner.setText(
                f"🔌 <b>Console file:</b> {self.doc.path}   {state}<br>"
                "<span style='color:#9aa'>Save writes fixture names, types, DMX addresses, groups and playback "
                "names straight into this .SHO (CRC updated, file re-read to verify). Copy it to the USB stick "
                "and load it on the console.</span>")
        elif self.path:
            self.banner.setText(f"🗂 <b>MiniDesk project:</b> {self.path}"
                                + ("   <span style='color:#ffb347'>● unsaved</span>" if self.dirty else ""))
        else:
            self.banner.setText("No file open – <b>File → Open console file (.SHO)</b> to start from your "
                                "console show, or patch fixtures in the Patch tab.")

    # ---------------------------------------------------------------- actions
    def _blackout(self, on: bool) -> None:
        self.engine.blackout = on

    def _gm(self, v: int) -> None:
        self.engine.grand_master = v / 100
        self.gm_lbl.setText(f"{v}%")

    def _view(self, mode: str) -> None:
        self.view.set_mode(mode)
        self.stage.sync_mode()
        if mode != "3d":
            self.show_tab(self.stage)

    def _vis_click(self, fid: int, add: bool) -> None:
        if fid < 0:
            self.engine.select([])
        else:
            self.engine.select([fid], add=add)
        self._selection_changed()

    def _select_from_patch(self, fids: list) -> None:
        self.engine.select(list(fids))
        self.view.selection = set(self.engine.selection)
        self.stage.refresh()

    def _selection_changed(self) -> None:
        self.view.selection = set(self.engine.selection)
        self.prog.rebuild()
        self.prog.fx.refresh()
        self.stage.refresh()
        self.sheet.grid.update()

    def _layout_edited(self) -> None:
        self.stage.refresh()
        self.mark_dirty()

    def _edit_playback(self, st) -> None:
        self.cues.bind(st)
        self.show_tab(self.cues)

    def _go_current(self) -> None:
        if self.cues.st:
            self.engine.go(self.cues.st)

    def _run_cmd(self) -> None:
        text = self.cmdline.text()
        try:
            msg = self.cmd.run(text)
        except Exception as e:   # a typo must never crash the app
            msg = f"Error: {e}"
        self.cmd_out.setText(f"> {text}    {msg}")
        self.cmdline.clear()
        if "stored" in msg:
            self.mark_dirty()
        self.execs.rebind()
        self._selection_changed()
        self.a_bo.setChecked(self.engine.blackout)

    def store_dialog(self) -> None:
        if self.engine.programmer_empty:
            QMessageBox.information(self, "Store", "The programmer is empty – set some values or start an effect.")
            return
        d = StoreDialog(self.engine, self.cues.st.pb if self.cues.st else None, self,
                        prefs.get(self.settings, "default_fade"))
        if d.exec():
            pb = d.apply()
            st = self.engine.state_for(pb)
            self.execs.rebind()
            self.execs.show_playback(st)
            self.cues.bind(st)
            self.mark_dirty()

    def _patch_changed(self) -> None:
        self.engine.rebuild_patch()
        self.sheet.rebuild()
        self.stage.refresh()
        self.view.update()
        self.mark_dirty()

    def show_guide(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("Panduan")
        d.resize(720, 620)
        lay = QVBoxLayout(d)
        t = QLabel(GUIDE)
        t.setWordWrap(True)
        t.setTextFormat(Qt.RichText)
        lay.addWidget(t, 1)
        b = QPushButton("OK")
        b.clicked.connect(d.accept)
        lay.addWidget(b)
        d.exec()

    def file_info(self) -> None:
        if not self.doc:
            QMessageBox.information(self, "Console file", "No console file is open.")
            return
        s = self.engine.show
        ci = s.console_info
        txt = (f"File: {self.doc.path}\nConsole: {ci.get('console')}   IP {ci.get('ip')} / {ci.get('netmask')}\n"
               f"Header CRC: {'valid' if self.doc.crc_ok() else 'INVALID'}\n"
               f"Fixture library: {sum(1 for t in s.types.values() if t.lib_index >= 0)} types\n"
               f"Fixtures: {len(s.fixtures)} ({sum(1 for f in s.fixtures if f.patched)} patched)\n"
               f"Groups: {len(s.groups)}\nPlaybacks: {len(s.playbacks)}\n"
               f"Companion project: {companion.path_for(s)}\nBackups: {companion.BACKUPS}")
        QMessageBox.information(self, "Console file", txt)

    # ------------------------------------------------------------------ files
    def _refresh_recent(self):
        self.m_recent.clear()
        for p in self.recent():
            a = QAction(p, self)
            a.triggered.connect(lambda _=False, path=p: self.open_path(path))
            self.m_recent.addAction(a)

    def recent(self) -> list[str]:
        r = self.settings.value("recent", [])
        if isinstance(r, str):
            r = [r]
        return [p for p in (r or []) if os.path.exists(p)][:8]

    def _add_recent(self, p: str):
        r = [x for x in self.recent() if x != p]
        self.settings.setValue("recent", [p] + r[:7])
        self._refresh_recent()

    def show_welcome(self):
        d = WelcomeDialog(self.recent(), self)
        if d.exec() and d.choice:
            k, p = d.choice
            if k == "sho":
                self.import_dialog()
            elif k == "mdshow":
                self.open_dialog()
            elif k == "path":
                self.open_path(p)

    def maybe_save(self) -> bool:
        if not self.dirty or not prefs.get(self.settings, "confirm_exit"):
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save your changes first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self.save()
        return True

    def set_show(self, show: Show, path: str | None, doc: ShoDocument | None = None) -> None:
        self.engine.release_all()
        self.engine.set_show(show)
        self.path, self.doc = path, doc
        self.view.set_show(show)
        self.sheet.rebuild()
        self.prog.rebuild()
        self.prog.fx.refresh()
        self.patch.rebuild()
        self.presets.rebuild()
        self.stage.refresh()
        self.cues.bind(None)
        if any(p.steps for p in show.playbacks):
            self.execs.bank.setCurrentText("With steps")
        self.execs.rebind()
        self.restart_io()
        self.dirty = False
        self._update_title()
        self._update_banner()

    def new_show(self) -> None:
        if not self.maybe_save():
            return
        show = Show()
        for t in builtin_types():
            show.add_type(t)
        self.set_show(show, None)

    def open_path(self, path: str) -> None:
        if not self.maybe_save():
            return
        try:
            if path.lower().endswith(".sho"):
                show, rep = import_sho(path)
                companion.remember_imported(show)
                restored = companion.load(show)
                doc = ShoDocument.open(path)
                doc.signature = step_signature(show)
                self.set_show(show, None, doc)
                msg = f"Opened {os.path.basename(path)}: {rep.summary()}"
                if restored:
                    msg += "  (stage layout & MiniDesk edits restored)"
                if not doc.crc_ok():
                    QMessageBox.warning(self, "Console file", "The header checksum of this file is not valid. "
                                        "It may be damaged – keep a copy before saving.")
                self.statusBar().showMessage(msg, 15000)
            else:
                self.set_show(Show.load(path), path)
            self._add_recent(path)
        except (ShoFormatError, OSError, ValueError, KeyError) as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Open", f"Could not open {path}:\n{e}")

    def open_dialog(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Open", "",
                                           "Shows (*.SHO *.sho *.mdshow);;Console file (*.SHO *.sho);;"
                                           "MiniDesk project (*.mdshow)")
        if p:
            self.open_path(p)

    def import_dialog(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Open CODE MINI 1000T show", "",
                                           "Console show (*.SHO *.sho);;All files (*)")
        if p:
            self.open_path(p)

    def _save_console(self, path: str | None = None) -> bool:
        show = self.engine.show
        with self.engine.lock:
            rep = self.doc.save(show, path=path, backup_dir=companion.BACKUPS)
        if rep.errors:
            QMessageBox.critical(self, "Save – not saved", rep.text())
            return False
        show.source_path = self.doc.path
        try:
            companion.save(show)
        except OSError as e:
            rep.not_saved.append(f"(companion project could not be written: {e})")
        self.doc.signature = step_signature(show)
        self.dirty = False
        self._update_title()
        self._update_banner()
        self.patch.rebuild()
        self.sheet.rebuild()
        self._add_recent(self.doc.path)
        box = QMessageBox(QMessageBox.Information if rep.verified else QMessageBox.Warning,
                          "Saved to console file", rep.text().split("\n")[0], parent=self)
        box.setInformativeText("Verification: " + ("OK – file re-read, CRC valid, content matches." if rep.verified
                                                   else "FAILED – do not use this file, restore the backup."))
        box.setDetailedText(rep.text())
        box.exec()
        return True

    def save(self) -> bool:
        if self.doc:
            return self._save_console()
        if not self.path:
            return self.save_as()
        self.engine.show.save(self.path)
        self.dirty = False
        self._update_title()
        self._update_banner()
        self.statusBar().showMessage(f"Saved {self.path}", 5000)
        return True

    def save_as(self) -> bool:
        if self.doc:
            p, _ = QFileDialog.getSaveFileName(self, "Save console file as", self.doc.path,
                                               "Console show (*.SHO)")
            if not p:
                return False
            if not p.upper().endswith(".SHO"):
                p += ".SHO"
            return self._save_console(p)
        return self.export_project()

    def export_project(self) -> bool:
        p, _ = QFileDialog.getSaveFileName(self, "Save MiniDesk project", f"{self.engine.show.name}.mdshow",
                                           "MiniDesk project (*.mdshow)")
        if not p:
            return False
        if not p.endswith(".mdshow"):
            p += ".mdshow"
        self.engine.show.save(p)
        if not self.doc:
            self.path = p
            self.dirty = False
            self._update_title()
            self._update_banner()
        self._add_recent(p)
        self.statusBar().showMessage(f"Saved {p}", 5000)
        return True

    def closeEvent(self, e):
        if not self.maybe_save():
            e.ignore()
            return
        self.runner.stop()
        for o in self.outputs:
            try:
                o.close()
            except Exception:
                pass
        if self.dmx_input:
            self.dmx_input.stop()
        self.midi.close()
        super().closeEvent(e)
