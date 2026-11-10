"""Main window: ties engine, visualizer, programmer, executors and I/O together."""
from __future__ import annotations

import os
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QSlider, QSplitter, QTabWidget, QToolBar, QVBoxLayout, QWidget,
                               QSpinBox)

from ..commands import CommandLine
from ..dmx_io import (ArtNetInput, ArtNetOutput, EnttecProInput, EnttecProOutput, SacnOutput,
                      local_ips)
from ..engine import Engine, EngineRunner
from ..model import Playback, Show, builtin_types
from ..sho_import import ShoFormatError, import_sho
from .cue_editor import CueEditor
from .dmx_monitor import DmxMonitor
from .executors import ExecutorBar
from .fixture_sheet import FixtureSheet
from .patch import PatchPanel
from .programmer import ProgrammerPanel
from .settings import IOSettingsDialog
from .theme import DARK_QSS
from .visualizer import StageView

APP_NAME = "MiniDesk – CODE MINI 1000T companion"


class StoreDialog(QDialog):
    def __init__(self, engine: Engine, current: Playback | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Store programmer")
        self.engine = engine
        f = QFormLayout(self)
        self.num = QSpinBox()
        self.num.setRange(1, 9999)
        nums = [p.number for p in engine.show.playbacks]
        self.num.setValue(current.number if current else (max(nums, default=0) + 1))
        self.name = QLineEdit()
        self.mode = QComboBox()
        self.mode.addItems(["add step", "merge into last step", "overwrite last step"])
        self.fade = QDoubleSpinBox()
        self.fade.setRange(0, 600)
        self.fade.setSuffix(" s")
        self.lbl = QLabel()
        self.num.valueChanged.connect(self._upd)
        f.addRow("Executor number", self.num)
        f.addRow("", self.lbl)
        f.addRow("Name (new playback)", self.name)
        f.addRow("Mode", self.mode)
        f.addRow("Step fade", self.fade)
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
        self.lbl.setText(f"existing: {p.name} ({len(p.steps)} steps)" if p else "new playback will be created")

    def apply(self) -> Playback:
        pb = self._pb()
        if pb is None:
            pb = Playback(name=self.name.text() or f"Playback {self.num.value()}", number=self.num.value(),
                          bank="User", mode="cuelist")
            self.engine.show.playbacks.append(pb)
            self.engine.rebuild_patch()
        mode = {0: "add", 1: "merge", 2: "overwrite"}[self.mode.currentIndex()]
        self.engine.store(pb, mode, fade=self.fade.value())
        return pb


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1600, 980)
        self.setStyleSheet(DARK_QSS)
        self.path: str | None = None
        show = Show()
        for t in builtin_types():
            show.add_type(t)
        self.engine = Engine(show)
        self.outputs = []
        self.dmx_input = None
        self.cmd = CommandLine(self.engine)
        self.vis_source = "auto"
        self._build()
        self.runner = EngineRunner(self.engine, self._send)
        self.runner.start()
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._status)
        self.status_timer.start(500)
        if path:
            self.open_path(path)

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(text, fn, shortcut=None, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(fn)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setCheckable(checkable)
            tb.addAction(a)
            return a

        act("New", self.new_show)
        act("Open…", self.open_dialog, "Ctrl+O")
        act("Save", self.save, "Ctrl+S")
        act("Save as…", self.save_as)
        act("Import MINI 1000 .SHO…", self.import_dialog, "Ctrl+I")
        tb.addSeparator()
        act("DMX I/O…", self.io_settings)
        tb.addSeparator()
        self.a_bo = act("BLACKOUT", self._blackout, None, True)
        tb.addWidget(QLabel(" GM "))
        self.gm = QSlider(Qt.Horizontal)
        self.gm.setRange(0, 100)
        self.gm.setValue(100)
        self.gm.setFixedWidth(120)
        self.gm.valueChanged.connect(lambda v: setattr(self.engine, "grand_master", v / 100))
        tb.addWidget(self.gm)
        tb.addSeparator()
        tb.addWidget(QLabel(" Visualizer source "))
        self.src = QComboBox()
        self.src.addItems(["auto", "program (PC)", "console input", "mix (HTP)"])
        self.src.currentTextChanged.connect(lambda t: setattr(self, "vis_source", t))
        tb.addWidget(self.src)
        act("3D / Top", lambda: self.view.toggle_mode())
        act("Reset camera", lambda: self.view.reset_camera())
        tb.addWidget(QLabel(" Haze "))
        haze = QSlider(Qt.Horizontal)
        haze.setRange(0, 100)
        haze.setValue(35)
        haze.setFixedWidth(90)
        haze.valueChanged.connect(lambda v: setattr(self.view, "haze", v / 100))
        tb.addWidget(haze)

        self.view = StageView(self.engine.show, self.vis_dmx)
        self.view.fixtureClicked.connect(self._vis_click)
        self.view.fixtureMoved.connect(lambda _f: None)

        self.sheet = FixtureSheet(self.engine, self.vis_dmx)
        self.sheet.selectionChanged.connect(self._selection_changed)
        self.prog = ProgrammerPanel(self.engine)
        self.prog.storeRequested.connect(self.store_dialog)
        self.prog.programmerChanged.connect(self.sheet.grid.update)
        self.cues = CueEditor(self.engine)
        self.cues.changed.connect(lambda: self.execs.rebind())
        self.cues.loadedToProgrammer.connect(self._selection_changed)
        self.patch = PatchPanel(self.engine)
        self.patch.changed.connect(self._patch_changed)
        self.monitor = DmxMonitor({"program output": self.prog_dmx, "console input": self.input_dmx,
                                   "visualizer": self.vis_dmx}, lambda: self.engine.show)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.sheet, "Fixtures / Groups")
        self.tabs.addTab(self.prog, "Programmer")
        self.tabs.addTab(self.cues, "Cues")
        self.tabs.addTab(self.patch, "Patch")
        self.tabs.addTab(self.monitor, "DMX")

        top = QSplitter(Qt.Horizontal)
        top.addWidget(self.view)
        top.addWidget(self.tabs)
        top.setSizes([900, 700])
        self.execs = ExecutorBar(self.engine)
        self.execs.playbackSelected.connect(self._edit_playback)
        vs = QSplitter(Qt.Vertical)
        vs.addWidget(top)
        vs.addWidget(self.execs)
        vs.setSizes([640, 320])

        self.cmdline = QLineEdit()
        self.cmdline.setObjectName("cmd")
        self.cmdline.setPlaceholderText("Command:  fixture 1 thru 8 at 50  |  group 2 at full  |  go 3  |  "
                                        "store 5  |  clear  |  blackout")
        self.cmdline.returnPressed.connect(self._run_cmd)
        self.cmd_out = QLabel("")
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(2, 2, 2, 2)
        cl.addWidget(vs, 1)
        cl.addWidget(self.cmdline)
        cl.addWidget(self.cmd_out)
        self.setCentralWidget(central)

        self.st_out = QLabel("Output: off")
        self.st_in = QLabel("Input: off")
        self.st_show = QLabel("")
        for w in (self.st_show, self.st_out, self.st_in):
            self.statusBar().addPermanentWidget(w)
        QShortcut(QKeySequence("Escape"), self, activated=self._escape)
        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self._go_current)

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
            if alive:
                src = "console input" if cfg.input_merge == "replace" else "mix (HTP)"
            else:
                src = "program (PC)"
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
        if errors:
            QMessageBox.warning(self, "DMX I/O", "\n".join(errors))

    def io_settings(self) -> None:
        d = IOSettingsDialog(self.engine.show.output, self.engine.show.console_info.get("ip", ""), self)
        if d.exec():
            d.apply()
            self.restart_io()

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
        running = sum(1 for s in self.engine.states if s.running)
        self.st_show.setText(f"{self.engine.show.name}  |  {len(self.engine.show.fixtures)} fixtures  |  "
                             f"{running} playback(s) running" + ("  |  BLACKOUT" if self.engine.blackout else ""))

    # ---------------------------------------------------------------- actions
    def _blackout(self, on: bool) -> None:
        self.engine.blackout = on

    def _vis_click(self, fid: int, add: bool) -> None:
        self.engine.select([fid], add=add)
        self._selection_changed()

    def _selection_changed(self) -> None:
        self.view.selection = set(self.engine.selection)
        self.prog.rebuild()
        self.sheet.grid.update()

    def _edit_playback(self, st) -> None:
        self.cues.bind(st)
        self.tabs.setCurrentWidget(self.cues)

    def _go_current(self) -> None:
        if self.cues.st:
            self.engine.go(self.cues.st)

    def _escape(self) -> None:
        self.cmdline.clear()

    def _run_cmd(self) -> None:
        text = self.cmdline.text()
        try:
            msg = self.cmd.run(text)
        except Exception as e:   # user typo should never crash the app
            msg = f"Error: {e}"
        self.cmd_out.setText(f"> {text}    {msg}")
        self.cmdline.clear()
        self.execs.rebind()
        self._selection_changed()
        self.a_bo.setChecked(self.engine.blackout)

    def store_dialog(self) -> None:
        if not self.engine.programmer:
            QMessageBox.information(self, "Store", "The programmer is empty.")
            return
        d = StoreDialog(self.engine, self.cues.st.pb if self.cues.st else None, self)
        if d.exec():
            pb = d.apply()
            st = self.engine.state_for(pb)
            self.execs.rebind()
            self.execs.show_playback(st)
            self.cues.bind(st)

    def _patch_changed(self) -> None:
        self.engine.rebuild_patch()
        self.sheet.rebuild()
        self.view.update()

    # ------------------------------------------------------------------ files
    def set_show(self, show: Show, path: str | None) -> None:
        self.engine.release_all()
        self.engine.set_show(show)
        self.path = path
        self.view.set_show(show)
        self.sheet.rebuild()
        self.prog.rebuild()
        self.patch.rebuild()
        self.cues.bind(None)
        if any(p.steps for p in show.playbacks):
            self.execs.bank.setCurrentText("With steps")
        self.execs.rebind()
        self.restart_io()
        self.setWindowTitle(f"{APP_NAME}  –  {show.name}")

    def new_show(self) -> None:
        show = Show()
        for t in builtin_types():
            show.add_type(t)
        self.set_show(show, None)

    def open_path(self, path: str) -> None:
        try:
            if path.lower().endswith(".sho"):
                show, rep = import_sho(path)
                self.set_show(show, None)
                self.statusBar().showMessage(f"Imported {os.path.basename(path)}: {rep.summary()}", 15000)
            else:
                self.set_show(Show.load(path), path)
        except (ShoFormatError, OSError, ValueError, KeyError) as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Open", f"Could not open {path}:\n{e}")

    def open_dialog(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Open show", "",
                                           "Shows (*.mdshow *.SHO *.sho);;MiniDesk show (*.mdshow);;"
                                           "MINI 1000 show (*.SHO *.sho)")
        if p:
            self.open_path(p)

    def import_dialog(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Import CODE MINI 1000T show", "",
                                           "MINI 1000 show (*.SHO *.sho);;All files (*)")
        if p:
            self.open_path(p)

    def save(self) -> None:
        if not self.path:
            return self.save_as()
        self.engine.show.save(self.path)
        self.statusBar().showMessage(f"Saved {self.path}", 5000)

    def save_as(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Save show", f"{self.engine.show.name}.mdshow",
                                           "MiniDesk show (*.mdshow)")
        if p:
            if not p.endswith(".mdshow"):
                p += ".mdshow"
            self.path = p
            self.save()

    def closeEvent(self, e):
        self.runner.stop()
        for o in self.outputs:
            try:
                o.close()
            except Exception:
                pass
        if self.dmx_input:
            self.dmx_input.stop()
        super().closeEvent(e)
