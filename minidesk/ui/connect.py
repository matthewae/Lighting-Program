"""Connect-console wizard: Art-Net scan, USB DMX devices, MIDI ports + MIDI learn."""
from __future__ import annotations

import threading

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from ..dmx_io import all_local_ipv4, describe_serial_ports, same_subnet, scan_artnet
from ..midi import ACTIONS, MidiManager
from ..model import OutputConfig


class ConnectDialog(QDialog):
    scanned = Signal(dict)

    def __init__(self, cfg: OutputConfig, midi: MidiManager, console_ip: str, stop_input, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect console – DMX / Art-Net / MIDI")
        self.resize(820, 620)
        self.cfg, self.midi, self.console_ip, self.stop_input = cfg, midi, console_ip, stop_input
        self.map = [dict(m) for m in cfg.midi_map]
        lay = QVBoxLayout(self)
        intro = QLabel("Choose how the <b>CODE MINI 1000T</b> is connected to this PC. MiniDesk can "
                       "<b>listen</b> to the console (live 3D view of what you program on the console) and "
                       "<b>send</b> DMX to the fixtures itself.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._artnet_tab(), "🌐 Art-Net (network)")
        self.tabs.addTab(self._usb_tab(), "🔌 USB DMX")
        self.tabs.addTab(self._midi_tab(), "🎹 MIDI")
        lay.addWidget(self.tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.scanned.connect(self._show_scan)

    # ------------------------------------------------------------ Art-Net
    def _artnet_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        ips = all_local_ipv4()
        ok = [ip for ip in ips if self.console_ip and same_subnet(ip, self.console_ip)]
        txt = f"This PC: {', '.join(ips) or 'no network'}"
        if self.console_ip:
            txt += f"<br>Console IP stored in the show file: <b>{self.console_ip}</b> – "
            txt += ("<span style='color:#7f7'>PC is in the same network ✔</span>" if ok else
                    "<span style='color:#fa5'>PC is NOT in the same network: give the PC a fixed IP like "
                    f"{'.'.join(self.console_ip.split('.')[:3])}.10 / 255.255.255.0</span>")
        lab = QLabel(txt)
        lab.setWordWrap(True)
        v.addWidget(lab)
        steps = QLabel("1. Connect console and PC with a network cable (or the same switch).<br>"
                       "2. Enable Art-Net output on the console.<br>3. Press <b>Scan</b>, select the console "
                       "and press <b>Use as console input</b>.")
        steps.setWordWrap(True)
        v.addWidget(steps)
        h = QHBoxLayout()
        self.b_scan = QPushButton("🔍 Scan network (3 s)")
        self.b_scan.clicked.connect(self._scan)
        h.addWidget(self.b_scan)
        self.scan_state = QLabel("")
        h.addWidget(self.scan_state, 1)
        v.addLayout(h)
        self.t_net = QTableWidget(0, 4)
        self.t_net.setHorizontalHeaderLabels(["IP", "Name", "Universes", "DMX packets"])
        self.t_net.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.t_net.setSelectionBehavior(QAbstractItemView.SelectRows)
        v.addWidget(self.t_net, 1)
        h2 = QHBoxLayout()
        b_use = QPushButton("Use as console input")
        b_use.setObjectName("go")
        b_use.clicked.connect(self._use_net)
        h2.addWidget(b_use)
        h2.addWidget(QLabel("Universe"))
        self.net_uni = QSpinBox()
        self.net_uni.setRange(0, 32767)
        self.net_uni.setValue(self.cfg.input_universe)
        h2.addWidget(self.net_uni)
        h2.addStretch(1)
        v.addLayout(h2)
        g = QGroupBox("Send DMX from MiniDesk over Art-Net")
        gh = QHBoxLayout(g)
        self.an_out = QCheckBox("Enable Art-Net output")
        self.an_out.setChecked(self.cfg.artnet_enabled)
        self.an_ip = QLineEdit(self.cfg.artnet_target)
        gh.addWidget(self.an_out)
        gh.addWidget(QLabel("to"))
        gh.addWidget(self.an_ip)
        v.addWidget(g)
        self.net_state = QLabel(self._input_text())
        v.addWidget(self.net_state)
        return w

    def _input_text(self) -> str:
        c = self.cfg
        if c.input_mode == "artnet":
            return f"Current console input: Art-Net universe {c.input_universe}"
        if c.input_mode == "enttec":
            return f"Current console input: USB DMX {c.input_enttec_port}"
        return "Current console input: none"

    def _scan(self):
        self.b_scan.setEnabled(False)
        self.scan_state.setText("scanning…")
        self.stop_input()              # free UDP port 6454 while scanning

        def run():
            self.scanned.emit(scan_artnet(3.0))
        threading.Thread(target=run, daemon=True).start()

    def _show_scan(self, res: dict):
        self.b_scan.setEnabled(True)
        rows = {}
        for n in res.get("nodes", []):
            rows[n["ip"]] = [n["ip"], n["long"] or n["short"], "", ""]
        for ip, s in res.get("sources", {}).items():
            r = rows.setdefault(ip, [ip, "", "", ""])
            r[2] = ", ".join(str(u) for u in s["universes"])
            r[3] = str(s["packets"])
        if self.console_ip and self.console_ip in rows and not rows[self.console_ip][1]:
            rows[self.console_ip][1] = "CODE MINI 1000T (from show file)"
        self.t_net.setRowCount(len(rows))
        for i, r in enumerate(rows.values()):
            for c, v in enumerate(r):
                self.t_net.setItem(i, c, QTableWidgetItem(v))
        err = res.get("error")
        self.scan_state.setText(err or (f"{len(rows)} device(s) found" if rows else
                                        "nothing found – is Art-Net enabled on the console and the PC IP "
                                        "in the same network?"))
        if rows:
            self.t_net.selectRow(0)

    def _use_net(self):
        r = self.t_net.currentRow()
        if r >= 0:
            unis = (self.t_net.item(r, 2).text() or "").split(",")
            if unis and unis[0].strip().isdigit():
                self.net_uni.setValue(int(unis[0]))
        self.cfg.input_mode = "artnet"
        self.cfg.input_universe = self.net_uni.value()
        self.cfg.input_bind = "0.0.0.0"
        self.net_state.setText(self._input_text())

    # ---------------------------------------------------------------- USB
    def _usb_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel("USB DMX interfaces found on this PC. Plug the interface in and press <b>Refresh</b>. "
                     "<br>• To <b>listen to the console</b>: console DMX OUT → interface DMX IN (ENTTEC USB "
                     "Pro), then <i>Use as console input</i>.<br>• To <b>drive fixtures</b> from MiniDesk: "
                     "interface DMX OUT → fixtures, then <i>Use as output</i>.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.t_usb = QTableWidget(0, 3)
        self.t_usb.setHorizontalHeaderLabels(["Port", "Type", "Description"])
        self.t_usb.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.t_usb.setSelectionBehavior(QAbstractItemView.SelectRows)
        v.addWidget(self.t_usb, 1)
        h = QHBoxLayout()
        for text, fn in (("⟳ Refresh", self._refresh_usb), ("Use as console input", self._usb_in),
                         ("Use as output (USB Pro)", self._usb_out), ("Use as output (Open DMX)", self._usb_open),
                         ("Disable USB", self._usb_off)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            h.addWidget(b)
        v.addLayout(h)
        self.auto_rc = QCheckBox("Reconnect automatically when the interface is unplugged / plugged in")
        self.auto_rc.setChecked(self.cfg.auto_reconnect)
        v.addWidget(self.auto_rc)
        self.usb_state = QLabel("")
        v.addWidget(self.usb_state)
        self._refresh_usb()
        return w

    def _refresh_usb(self):
        ports = describe_serial_ports()
        self.t_usb.setRowCount(len(ports))
        for i, p in enumerate(ports):
            for c, k in enumerate(("port", "kind", "desc")):
                self.t_usb.setItem(i, c, QTableWidgetItem(p[k]))
        if ports:
            self.t_usb.selectRow(0)
        self._usb_state()

    def _usb_state(self):
        c = self.cfg
        outs = [x for x in (f"USB Pro {c.enttec_port}" if c.enttec_enabled else "",
                            f"Open DMX {c.opendmx_port}" if c.opendmx_enabled else "") if x]
        self.usb_state.setText(f"Input: {c.input_enttec_port if c.input_mode == 'enttec' else '—'}    "
                               f"Output: {', '.join(outs) or '—'}")

    def _port(self) -> str:
        r = self.t_usb.currentRow()
        if r < 0:
            QMessageBox.information(self, "USB", "No USB DMX interface selected / found.")
            return ""
        return self.t_usb.item(r, 0).text()

    def _usb_in(self):
        p = self._port()
        if p:
            self.cfg.input_mode, self.cfg.input_enttec_port = "enttec", p
            self._usb_state()

    def _usb_out(self):
        p = self._port()
        if p:
            self.cfg.enttec_enabled, self.cfg.enttec_port = True, p
            self.cfg.opendmx_enabled = False
            self._usb_state()

    def _usb_open(self):
        p = self._port()
        if p:
            self.cfg.opendmx_enabled, self.cfg.opendmx_port = True, p
            self.cfg.enttec_enabled = False
            self._usb_state()

    def _usb_off(self):
        self.cfg.enttec_enabled = self.cfg.opendmx_enabled = False
        if self.cfg.input_mode == "enttec":
            self.cfg.input_mode = "none"
        self._usb_state()

    # --------------------------------------------------------------- MIDI
    def _midi_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        if not self.midi.available:
            lab = QLabel("No MIDI system found. On Windows MIDI works out of the box; on Linux/macOS install "
                         "<code>pip install python-rtmidi</code>.")
            lab.setWordWrap(True)
            v.addWidget(lab)
        info = QLabel("Use the console's MIDI port or any MIDI controller to fire MiniDesk playbacks. "
                      "<b>Learn</b>: choose an action, press Learn, then press the key / move the fader on the "
                      "console. MIDI out sends a note when a playback is triggered.")
        info.setWordWrap(True)
        v.addWidget(info)
        h = QHBoxLayout()
        h.addWidget(QLabel("MIDI in"))
        self.m_in = QComboBox()
        self.m_in.addItems([""] + self.midi.inputs())
        self.m_in.setCurrentText(self.cfg.midi_in)
        h.addWidget(self.m_in, 1)
        h.addWidget(QLabel("MIDI out"))
        self.m_out = QComboBox()
        self.m_out.addItems([""] + self.midi.outputs())
        self.m_out.setCurrentText(self.cfg.midi_out)
        h.addWidget(self.m_out, 1)
        b_open = QPushButton("Open ports")
        b_open.clicked.connect(self._open_midi)
        h.addWidget(b_open)
        v.addLayout(h)
        self.m_fb = QCheckBox("Send MIDI note on playback GO (note = playback number − 1)")
        self.m_fb.setChecked(self.cfg.midi_feedback)
        v.addWidget(self.m_fb)
        self.m_last = QLabel("Last MIDI message: –")
        v.addWidget(self.m_last)
        self.t_map = QTableWidget(0, 4)
        self.t_map.setHorizontalHeaderLabels(["MIDI", "Action", "Playback #", ""])
        self.t_map.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        v.addWidget(self.t_map, 1)
        h2 = QHBoxLayout()
        self.a_combo = QComboBox()
        for k, label in ACTIONS.items():
            self.a_combo.addItem(label, k)
        self.a_target = QSpinBox()
        self.a_target.setRange(1, 9999)
        self.b_learn = QPushButton("🎯 Learn")
        self.b_learn.clicked.connect(self._learn)
        h2.addWidget(QLabel("Action"))
        h2.addWidget(self.a_combo, 1)
        h2.addWidget(QLabel("Playback #"))
        h2.addWidget(self.a_target)
        h2.addWidget(self.b_learn)
        b_auto = QPushButton("Auto map 15 notes/CC → bank 1")
        b_auto.clicked.connect(self._automap)
        b_clear = QPushButton("Clear all")
        b_clear.clicked.connect(lambda: (self.map.clear(), self._fill_map()))
        h2.addWidget(b_auto)
        h2.addWidget(b_clear)
        v.addLayout(h2)
        self._fill_map()
        self._poll = QTimer(self)
        self._poll.timeout.connect(lambda: self.m_last.setText(f"Last MIDI message: {self.midi.last or '–'}"))
        self._poll.start(200)
        return w

    def _open_midi(self):
        errs = self.midi.open(self.m_in.currentText(), self.m_out.currentText())
        if errs:
            QMessageBox.warning(self, "MIDI", "\n".join(errs))

    def _fill_map(self):
        self.t_map.setRowCount(len(self.map))
        for i, m in enumerate(self.map):
            self.t_map.setItem(i, 0, QTableWidgetItem(f"{m['kind']} ch{m['ch'] + 1} #{m['num']}"))
            self.t_map.setItem(i, 1, QTableWidgetItem(ACTIONS.get(m["action"], m["action"])))
            self.t_map.setItem(i, 2, QTableWidgetItem(str(m.get("target", ""))))
            b = QPushButton("✕")
            b.clicked.connect(lambda _=False, k=i: (self.map.pop(k), self._fill_map()))
            self.t_map.setCellWidget(i, 3, b)

    def _learn(self):
        if not self.midi.inp:
            self._open_midi()
        if not self.midi.inp:
            QMessageBox.information(self, "MIDI", "Open a MIDI input first.")
            return
        self.b_learn.setText("… press a key / move a fader")
        action, target = self.a_combo.currentData(), self.a_target.value()

        def got(msg):
            self.map = [m for m in self.map if not (m["kind"] == msg["kind"] and m["ch"] == msg["ch"]
                                                    and m["num"] == msg["num"])]
            self.map.append({"kind": msg["kind"], "ch": msg["ch"], "num": msg["num"],
                             "action": action, "target": target})
            QTimer.singleShot(0, lambda: (self._fill_map(), self.b_learn.setText("🎯 Learn"),
                                          self.a_target.setValue(target + 1)))
        self.midi.learn = got

    def _automap(self):
        self.map = MidiManager.default_bank_map(1, 15)
        self._fill_map()

    # --------------------------------------------------------------- apply
    def apply(self) -> None:
        c = self.cfg
        c.artnet_enabled = self.an_out.isChecked()
        c.artnet_target = self.an_ip.text().strip() or "255.255.255.255"
        c.auto_reconnect = self.auto_rc.isChecked()
        c.midi_in, c.midi_out = self.m_in.currentText(), self.m_out.currentText()
        c.midi_feedback = self.m_fb.isChecked()
        c.midi_map = self.map
        self.midi.learn = None
