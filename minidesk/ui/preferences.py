"""Application preferences (stored with QSettings, per user)."""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QLabel, QPushButton, QSpinBox, QVBoxLayout)

DEFAULTS = {"splash": True, "welcome": True, "per_page": 15, "default_fade": 0.0, "haze": 35,
            "models": True, "labels": True, "autosave_min": 0, "confirm_exit": True}


def get(settings: QSettings, key: str):
    d = DEFAULTS[key]
    return settings.value(key, d, type=type(d))


class PreferencesDialog(QDialog):
    def __init__(self, settings: QSettings, open_connect=None, open_io=None, parent=None):
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle("Preferences")
        self.resize(480, 520)
        lay = QVBoxLayout(self)
        g = QGroupBox("Start-up")
        f = QFormLayout(g)
        self.splash = QCheckBox("Show splash screen")
        self.splash.setChecked(get(settings, "splash"))
        self.welcome = QCheckBox("Show welcome screen when no file is given")
        self.welcome.setChecked(get(settings, "welcome"))
        f.addRow(self.splash)
        f.addRow(self.welcome)
        lay.addWidget(g)
        g2 = QGroupBox("Playback / programming")
        f2 = QFormLayout(g2)
        self.per_page = QComboBox()
        self.per_page.addItems(["10", "12", "15", "20"])
        self.per_page.setCurrentText(str(get(settings, "per_page")))
        self.fade = QDoubleSpinBox()
        self.fade.setRange(0, 60)
        self.fade.setSuffix(" s")
        self.fade.setValue(get(settings, "default_fade"))
        self.autosave = QSpinBox()
        self.autosave.setRange(0, 60)
        self.autosave.setSuffix(" min (0 = off)")
        self.autosave.setValue(get(settings, "autosave_min"))
        self.autosave.setToolTip("Autosave the MiniDesk project (stage layout, effects, cues). "
                                 "The console .SHO file is only written when you press Save.")
        f2.addRow("Playbacks per bank", self.per_page)
        f2.addRow("Default fade for new cues", self.fade)
        f2.addRow("Autosave MiniDesk project", self.autosave)
        lay.addWidget(g2)
        g3 = QGroupBox("Stage view")
        f3 = QFormLayout(g3)
        self.haze = QSpinBox()
        self.haze.setRange(0, 100)
        self.haze.setSuffix(" %")
        self.haze.setValue(get(settings, "haze"))
        self.models = QCheckBox("Draw 3D fixture models")
        self.models.setChecked(get(settings, "models"))
        self.labels = QCheckBox("Show fixture numbers / names")
        self.labels.setChecked(get(settings, "labels"))
        f3.addRow("Haze", self.haze)
        f3.addRow(self.models)
        f3.addRow(self.labels)
        lay.addWidget(g3)
        g4 = QGroupBox("Connections")
        v4 = QVBoxLayout(g4)
        if open_connect:
            b = QPushButton("Connect console (DMX / Art-Net / MIDI)…")
            b.clicked.connect(open_connect)
            v4.addWidget(b)
        if open_io:
            b2 = QPushButton("Advanced DMX input / output…")
            b2.clicked.connect(open_io)
            v4.addWidget(b2)
        lay.addWidget(g4)
        self.confirm = QCheckBox("Ask to save unsaved changes on exit")
        self.confirm.setChecked(get(settings, "confirm_exit"))
        lay.addWidget(self.confirm)
        lay.addWidget(QLabel("Some options take effect after a restart."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def apply(self) -> None:
        s = self.s
        s.setValue("splash", self.splash.isChecked())
        s.setValue("welcome", self.welcome.isChecked())
        s.setValue("per_page", int(self.per_page.currentText()))
        s.setValue("default_fade", self.fade.value())
        s.setValue("autosave_min", self.autosave.value())
        s.setValue("haze", self.haze.value())
        s.setValue("models", self.models.isChecked())
        s.setValue("labels", self.labels.isChecked())
        s.setValue("confirm_exit", self.confirm.isChecked())
