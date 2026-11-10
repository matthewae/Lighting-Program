"""Start-up splash screen (drawn in code, no image files needed)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF,
                           QRadialGradient)
from PySide6.QtWidgets import QSplashScreen

VERSION = "2.0"


def splash_pixmap(w: int = 640, h: int = 360) -> QPixmap:
    pm = QPixmap(w, h)
    pm.fill(QColor(8, 9, 14))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    bg = QLinearGradient(0, 0, 0, h)
    bg.setColorAt(0, QColor(18, 20, 32))
    bg.setColorAt(1, QColor(6, 6, 10))
    p.fillRect(pm.rect(), bg)
    # beams
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    cols = [QColor(255, 60, 60), QColor(255, 200, 40), QColor(60, 220, 120), QColor(60, 140, 255),
            QColor(200, 80, 255)]
    for i, c in enumerate(cols):
        x = w * (0.18 + i * 0.16)
        ang = math.radians(-18 + i * 9)
        tip = QPointF(x, 18)
        ex, ey = x + math.sin(ang) * h, h + 10
        poly = QPolygonF([tip, QPointF(ex - 55, ey), QPointF(ex + 55, ey)])
        g = QLinearGradient(tip, QPointF(ex, ey))
        c0 = QColor(c)
        c0.setAlpha(120)
        c1 = QColor(c)
        c1.setAlpha(10)
        g.setColorAt(0, c0)
        g.setColorAt(1, c1)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPolygon(poly)
        rg = QRadialGradient(tip, 14)
        rg.setColorAt(0, QColor(255, 255, 255, 220))
        rg.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(rg)
        p.drawEllipse(tip, 14, 14)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    p.setPen(QPen(QColor(90, 94, 110), 4))
    p.drawLine(int(w * 0.1), 14, int(w * 0.9), 14)
    # title
    f = QFont()
    f.setPointSize(38)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(0, h * 0.36, w, 60), Qt.AlignHCenter, "MiniDesk")
    f2 = QFont()
    f2.setPointSize(12)
    p.setFont(f2)
    p.setPen(QColor(255, 204, 51))
    p.drawText(QRectF(0, h * 0.36 + 62, w, 24), Qt.AlignHCenter,
               "Lighting programmer & 3D visualizer")
    p.setPen(QColor(170, 175, 195))
    p.drawText(QRectF(0, h * 0.36 + 88, w, 24), Qt.AlignHCenter,
               f"for CODE MINI 1000T / MINI 1000T PRO   ·   v{VERSION}")
    p.end()
    return pm


class Splash(QSplashScreen):
    def __init__(self):
        super().__init__(splash_pixmap())
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    def step(self, text: str) -> None:
        self.showMessage(text, Qt.AlignBottom | Qt.AlignHCenter, QColor(200, 205, 220))
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
