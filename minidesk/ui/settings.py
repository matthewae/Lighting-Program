"""Output / input (console link) settings dialog."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QLabel, QLineEdit, QSpinBox, QVBoxLayout)

from ..dmx_io import list_serial_ports
from ..model import OutputConfig


class IOSettingsDialog(QDialog):
    def __init__(self, cfg: OutputConfig, console_ip: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("DMX Output & Console Input")
        self.cfg = cfg
        ports = list_serial_ports()
        lay = QVBoxLayout(self)

        g_in = QGroupBox("Input from CODE MINI 1000T console (live visualizer)")
        f = QFormLayout(g_in)
        self.in_mode = QComboBox()
        self.in_mode.addItems(["none", "artnet", "enttec"])
        self.in_mode.setCurrentText(cfg.input_mode)
        self.in_uni = QSpinBox()
        self.in_uni.setRange(0, 32767)
        self.in_uni.setValue(cfg.input_universe)
        self.in_bind = QLineEdit(cfg.input_bind)
        self.in_port = QComboBox()
        self.in_port.setEditable(True)
        self.in_port.addItems(ports)
        self.in_port.setCurrentText(cfg.input_enttec_port)
        self.in_merge = QComboBox()
        self.in_merge.addItems(["replace", "htp"])
        self.in_merge.setCurrentText(cfg.input_merge)
        f.addRow("Input mode", self.in_mode)
        f.addRow("Art-Net universe (0 = first)", self.in_uni)
        f.addRow("Listen on IP", self.in_bind)
        f.addRow("USB DMX Pro port", self.in_port)
        f.addRow("Visualizer: console vs PC", self.in_merge)
        hint = ("Set the PC to the same network as the console"
                + (f" (console IP in show file: {console_ip})" if console_ip else "")
                + " and enable Art-Net output on the console.\n"
                  "'replace' shows only the console, 'htp' mixes console + this program.")
        lab = QLabel(hint)
        lab.setWordWrap(True)
        f.addRow(lab)
        lay.addWidget(g_in)

        g_out = QGroupBox("DMX output from this program")
        o = QFormLayout(g_out)
        self.an = QCheckBox("Art-Net")
        self.an.setChecked(cfg.artnet_enabled)
        self.an_ip = QLineEdit(cfg.artnet_target)
        self.an_off = QSpinBox()
        self.an_off.setRange(0, 32000)
        self.an_off.setValue(cfg.artnet_universe_offset)
        self.sa = QCheckBox("sACN / E1.31 (multicast)")
        self.sa.setChecked(cfg.sacn_enabled)
        self.sa_off = QSpinBox()
        self.sa_off.setRange(1, 63999)
        self.sa_off.setValue(cfg.sacn_universe_offset)
        self.en = QCheckBox("ENTTEC DMX USB Pro (universe 1)")
        self.en.setChecked(cfg.enttec_enabled)
        self.en_port = QComboBox()
        self.en_port.setEditable(True)
        self.en_port.addItems(ports)
        self.en_port.setCurrentText(cfg.enttec_port)
        o.addRow(self.an)
        o.addRow("Art-Net target IP (broadcast ok)", self.an_ip)
        o.addRow("Art-Net universe offset", self.an_off)
        o.addRow(self.sa)
        o.addRow("sACN first universe", self.sa_off)
        o.addRow(self.en)
        o.addRow("Serial port", self.en_port)
        self.od = QCheckBox("Open DMX (FTDI cable, universe 1)")
        self.od.setChecked(cfg.opendmx_enabled)
        self.od_port = QComboBox()
        self.od_port.setEditable(True)
        self.od_port.addItems(ports)
        self.od_port.setCurrentText(cfg.opendmx_port)
        o.addRow(self.od)
        o.addRow("Serial port ", self.od_port)
        warn = QLabel("Do not output to the same fixtures the console is driving at the same time "
                      "unless you know your network merges the sources.")
        warn.setWordWrap(True)
        o.addRow(warn)
        lay.addWidget(g_out)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def apply(self) -> None:
        c = self.cfg
        c.input_mode = self.in_mode.currentText()
        c.input_universe = self.in_uni.value()
        c.input_bind = self.in_bind.text().strip() or "0.0.0.0"
        c.input_enttec_port = self.in_port.currentText()
        c.input_merge = self.in_merge.currentText()
        c.artnet_enabled = self.an.isChecked()
        c.artnet_target = self.an_ip.text().strip() or "255.255.255.255"
        c.artnet_universe_offset = self.an_off.value()
        c.sacn_enabled = self.sa.isChecked()
        c.sacn_universe_offset = self.sa_off.value()
        c.enttec_enabled = self.en.isChecked()
        c.enttec_port = self.en_port.currentText()
        c.opendmx_enabled = self.od.isChecked()
        c.opendmx_port = self.od_port.currentText()
