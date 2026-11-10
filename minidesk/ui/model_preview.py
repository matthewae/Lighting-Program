"""Small rotating 3D preview of a fixture model."""
from __future__ import annotations

import time

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..meshes import get_mesh
from .mesh_render import Camera, mesh_faces, part_transforms


class ModelPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.model, self.kind, self.scale = "", "par", 1.0
        self.info = ""
        self.t0 = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(40)

    def set_model(self, model: str, kind: str, scale: float = 1.0) -> None:
        self.model, self.kind, self.scale = model, kind, scale
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(14, 15, 20))
        mesh = get_mesh(self.model, self.kind, self.scale, 1)
        if mesh is None:
            p.end()
            return
        lo, hi = mesh.bounds()
        size = float(max(hi - lo)) or 0.3
        centre = (lo + hi) / 2
        t = time.time() - self.t0
        cam = Camera(centre, 0.6 + t * 0.6, 0.35, size * 2.6, self.width(), self.height())
        tilt = 35 * np.sin(t * 0.8)
        tr = part_transforms(mesh, (0, 0, 0), 25 * np.sin(t * 0.5), tilt, 0, True, self.kind == "fog")
        faces = []
        mesh_faces(cam, mesh, tr, QColor(255, 230, 160), None, faces)
        faces.sort(key=lambda f: -f[0])
        for _d, poly, col, _o in faces:
            p.setPen(QPen(QColor(10, 10, 12, 140), 0.5))
            p.setBrush(col)
            p.drawPolygon(poly)
        p.setPen(QColor(150, 150, 165))
        p.drawText(self.rect().adjusted(6, 4, -6, -4), Qt.AlignBottom | Qt.AlignLeft,
                   f"{mesh.face_count} polygons · {size:.2f} m")
        p.end()
