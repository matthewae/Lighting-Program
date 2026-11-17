"""Run with:  python -m minidesk [show.mdshow | console.SHO]"""
import sys


def main() -> int:
    import os
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    # interface size (Preferences → Interface size); an explicit QT_SCALE_FACTOR wins
    scale = str(QSettings("MiniDesk", "MiniDesk").value("ui_scale", "0.9"))
    if "QT_SCALE_FACTOR" not in os.environ and scale not in ("", "1", "1.0"):
        os.environ["QT_SCALE_FACTOR"] = scale
    app = QApplication(sys.argv)
    app.setApplicationName("MiniDesk")
    app.setOrganizationName("MiniDesk")
    show_splash = QSettings("MiniDesk", "MiniDesk").value("splash", True, type=bool)
    splash = None
    if show_splash:
        from .ui.splash import Splash
        splash = Splash()
        splash.show()
        splash.step("Loading engine…")
    from .ui.main_window import MainWindow
    if splash:
        splash.step("Building user interface…")
    path = sys.argv[1] if len(sys.argv) > 1 else None
    win = MainWindow(path, welcome=path is None, splash=splash)
    win.show()
    if splash:
        splash.finish(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
