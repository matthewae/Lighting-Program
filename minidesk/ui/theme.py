ACCENT = "#f5b331"

DARK_QSS = """
* { font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; }
QWidget { background: #121318; color: #dfe1e8; font-size: 10pt; }
QMainWindow::separator, QSplitter::handle { background: #1d1f27; }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }
QSplitter::handle:hover { background: #f5b331; }

QMenuBar { background: #0e0f13; border-bottom: 1px solid #22242e; }
QMenuBar::item { padding: 6px 12px; background: transparent; }
QMenuBar::item:selected { background: #262936; border-radius: 4px; }
QMenu { background: #1a1c24; border: 1px solid #2c2f3c; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background: #f5b331; color: #121318; }

QToolBar { background: #16171d; border: none; border-bottom: 1px solid #22242e; spacing: 6px; padding: 4px; }
QToolBar QToolButton { padding: 6px 12px; border-radius: 6px; }
QToolBar QToolButton:hover { background: #262936; }
QToolBar QToolButton:checked { background: #b02a2a; color: white; }

QTabWidget::pane { border: none; border-top: 1px solid #22242e; }
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: #9aa0b3; padding: 8px 14px; margin: 4px 2px 0 2px;
               border-radius: 8px; }
QTabBar::tab:hover { background: #1f212b; color: #e6e8ef; }
QTabBar::tab:selected { background: #262936; color: #f5b331; font-weight: 600; }

QPushButton, QToolButton { background: #232631; border: 1px solid #2f3342; border-radius: 6px;
                           padding: 6px 10px; color: #e3e5ec; }
QPushButton:hover, QToolButton:hover { background: #2c3040; border-color: #3d4256; }
QPushButton:pressed, QToolButton:pressed { background: #f5b331; color: #121318; }
QPushButton:checked, QToolButton:checked { background: #3a3220; border-color: #f5b331; color: #f5d27a; }
QPushButton:disabled, QToolButton:disabled { color: #5a5e6c; background: #1a1c23; border-color: #23252e; }
QPushButton#go { background: #1d6b38; border-color: #27904c; font-weight: 600; }
QPushButton#go:hover { background: #23804a; }
QPushButton#go:pressed { background: #46d07a; color: #0b1a10; }
QPushButton#flash { background: #5c2a1d; border-color: #7c3a28; }
QPushButton#flash:pressed { background: #ff7a45; color: #111; }
QPushButton#danger { background: #6a1f24; border-color: #8a2c33; }
QPushButton#danger:hover { background: #81262d; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #0d0e12; border: 1px solid #2c2f3c;
    border-radius: 6px; padding: 4px 8px; min-height: 22px; selection-background-color: #f5b331;
    selection-color: #121318; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #f5b331; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #1a1c24; border: 1px solid #2c2f3c; selection-background-color: #f5b331;
    selection-color: #121318; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #3d4256;
    background: #0d0e12; }
QCheckBox::indicator:checked { background: #f5b331; border-color: #f5b331; }

QTableWidget, QTableView, QListWidget, QTreeWidget { background: #0f1015; alternate-background-color: #14151c;
    border: 1px solid #22242e; border-radius: 6px; gridline-color: #1f212b;
    selection-background-color: #4a3c14; selection-color: #fff; }
QHeaderView::section { background: #181a22; color: #aab0c2; border: none; border-right: 1px solid #22242e;
    border-bottom: 1px solid #22242e; padding: 6px; font-weight: 600; }

QSlider::groove:vertical { background: #0b0c10; width: 12px; border-radius: 6px; border: 1px solid #22242e; }
QSlider::handle:vertical { background: #eceef4; height: 20px; margin: 0 -8px; border-radius: 5px; }
QSlider::sub-page:vertical { background: #0b0c10; border-radius: 6px; }
QSlider::add-page:vertical { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5b331, stop:1 #b9780f);
    border-radius: 6px; }
QSlider::groove:horizontal { background: #0b0c10; height: 8px; border-radius: 4px; border: 1px solid #22242e; }
QSlider::handle:horizontal { background: #eceef4; width: 16px; margin: -6px 0; border-radius: 5px; }
QSlider::sub-page:horizontal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b9780f, stop:1 #f5b331);
    border-radius: 4px; }

QGroupBox { border: 1px solid #23252f; border-radius: 10px; margin-top: 14px; padding: 10px 8px 8px 8px;
    background: #15161c; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #f5b331; font-weight: 600; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle { background: #2f3342; border-radius: 4px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background: #4a4f63; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QListWidget#nav { background: #0e0f13; border: none; border-right: 1px solid #22242e; border-radius: 0;
    padding-top: 6px; outline: none; }
QListWidget#nav::item { color: #9aa0b3; border-radius: 10px; margin: 3px 4px; padding-top: 6px; font-size: 8.5pt; }
QListWidget#nav::item:hover { background: #1c1e27; color: #e6e8ef; }
QListWidget#nav::item:selected { background: #2a2618; color: #f5b331; border: 1px solid #5a4a1c; }
QWidget#overlay { background: rgba(14, 15, 19, 200); border: 1px solid #2c2f3c; border-radius: 10px; }
QWidget#overlay QToolButton { background: transparent; border: none; padding: 4px 8px; border-radius: 6px; }
QWidget#overlay QToolButton:hover { background: #262936; }
QWidget#overlay QToolButton:checked { background: #3a3220; color: #f5d27a; }
QProgressBar#stepbar { background: #0b0c10; border: none; border-radius: 2px; }
QProgressBar#stepbar::chunk { background: #46d07a; border-radius: 2px; }
QStatusBar { background: #0e0f13; border-top: 1px solid #22242e; color: #9aa0b3; }
QStatusBar QLabel { padding: 0 6px; }
QToolTip { background: #1f212b; color: #e6e8ef; border: 1px solid #f5b331; padding: 6px; border-radius: 4px; }
QLabel#title { color: #f5b331; font-weight: 700; font-size: 11pt; }
QLineEdit#cmd { font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11pt; background: #07080a;
    color: #8fff9f; border-radius: 8px; padding: 6px 10px; }
"""
