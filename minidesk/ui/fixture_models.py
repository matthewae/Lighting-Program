"""2D icons of the fixture models (used in tiles, top view, dialogs)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QIcon

from ..model import MODEL_KINDS

BODY = QColor(70, 74, 86)
EDGE = QColor(20, 20, 24)


def _lens(p: QPainter, c: QPointF, r: float, colour: QColor | None) -> None:
    p.setPen(QPen(EDGE, 1))
    p.setBrush(colour if colour is not None else QColor(30, 32, 38))
    p.drawEllipse(c, r, r)


def draw_icon(p: QPainter, rect: QRectF, kind: str, colour: QColor | None = None) -> None:
    """Draw a small front/side view of the fixture model inside ``rect``."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    s = min(rect.width(), rect.height())
    cx, cy = rect.center().x(), rect.center().y()
    p.setPen(QPen(EDGE, 1))
    p.setBrush(BODY)
    if kind in ("beam", "spot", "wash"):
        # base
        p.drawRoundedRect(QRectF(cx - s * 0.32, rect.top() + s * 0.04, s * 0.64, s * 0.16), 2, 2)
        # yoke
        p.drawRect(QRectF(cx - s * 0.30, rect.top() + s * 0.18, s * 0.08, s * 0.40))
        p.drawRect(QRectF(cx + s * 0.22, rect.top() + s * 0.18, s * 0.08, s * 0.40))
        # head
        hr = {"beam": 0.18, "spot": 0.21, "wash": 0.24}[kind]
        head = QRectF(cx - s * hr, cy - s * 0.02, s * hr * 2, s * 0.42)
        p.drawRoundedRect(head, s * 0.06, s * 0.06)
        lr = s * (0.08 if kind == "beam" else 0.12 if kind == "spot" else 0.15)
        _lens(p, QPointF(cx, head.bottom() - s * 0.04), lr, colour)
    elif kind == "par":
        p.drawRect(QRectF(cx - s * 0.04, rect.top() + s * 0.04, s * 0.08, s * 0.14))
        p.drawRoundedRect(QRectF(cx - s * 0.30, rect.top() + s * 0.18, s * 0.60, s * 0.58), 5, 5)
        _lens(p, QPointF(cx, rect.top() + s * 0.47), s * 0.22, colour)
    elif kind == "fresnel":
        p.drawRect(QRectF(cx - s * 0.04, rect.top() + s * 0.04, s * 0.08, s * 0.12))
        p.drawRect(QRectF(cx - s * 0.34, rect.top() + s * 0.16, s * 0.68, s * 0.64))
        _lens(p, QPointF(cx, rect.top() + s * 0.48), s * 0.24, colour)
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.setBrush(Qt.NoBrush)
        for k in (0.16, 0.10):
            p.drawEllipse(QPointF(cx, rect.top() + s * 0.48), s * k, s * k)
    elif kind == "strobe":
        p.drawRoundedRect(QRectF(rect.left() + s * 0.06, cy - s * 0.18, s * 0.88, s * 0.36), 3, 3)
        p.setBrush(colour if colour is not None else QColor(60, 62, 70))
        p.drawRect(QRectF(rect.left() + s * 0.14, cy - s * 0.10, s * 0.72, s * 0.20))
    elif kind == "ledbar":
        p.drawRoundedRect(QRectF(rect.left() + s * 0.02, cy - s * 0.10, s * 0.96, s * 0.20), 2, 2)
        for i in range(6):
            _lens(p, QPointF(rect.left() + s * (0.12 + i * 0.152), cy), s * 0.055, colour)
    elif kind == "blinder":
        p.drawRoundedRect(QRectF(rect.left() + s * 0.08, cy - s * 0.24, s * 0.84, s * 0.48), 3, 3)
        for dx in (-0.2, 0.2):
            _lens(p, QPointF(cx + s * dx, cy), s * 0.15, colour)
    elif kind == "fog":
        p.drawRoundedRect(QRectF(cx - s * 0.36, cy - s * 0.08, s * 0.66, s * 0.36), 3, 3)
        p.drawRect(QRectF(cx + s * 0.30, cy + s * 0.02, s * 0.12, s * 0.10))
        if colour is not None:
            p.setPen(Qt.NoPen)
            c = QColor(colour)
            c.setAlpha(150)
            p.setBrush(c)
            p.drawEllipse(QPointF(cx + s * 0.40, cy - s * 0.14), s * 0.10, s * 0.08)
            p.drawEllipse(QPointF(cx + s * 0.30, cy - s * 0.28), s * 0.08, s * 0.06)
    else:
        p.drawRoundedRect(QRectF(cx - s * 0.3, cy - s * 0.25, s * 0.6, s * 0.5), 3, 3)
        _lens(p, QPointF(cx, cy), s * 0.15, colour)
    p.restore()


def model_icon(kind: str, size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_icon(p, QRectF(1, 1, size - 2, size - 2), kind, QColor(255, 210, 120))
    p.end()
    return QIcon(pm)


def model_items() -> list[tuple[str, str]]:
    return list(MODEL_KINDS.items())
