DARK_QSS = """
QWidget { background: #15161c; color: #d6d7de; font-size: 10pt; }
QMainWindow::separator { background: #2a2c36; width: 4px; height: 4px; }
QTabWidget::pane { border: 1px solid #2a2c36; }
QTabBar::tab { background: #1d1f27; padding: 6px 12px; border: 1px solid #2a2c36; border-bottom: none; }
QTabBar::tab:selected { background: #2b2e3b; color: #ffcc33; }
QPushButton { background: #262934; border: 1px solid #3a3d4b; border-radius: 4px; padding: 5px 8px; }
QPushButton:hover { background: #30344a; }
QPushButton:pressed, QPushButton:checked { background: #b8860b; color: #111; }
QPushButton#go { background: #1f5f2a; font-weight: bold; }
QPushButton#go:pressed { background: #3fbf55; }
QPushButton#flash { background: #5a2a1f; }
QPushButton#flash:pressed { background: #ff7040; color: #111; }
QPushButton#danger { background: #6b1f1f; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #0f1015; border: 1px solid #3a3d4b; border-radius: 3px; padding: 3px; }
QTableWidget, QTableView, QListWidget, QTreeWidget { background: #101117; alternate-background-color: #16171f; gridline-color: #262834; selection-background-color: #4b3d10; }
QHeaderView::section { background: #1d1f27; border: 1px solid #2a2c36; padding: 3px; }
QSlider::groove:vertical { background: #0c0d11; width: 10px; border-radius: 4px; }
QSlider::handle:vertical { background: #d9d9e3; height: 18px; margin: 0 -9px; border-radius: 3px; }
QSlider::sub-page:vertical { background: #0c0d11; }
QSlider::add-page:vertical { background: #c08a10; border-radius: 4px; }
QSlider::groove:horizontal { background: #0c0d11; height: 8px; border-radius: 4px; }
QSlider::handle:horizontal { background: #d9d9e3; width: 14px; margin: -5px 0; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #c08a10; border-radius: 4px; }
QGroupBox { border: 1px solid #2a2c36; border-radius: 4px; margin-top: 10px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #ffcc33; }
QStatusBar { background: #0e0f13; }
QToolBar { background: #1a1b22; border-bottom: 1px solid #2a2c36; spacing: 4px; }
QScrollArea { border: none; }
QLabel#title { color: #ffcc33; font-weight: bold; }
QLineEdit#cmd { font-family: monospace; font-size: 11pt; background: #050608; color: #8fff8f; }
"""
