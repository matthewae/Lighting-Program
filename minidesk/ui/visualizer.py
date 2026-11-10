"""3D stage visualizer (QPainter, additive light beams) + top view editor."""
from __future__ import annotations

import math
import time
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPen,
                           QPolygonF, QRadialGradient)
from PySide6.QtWidgets import QWidget

from ..model import Show
from ..vis_state import VisState, compute

Vec = tuple[float, float, float]


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec) -> Vec:
    n = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


class StageView(QWidget):
    fixtureClicked = Signal(int, bool)       # fid, additive
    fixtureMoved = Signal(int)

    def __init__(self, show: Show, dmx_source: Callable[[], dict[int, bytes]], parent=None):
        super().__init__(parent)
        self.show = show
        self.dmx_source = dmx_source
        self.selection: set[int] = set()
        self.mode = "3d"                 # 3d | top
        self.yaw, self.pitch, self.dist = 0.0, 0.32, 15.0
        self.haze = 0.35
        self.show_labels = True
        self.fog_level = 0.0
        self._drag: Optional[tuple] = None
        self._screen_pos: dict[int, QPointF] = {}
        self._states: dict[int, VisState] = {}
        self.setMinimumSize(480, 320)
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

    def set_show(self, show: Show) -> None:
        self.show = show
        self.selection.clear()
        self.update()

    # ------------------------------------------------------------ projection
    @property
    def target(self) -> Vec:
        return (0.0, self.show.stage_depth / 2, 2.0)

    def to_cam(self, p: Vec) -> Vec:
        x, y, z = _sub(p, self.target)
        c, s = math.cos(-self.yaw), math.sin(-self.yaw)
        x, y = x * c - y * s, x * s + y * c
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        y, z = y * cp - z * sp, z * cp + y * sp
        return (x, y + self.dist, z)

    def project_cam(self, c: Vec) -> Optional[QPointF]:
        if c[1] < 0.2:
            return None
        f = min(self.width(), self.height() * 1.6) * 0.9
        return QPointF(self.width() / 2 + f * c[0] / c[1], self.height() / 2 - f * c[2] / c[1])

    def project(self, p: Vec) -> Optional[QPointF]:
        return self.project_cam(self.to_cam(p))

    def top_map(self, x: float, y: float) -> QPointF:
        W, D = self.show.stage_width + 2, self.show.stage_depth + 2
        sc = min(self.width() / W, self.height() / D) * 0.92
        return QPointF(self.width() / 2 + x * sc, self.height() / 2 + (self.show.stage_depth / 2 - y) * sc)

    def top_unmap(self, p: QPointF) -> tuple[float, float]:
        W, D = self.show.stage_width + 2, self.show.stage_depth + 2
        sc = min(self.width() / W, self.height() / D) * 0.92
        return (p.x() - self.width() / 2) / sc, self.show.stage_depth / 2 - (p.y() - self.height() / 2) / sc

    # ---------------------------------------------------------------- states
    def _compute_states(self) -> None:
        unis = self.dmx_source() or {}
        now = time.time()
        fog = 0.0
        self._states.clear()
        for fx in self.show.fixtures:
            ft = self.show.types.get(fx.type_key)
            if not ft:
                continue
            dmx = unis.get(fx.universe, b"")
            st = compute(fx, ft, dmx, now)
            self._states[fx.fid] = st
            fog = max(fog, st.fog)
        # fog builds up slowly and decays slowly
        target = max(self.haze, min(1.0, self.haze + fog * 0.6))
        self.fog_level += (target - self.fog_level) * (0.08 if target > self.fog_level else 0.01)

    def _hit(self, p: Vec, d: Vec) -> float:
        D = self.show.stage_depth
        best = 14.0
        if d[2] < -1e-3:
            best = min(best, -p[2] / d[2])
        if d[2] > 1e-3:
            best = min(best, (self.show.stage_height + 2.5 - p[2]) / d[2])
        if d[1] > 1e-3:
            best = min(best, (D + 0.5 - p[1]) / d[1])
        return max(0.3, best)

    # ------------------------------------------------------------------ paint
    def paintEvent(self, ev):
        self._compute_states()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(8, 9, 14))
        if self.mode == "top":
            self._paint_top(p)
        else:
            self._paint_3d(p)
        p.end()

    def _line(self, p: QPainter, a: Vec, b: Vec) -> None:
        pa, pb = self.project(a), self.project(b)
        if pa and pb:
            p.drawLine(pa, pb)

    def _poly(self, pts: list[Vec]) -> Optional[QPolygonF]:
        out = []
        for v in pts:
            q = self.project(v)
            if q is None:
                return None
            out.append(q)
        return QPolygonF(out)

    def _paint_3d(self, p: QPainter) -> None:
        W, D, H = self.show.stage_width, self.show.stage_depth, self.show.stage_height
        hw = W / 2 + 1
        # floor + back wall
        floor = self._poly([(-hw, 0, 0), (hw, 0, 0), (hw, D + 0.5, 0), (-hw, D + 0.5, 0)])
        wall = self._poly([(-hw, D + 0.5, 0), (hw, D + 0.5, 0), (hw, D + 0.5, H + 2.5), (-hw, D + 0.5, H + 2.5)])
        if wall:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(16, 17, 24))
            p.drawPolygon(wall)
        if floor:
            p.setBrush(QColor(22, 22, 28))
            p.drawPolygon(floor)
        p.setPen(QPen(QColor(40, 42, 52), 1))
        for i in range(int(-hw), int(hw) + 1):
            self._line(p, (i, 0, 0), (i, D + 0.5, 0))
        for j in range(0, int(D) + 1):
            self._line(p, (-hw, j, 0), (hw, j, 0))
        # stage edge
        p.setPen(QPen(QColor(90, 90, 110), 2))
        self._line(p, (-W / 2, 0, 0), (W / 2, 0, 0))
        # trusses: one line per distinct (y, z) hanging height
        p.setPen(QPen(QColor(85, 88, 100), 3))
        levels = {}
        for fx in self.show.fixtures:
            if fx.mount == "hang" and abs(fx.x) <= W / 2 + 0.01:
                key = (round(fx.y, 1), round(fx.z, 1))
                lo, hi = levels.get(key, (fx.x, fx.x))
                levels[key] = (min(lo, fx.x), max(hi, fx.x))
        for (y, z), (lo, hi) in levels.items():
            self._line(p, (lo - 0.5, y, z + 0.2), (hi + 0.5, y, z + 0.2))
        for fx in self.show.fixtures:   # towers
            if abs(fx.x) > W / 2 + 0.01:
                self._line(p, (fx.x, fx.y, 0), (fx.x, fx.y, fx.z + 0.6))

        # ---- beams (additive) ----
        cam_pos_c = (0.0, 0.0, 0.0)
        beams = []
        for fx in self.show.fixtures:
            st = self._states.get(fx.fid)
            if not st or st.intensity <= 0.01 or not st.has_beam:
                continue
            pos = (fx.x, fx.y, fx.z)
            L = self._hit(pos, st.direction)
            end = _add(pos, _mul(st.direction, L))
            depth = self.to_cam(end)[1]
            beams.append((depth, fx, st, pos, end, L))
        beams.sort(key=lambda b: -b[0])
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for depth, fx, st, pos, end, L in beams:
            r = L * math.tan(math.radians(st.beam_angle / 2))
            a_c, e_c = self.to_cam(pos), self.to_cam(end)
            axis = _norm(_sub(e_c, a_c))
            view = _norm(_sub(e_c, cam_pos_c))
            perp = _norm(_cross(axis, view))
            r0 = 0.06
            pts = [_add(a_c, _mul(perp, r0)), _add(e_c, _mul(perp, r)),
                   _add(e_c, _mul(perp, -r)), _add(a_c, _mul(perp, -r0))]
            qpts = [self.project_cam(v) for v in pts]
            if any(q is None for q in qpts):
                continue
            col = QColor(*st.colour)
            k = st.intensity * max(0.3, min(1.0, (14.0 / max(st.beam_angle, 1.0)) ** 0.6))
            beam_alpha = int(min(255, 170 * self.fog_level * k + 18 * k))
            pa, pe = self.project_cam(a_c), self.project_cam(e_c)
            grad = QLinearGradient(pa, pe)
            c0 = QColor(col)
            c0.setAlpha(beam_alpha)
            c1 = QColor(col)
            c1.setAlpha(int(beam_alpha * 0.25))
            grad.setColorAt(0, c0)
            grad.setColorAt(1, c1)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawPolygon(QPolygonF(qpts))
            # light pool where the beam hits a surface
            self._draw_pool(p, end, st, r, k)
            # lens glow
            if pa:
                g = QRadialGradient(pa, 10 + 8 * k)
                c2 = QColor(col)
                c2.setAlpha(int(255 * k))
                g.setColorAt(0, c2)
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(QBrush(g))
                p.drawEllipse(pa, 10 + 8 * k, 10 + 8 * k)
        # fog haze glow
        if self.fog_level > self.haze + 0.02:
            p.setBrush(QColor(120, 120, 140, int(60 * (self.fog_level - self.haze))))
            p.drawRect(self.rect())
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # ---- fixture bodies ----
        self._screen_pos.clear()
        font = QFont()
        font.setPointSize(7)
        p.setFont(font)
        for fx in sorted(self.show.fixtures, key=lambda f: -self.to_cam((f.x, f.y, f.z))[1]):
            q = self.project((fx.x, fx.y, fx.z))
            if q is None:
                continue
            self._screen_pos[fx.fid] = q
            st = self._states.get(fx.fid)
            sel = fx.fid in self.selection
            body = QColor(55, 58, 68) if fx.patched else QColor(60, 30, 30)
            p.setPen(QPen(QColor(255, 200, 0) if sel else QColor(20, 20, 24), 2 if sel else 1))
            p.setBrush(body)
            rad = 6 if self.show.types[fx.type_key].kind != "moving" else 7
            p.drawEllipse(q, rad, rad)
            if st and st.intensity > 0.01:
                c = QColor(*st.colour)
                c.setAlpha(int(80 + 175 * st.intensity))
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawEllipse(q, rad - 2.5, rad - 2.5)
            if self.show_labels:
                p.setPen(QColor(170, 170, 185) if not sel else QColor(255, 210, 60))
                p.drawText(q + QPointF(-10, -10), str(fx.fid))
        self._hud(p, "3D  |  drag: orbit   wheel: zoom   click: select   Tab: top view")

    def _draw_pool(self, p: QPainter, end: Vec, st: VisState, r: float, k: float) -> None:
        if end[2] > 0.05:       # wall hit: project a flat circle in the x/z plane
            pts = [(end[0] + r * math.cos(a), end[1] - 0.01, end[2] + r * math.sin(a))
                   for a in [i * math.pi / 8 for i in range(16)]]
        else:
            pts = [(end[0] + r * math.cos(a), end[1] + r * math.sin(a), 0.01)
                   for a in [i * math.pi / 8 for i in range(16)]]
        poly = self._poly(pts)
        c = self.project(end)
        if not poly or not c:
            return
        br = poly.boundingRect()
        g = QRadialGradient(c, max(br.width(), br.height()) / 2 + 1)
        col = QColor(*st.colour)
        col.setAlpha(int(120 * k))
        g.setColorAt(0, col)
        col2 = QColor(*st.colour)
        col2.setAlpha(int(30 * k))
        g.setColorAt(0.7, col2)
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g))
        p.drawPolygon(poly)

    def _paint_top(self, p: QPainter) -> None:
        W, D = self.show.stage_width, self.show.stage_depth
        a, b = self.top_map(-W / 2, D), self.top_map(W / 2, 0)
        p.setPen(QPen(QColor(70, 70, 85), 1))
        p.setBrush(QColor(22, 22, 28))
        p.drawRect(QRectF(a, b))
        p.setPen(QPen(QColor(38, 40, 50), 1))
        for i in range(int(-W / 2), int(W / 2) + 1):
            p.drawLine(self.top_map(i, 0), self.top_map(i, D))
        for j in range(0, int(D) + 1):
            p.drawLine(self.top_map(-W / 2, j), self.top_map(W / 2, j))
        p.setPen(QColor(120, 120, 140))
        p.drawText(self.top_map(-0.8, -0.4), "AUDIENCE / DOWNSTAGE")
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for fx in self.show.fixtures:
            st = self._states.get(fx.fid)
            if not st or st.intensity <= 0.01 or not st.has_beam:
                continue
            pos = (fx.x, fx.y, fx.z)
            L = self._hit(pos, st.direction)
            end = _add(pos, _mul(st.direction, L))
            r = max(0.15, L * math.tan(math.radians(st.beam_angle / 2)))
            c = self.top_map(end[0], end[1])
            sc = self.top_map(r, 0).x() - self.top_map(0, 0).x()
            col = QColor(*st.colour)
            col.setAlpha(int(70 * st.intensity))
            g = QRadialGradient(c, sc)
            g.setColorAt(0, col)
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(c, sc, sc)
            lc = QColor(*st.colour)
            lc.setAlpha(int(90 * st.intensity))
            p.setPen(QPen(lc, 1))
            p.drawLine(self.top_map(fx.x, fx.y), c)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        self._screen_pos.clear()
        font = QFont()
        font.setPointSize(7)
        p.setFont(font)
        for fx in self.show.fixtures:
            q = self.top_map(fx.x, fx.y)
            self._screen_pos[fx.fid] = q
            st = self._states.get(fx.fid)
            sel = fx.fid in self.selection
            p.setPen(QPen(QColor(255, 200, 0) if sel else QColor(90, 90, 100), 2 if sel else 1))
            col = QColor(50, 52, 60)
            if st and st.intensity > 0.01:
                col = QColor(*st.colour)
                col.setAlpha(int(90 + 165 * st.intensity))
            p.setBrush(col)
            kind = self.show.types[fx.type_key].kind
            if kind == "moving":
                p.drawEllipse(q, 8, 8)
            else:
                p.drawRoundedRect(QRectF(q.x() - 7, q.y() - 7, 14, 14), 3, 3)
            p.setPen(QColor(200, 200, 210) if not sel else QColor(255, 210, 60))
            p.drawText(q + QPointF(-8, -10), f"{fx.fid}")
            if self.show_labels:
                p.setPen(QColor(110, 110, 125))
                p.drawText(q + QPointF(-14, 19), f"{fx.name[:10]} z{fx.z:.1f}")
        self._hud(p, "TOP / EDIT  |  click: select   drag: move fixture   Tab: 3D view")

    def _hud(self, p: QPainter, text: str) -> None:
        p.setPen(QColor(110, 110, 130))
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        p.drawText(8, self.height() - 8, text)

    # ------------------------------------------------------------------ mouse
    def _pick(self, pos: QPointF) -> Optional[int]:
        best, bd = None, 14.0
        for fid, q in self._screen_pos.items():
            d = math.hypot(q.x() - pos.x(), q.y() - pos.y())
            if d < bd:
                best, bd = fid, d
        return best

    def mousePressEvent(self, e):
        pos = e.position()
        fid = self._pick(pos)
        add = bool(e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
        if fid is not None and e.button() == Qt.LeftButton:
            self.fixtureClicked.emit(fid, add)
            if self.mode == "top":
                self._drag = ("move", fid)
                return
        self._drag = ("orbit", pos, self.yaw, self.pitch)

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        pos = e.position()
        if self._drag[0] == "move":
            fx = self.show.fixture(self._drag[1])
            if fx:
                x, y = self.top_unmap(pos)
                fx.x, fx.y = round(x * 4) / 4, round(y * 4) / 4
                self.fixtureMoved.emit(fx.fid)
        elif self.mode == "3d":
            _, start, yaw, pitch = self._drag
            self.yaw = yaw + (pos.x() - start.x()) * 0.008
            self.pitch = max(-0.1, min(1.45, pitch + (pos.y() - start.y()) * 0.006))
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None

    def wheelEvent(self, e):
        self.dist = max(4.0, min(40.0, self.dist * (0.9 if e.angleDelta().y() > 0 else 1.1)))
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Tab:
            self.toggle_mode()
        else:
            super().keyPressEvent(e)

    def toggle_mode(self) -> None:
        self.mode = "top" if self.mode == "3d" else "3d"
        self.update()

    def reset_camera(self) -> None:
        self.yaw, self.pitch, self.dist = 0.0, 0.32, 15.0
        self.update()

    def focusNextPrevChild(self, nxt):   # keep Tab for the view toggle
        return False
