"""3D stage visualizer with fixture models + top/front layout editors."""
from __future__ import annotations

import math
import time
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QPolygonF,
                           QRadialGradient)
from PySide6.QtWidgets import QWidget

from ..model import MOVING_KINDS, Show
from ..vis_state import VisState, compute
from .fixture_models import draw_icon

Vec = tuple[float, float, float]
LIGHT = (0.35, -0.55, 0.76)


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec) -> Vec:
    n = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


class StageView(QWidget):
    fixtureClicked = Signal(int, bool)       # fid (-1 = clear), additive
    fixtureMoved = Signal(int)
    layoutEdited = Signal()

    def __init__(self, show: Show, dmx_source: Callable[[], dict[int, bytes]], parent=None):
        super().__init__(parent)
        self.show = show
        self.dmx_source = dmx_source
        self.selection: set[int] = set()
        self.mode = "3d"                 # 3d | top | front
        self.yaw, self.pitch, self.dist = 0.0, 0.30, 16.0
        self.haze = 0.35
        self.show_labels = True
        self.show_models = True
        self.snap = 0.25
        self.fog_level = 0.0
        self._drag: Optional[tuple] = None
        self._screen_pos: dict[int, QPointF] = {}
        self._states: dict[int, VisState] = {}
        self._faces: list = []
        self.setMinimumSize(480, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
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
        return (0.0, self.show.stage_depth / 2, 2.2)

    def rot_cam(self, v: Vec) -> Vec:
        x, y, z = v
        c, s = math.cos(-self.yaw), math.sin(-self.yaw)
        x, y = x * c - y * s, x * s + y * c
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        return (x, y * cp - z * sp, z * cp + y * sp)

    def to_cam(self, p: Vec) -> Vec:
        x, y, z = self.rot_cam(_sub(p, self.target))
        return (x, y + self.dist, z)

    def project_cam(self, c: Vec) -> Optional[QPointF]:
        if c[1] < 0.2:
            return None
        f = min(self.width(), self.height() * 1.6) * 0.9
        return QPointF(self.width() / 2 + f * c[0] / c[1], self.height() / 2 - f * c[2] / c[1])

    def project(self, p: Vec) -> Optional[QPointF]:
        return self.project_cam(self.to_cam(p))

    def _scale2d(self) -> float:
        W = self.show.stage_width + 3
        if self.mode == "top":
            return min(self.width() / W, self.height() / (self.show.stage_depth + 2.5)) * 0.92
        return min(self.width() / W, self.height() / (self.show.stage_height + 2.5)) * 0.92

    def map2d(self, a: float, b: float) -> QPointF:
        """top: (x, y)  front: (x, z)"""
        sc = self._scale2d()
        if self.mode == "top":
            return QPointF(self.width() / 2 + a * sc, self.height() / 2 + (self.show.stage_depth / 2 - b) * sc)
        return QPointF(self.width() / 2 + a * sc, self.height() - 40 - b * sc)

    def unmap2d(self, p: QPointF) -> tuple[float, float]:
        sc = self._scale2d()
        if self.mode == "top":
            return (p.x() - self.width() / 2) / sc, self.show.stage_depth / 2 - (p.y() - self.height() / 2) / sc
        return (p.x() - self.width() / 2) / sc, (self.height() - 40 - p.y()) / sc

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
            st = compute(fx, ft, unis.get(fx.universe, b""), now)
            self._states[fx.fid] = st
            fog = max(fog, st.fog)
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

    @staticmethod
    def _lens_offset(kind: str) -> float:
        return {"beam": 0.22, "spot": 0.24, "wash": 0.24, "par": 0.16, "fresnel": 0.18,
                "strobe": 0.07, "ledbar": 0.05, "blinder": 0.09}.get(kind, 0.12)

    # ------------------------------------------------------------------ paint
    def paintEvent(self, ev):
        self._compute_states()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(8, 9, 14))
        if self.mode in ("top", "front"):
            self._paint_2d(p)
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

    # --------------------------------------------------------------- models
    def _face(self, pts: list[Vec], normal: Vec, base: QColor, emissive: Optional[QColor] = None,
              outline: Optional[QColor] = None) -> None:
        cam = [self.to_cam(v) for v in pts]
        nc = self.rot_cam(normal)
        n = len(cam)
        centre = (sum(c[0] for c in cam) / n, sum(c[1] for c in cam) / n, sum(c[2] for c in cam) / n)
        if _dot(nc, centre) >= 0:
            return          # back face
        q = [self.project_cam(c) for c in cam]
        if any(x is None for x in q):
            return
        if emissive is not None:
            col = emissive
        else:
            k = 0.38 + 0.62 * max(0.0, _dot(_norm(normal), LIGHT))
            col = QColor(int(base.red() * k), int(base.green() * k), int(base.blue() * k))
        self._faces.append((centre[1], QPolygonF(q), col, outline))

    def _box(self, c: Vec, axes: tuple[Vec, Vec, Vec], half: Vec, col: QColor,
             front_emissive: Optional[QColor] = None, outline=None) -> None:
        u, v, w = axes
        hu, hv, hw = _mul(u, half[0]), _mul(v, half[1]), _mul(w, half[2])

        def corner(a, b, e):
            return _add(_add(_add(c, _mul(hu, a)), _mul(hv, b)), _mul(hw, e))
        faces = [
            ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1), u, front_emissive),
            ((-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1), _mul(u, -1), None),
            ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1), v, None),
            ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1), _mul(v, -1), None),
            ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1), w, None),
            ((-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1), _mul(w, -1), None),
        ]
        for a, b, e, f, n, em in faces:
            self._face([corner(*a), corner(*b), corner(*e), corner(*f)], n, col, em, outline)

    def _cylinder(self, p0: Vec, p1: Vec, r: float, col: QColor, cap: Optional[QColor] = None,
                  outline=None, seg: int = 10) -> None:
        d = _norm(_sub(p1, p0))
        a = _norm(_cross(d, (0, 0, 1))) if abs(d[2]) < 0.95 else (1.0, 0.0, 0.0)
        b = _cross(d, a)
        ring0, ring1 = [], []
        for i in range(seg):
            t = 2 * math.pi * i / seg
            off = _add(_mul(a, r * math.cos(t)), _mul(b, r * math.sin(t)))
            ring0.append(_add(p0, off))
            ring1.append(_add(p1, off))
        for i in range(seg):
            j = (i + 1) % seg
            t = 2 * math.pi * (i + 0.5) / seg
            n = _add(_mul(a, math.cos(t)), _mul(b, math.sin(t)))
            self._face([ring0[i], ring1[i], ring1[j], ring0[j]], n, col, None, outline)
        self._face(list(reversed(ring0)), _mul(d, -1), col, None, outline)
        self._face(ring1, d, col, cap, outline)

    @staticmethod
    def _emissive(st: Optional[VisState]) -> QColor:
        if not st or st.intensity <= 0.02:
            return QColor(34, 36, 42)
        k = 0.35 + 0.65 * st.intensity
        return QColor(int(st.colour[0] * k), int(st.colour[1] * k), int(st.colour[2] * k))

    def _model(self, fx, kind: str, st: Optional[VisState], sel: bool) -> None:
        P = (fx.x, fx.y, fx.z)
        M = (0.0, 0.0, 1.0) if fx.mount == "hang" else (0.0, 0.0, -1.0)
        D = st.direction if st else (0.0, 0.0, -1.0)
        body = QColor(58, 61, 72)
        out = QColor(255, 200, 0) if sel else None
        em = self._emissive(st)
        T = _cross(D, M)
        if math.sqrt(_dot(T, T)) < 1e-3:
            r = math.radians(fx.rot)
            T = (math.cos(r), math.sin(r), 0.0)
        T = _norm(T)
        if kind in MOVING_KINDS:
            Fw = _norm(_cross(M, T))
            self._box(_add(P, _mul(M, 0.30)), (T, Fw, M), (0.20, 0.15, 0.06), body, outline=out)
            for s in (-1, 1):
                self._box(_add(_add(P, _mul(T, s * 0.18)), _mul(M, 0.13)), (T, Fw, M),
                          (0.025, 0.05, 0.13), body, outline=out)
            r = {"beam": 0.10, "spot": 0.12, "wash": 0.15}[kind]
            self._cylinder(_add(P, _mul(D, -0.14)), _add(P, _mul(D, 0.22)), r, QColor(48, 50, 60), em, out)
        elif kind == "par":
            self._box(_add(P, _mul(M, 0.18)), (T, _norm(_cross(M, T)), M), (0.02, 0.06, 0.06), body)
            self._cylinder(_add(P, _mul(D, -0.10)), _add(P, _mul(D, 0.16)), 0.11, body, em, out)
        elif kind == "fresnel":
            self._box(_add(P, _mul(M, 0.20)), (T, _norm(_cross(M, T)), M), (0.02, 0.06, 0.06), body)
            U = _norm(_cross(T, D))
            self._box(P, (D, T, U), (0.17, 0.15, 0.15), body, outline=out)
            self._cylinder(_add(P, _mul(D, 0.17)), _add(P, _mul(D, 0.19)), 0.12, body, em)
        elif kind in ("strobe", "ledbar", "blinder"):
            U = _norm(_cross(T, D))
            half = {"strobe": (0.06, 0.32, 0.09), "ledbar": (0.05, 0.50, 0.045),
                    "blinder": (0.08, 0.22, 0.12)}[kind]
            self._box(P, (D, T, U), half, body, front_emissive=em if kind == "strobe" else None, outline=out)
            if kind == "ledbar":
                for i in range(8):
                    c = _add(_add(P, _mul(D, 0.051)), _mul(T, -0.44 + i * 0.125))
                    self._cylinder(c, _add(c, _mul(D, 0.01)), 0.04, body, em, seg=8)
            elif kind == "blinder":
                for s in (-1, 1):
                    c = _add(_add(P, _mul(D, 0.081)), _mul(T, s * 0.11))
                    self._cylinder(c, _add(c, _mul(D, 0.01)), 0.08, body, em, seg=10)
        elif kind == "fog":
            base = (fx.x, fx.y, max(0.0, fx.z - 0.25) + 0.15)
            self._box(base, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.30, 0.18, 0.15), QColor(50, 52, 58), outline=out)
            nz = _add(base, (0.0, -0.18, 0.05))
            self._cylinder(nz, _add(nz, (0.0, -0.10, 0.0)), 0.04, QColor(30, 30, 34),
                           em if st and st.has_beam else None)
        else:
            self._box(P, (T, _norm(_cross(M, T)), M), (0.12, 0.12, 0.12), body, em, outline=out)

    def _draw_fog(self, p: QPainter) -> None:
        now = time.time()
        p.setPen(Qt.NoPen)
        for fx in self.show.fixtures:
            st = self._states.get(fx.fid)
            if not st or st.fog <= 0.02:
                continue
            for i in range(10):
                ph = (now * 0.25 + i / 10) % 1.0
                pos = (fx.x + math.sin(i * 2.1 + now * 0.3) * 0.8 * ph, fx.y - 0.3 - ph * 2.5, 0.35 + ph * 1.6)
                q = self.project(pos)
                if not q:
                    continue
                rad = 10 + 60 * ph
                g = QRadialGradient(q, rad)
                g.setColorAt(0, QColor(200, 200, 215, int(70 * st.fog * (1 - ph))))
                g.setColorAt(1, QColor(200, 200, 215, 0))
                p.setBrush(QBrush(g))
                p.drawEllipse(q, rad, rad)

    def _paint_3d(self, p: QPainter) -> None:
        W, D, H = self.show.stage_width, self.show.stage_depth, self.show.stage_height
        hw = W / 2 + 1
        floor = self._poly([(-hw, 0, 0), (hw, 0, 0), (hw, D + 0.5, 0), (-hw, D + 0.5, 0)])
        wall = self._poly([(-hw, D + 0.5, 0), (hw, D + 0.5, 0), (hw, D + 0.5, H + 2.5), (-hw, D + 0.5, H + 2.5)])
        p.setPen(Qt.NoPen)
        if wall:
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
        p.setPen(QPen(QColor(90, 90, 110), 2))
        self._line(p, (-W / 2, 0, 0), (W / 2, 0, 0))
        # trusses
        p.setPen(QPen(QColor(95, 98, 110), 4))
        levels = {}
        for fx in self.show.fixtures:
            if fx.mount == "hang" and abs(fx.x) <= W / 2 + 0.01:
                key = (round(fx.y, 1), round(fx.z, 1))
                lo, hi = levels.get(key, (fx.x, fx.x))
                levels[key] = (min(lo, fx.x), max(hi, fx.x))
        for (y, z), (lo, hi) in levels.items():
            self._line(p, (lo - 0.6, y, z + 0.38), (hi + 0.6, y, z + 0.38))
        for fx in self.show.fixtures:
            if abs(fx.x) > W / 2 + 0.01:
                self._line(p, (fx.x, fx.y, 0), (fx.x, fx.y, fx.z + 0.6))

        # beams (additive)
        beams = []
        for fx in self.show.fixtures:
            st = self._states.get(fx.fid)
            if not st or st.intensity <= 0.01 or not st.has_beam:
                continue
            kind = self.show.types[fx.type_key].kind
            pos = _add((fx.x, fx.y, fx.z), _mul(st.direction, self._lens_offset(kind)))
            L = self._hit(pos, st.direction)
            end = _add(pos, _mul(st.direction, L))
            beams.append((self.to_cam(end)[1], fx, st, pos, end, L))
        beams.sort(key=lambda b: -b[0])
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for _depth, fx, st, pos, end, L in beams:
            r = L * math.tan(math.radians(st.beam_angle / 2))
            a_c, e_c = self.to_cam(pos), self.to_cam(end)
            axis = _norm(_sub(e_c, a_c))
            perp = _norm(_cross(axis, _norm(e_c)))
            r0 = 0.05
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
            self._draw_pool(p, end, st, r, k)
            if pa:
                g = QRadialGradient(pa, 8 + 8 * k)
                c2 = QColor(col)
                c2.setAlpha(int(230 * k))
                g.setColorAt(0, c2)
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(QBrush(g))
                p.drawEllipse(pa, 8 + 8 * k, 8 + 8 * k)
        if self.fog_level > self.haze + 0.02:
            p.setBrush(QColor(120, 120, 140, int(60 * (self.fog_level - self.haze))))
            p.drawRect(self.rect())
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        self._draw_fog(p)

        # fixture models
        self._screen_pos.clear()
        self._faces = []
        for fx in self.show.fixtures:
            q = self.project((fx.x, fx.y, fx.z))
            if q is None:
                continue
            self._screen_pos[fx.fid] = q
            if self.show_models:
                self._model(fx, self.show.types[fx.type_key].kind, self._states.get(fx.fid),
                            fx.fid in self.selection)
        self._faces.sort(key=lambda f: -f[0])
        for _d, poly, col, outline in self._faces:
            p.setPen(QPen(outline, 1.5) if outline else QPen(QColor(10, 10, 12, 160), 0.6))
            p.setBrush(col)
            p.drawPolygon(poly)
        font = QFont()
        font.setPointSize(7)
        p.setFont(font)
        for fx in self.show.fixtures:
            q = self._screen_pos.get(fx.fid)
            if q is None:
                continue
            sel = fx.fid in self.selection
            if not self.show_models:
                p.setPen(QPen(QColor(255, 200, 0) if sel else QColor(20, 20, 24), 2 if sel else 1))
                p.setBrush(self._emissive(self._states.get(fx.fid)))
                p.drawEllipse(q, 6, 6)
            if self.show_labels:
                p.setPen(QColor(255, 210, 60) if sel else QColor(160, 162, 178))
                p.drawText(q + QPointF(-6, -16 if fx.mount == "hang" else 20), str(fx.fid))
        self._hud(p, "3D  |  drag: orbit   wheel: zoom   click: select (Ctrl = add)   Tab: next view")

    def _draw_pool(self, p: QPainter, end: Vec, st: VisState, r: float, k: float) -> None:
        if end[2] > 0.05:
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

    # ------------------------------------------------------------- 2D views
    def _paint_2d(self, p: QPainter) -> None:
        W, D, H = self.show.stage_width, self.show.stage_depth, self.show.stage_height
        top = self.mode == "top"
        far = D if top else H
        a, b = self.map2d(-W / 2, far), self.map2d(W / 2, 0)
        p.setPen(QPen(QColor(70, 70, 85), 1))
        p.setBrush(QColor(22, 22, 28))
        p.drawRect(QRectF(a, b))
        p.setFont(QFont("", 7))
        x = -math.floor(W / 2)
        while x <= W / 2 + 1e-6:
            p.setPen(QPen(QColor(46, 48, 60) if float(x).is_integer() else QColor(32, 33, 42), 1))
            p.drawLine(self.map2d(x, 0), self.map2d(x, far))
            if float(x).is_integer():
                p.setPen(QColor(90, 92, 105))
                p.drawText(self.map2d(x, 0) + QPointF(-6, 14), f"{x:g}")
            x += 0.5
        yv = 0.0
        while yv <= far + 1e-6:
            p.setPen(QPen(QColor(46, 48, 60) if yv.is_integer() else QColor(32, 33, 42), 1))
            p.drawLine(self.map2d(-W / 2, yv), self.map2d(W / 2, yv))
            if yv.is_integer():
                p.setPen(QColor(90, 92, 105))
                p.drawText(self.map2d(-W / 2, yv) + QPointF(-30, 4), f"{yv:g}m")
            yv += 0.5
        p.setPen(QColor(140, 140, 160))
        if top:
            p.drawText(self.map2d(-1.6, 0) + QPointF(0, 28), "AUDIENCE / DOWNSTAGE  (Y = 0)")
            p.drawText(self.map2d(-0.6, D) + QPointF(0, -8), "UPSTAGE")
        else:
            p.drawText(self.map2d(-1.6, 0) + QPointF(0, 28), "FLOOR (Z = 0)  –  seen from the audience")
        if top:
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            for fx in self.show.fixtures:
                st = self._states.get(fx.fid)
                if not st or st.intensity <= 0.01 or not st.has_beam:
                    continue
                pos = (fx.x, fx.y, fx.z)
                L = self._hit(pos, st.direction)
                end = _add(pos, _mul(st.direction, L))
                r = max(0.15, L * math.tan(math.radians(st.beam_angle / 2)))
                c = self.map2d(end[0], end[1])
                sc = self._scale2d() * r
                col = QColor(*st.colour)
                col.setAlpha(int(70 * st.intensity))
                g = QRadialGradient(c, sc)
                g.setColorAt(0, col)
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(g))
                p.drawEllipse(c, sc, sc)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        self._screen_pos.clear()
        f2 = QFont()
        f2.setPointSize(7)
        p.setFont(f2)
        order = sorted(self.show.fixtures, key=lambda f: f.z if top else -f.y)
        for fx in order:
            q = self.map2d(fx.x, fx.y if top else fx.z)
            self._screen_pos[fx.fid] = q
            st = self._states.get(fx.fid)
            sel = fx.fid in self.selection
            kind = self.show.types[fx.type_key].kind
            col = QColor(*st.colour) if st and st.intensity > 0.02 else None
            r = QRectF(q.x() - 13, q.y() - 13, 26, 26)
            if sel:
                p.setPen(QPen(QColor(255, 200, 0), 2))
                p.setBrush(QColor(255, 200, 0, 40))
                p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 4, 4)
            draw_icon(p, r, kind, col)
            if st:
                d = st.direction
                v = (d[0], -d[1]) if top else (d[0], -d[2])
                n = math.hypot(*v)
                if n > 0.15:
                    p.setPen(QPen(QColor(255, 200, 0, 170) if sel else QColor(120, 120, 140, 140), 1))
                    p.drawLine(q, q + QPointF(v[0] / n * 22, v[1] / n * 22))
            p.setPen(QColor(255, 210, 60) if sel else QColor(205, 205, 215))
            p.drawText(q + QPointF(-8, -15), str(fx.fid))
            if self.show_labels and (sel or len(self.show.fixtures) <= 24):
                p.setPen(QColor(150, 150, 165) if sel else QColor(110, 110, 125))
                lab = f"{fx.name[:10]}  {'z' if top else 'y'}{(fx.z if top else fx.y):.1f}"
                p.drawText(q + QPointF(-20, 24), lab)
        if self._drag and self._drag[0] == "band":
            p.setPen(QPen(QColor(255, 200, 0), 1, Qt.DashLine))
            p.setBrush(QColor(255, 200, 0, 25))
            p.drawRect(QRectF(self._drag[1], self._drag[2]).normalized())
        txt = "TOP VIEW – edit X/Y" if top else "FRONT VIEW – edit X / height Z"
        self._hud(p, f"{txt}  |  drag fixture: move (whole selection, snap {self.snap:g} m)   "
                     "drag empty area: box select   Tab: next view")

    def _hud(self, p: QPainter, text: str) -> None:
        p.setPen(QColor(120, 120, 140))
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        p.drawText(8, self.height() - 8, text)

    # ------------------------------------------------------------------ mouse
    def _pick(self, pos: QPointF) -> Optional[int]:
        best, bd = None, 16.0
        for fid, q in self._screen_pos.items():
            d = math.hypot(q.x() - pos.x(), q.y() - pos.y())
            if d < bd:
                best, bd = fid, d
        return best

    def _coords(self, fid: int) -> tuple[float, float]:
        fx = self.show.fixture(fid)
        return (fx.x, fx.y) if self.mode == "top" else (fx.x, fx.z)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        fid = self._pick(pos)
        add = bool(e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
        if fid is not None:
            if not (fid in self.selection and self.mode != "3d" and not add):
                self.fixtureClicked.emit(fid, add)
            if self.mode != "3d":
                ids = set(self.selection) | {fid}
                self._drag = ("move", pos, {f: self._coords(f) for f in ids if self.show.fixture(f)})
            else:
                self._drag = None
            return
        if self.mode == "3d":
            self._drag = ("orbit", pos, self.yaw, self.pitch)
        else:
            self._drag = ("band", pos, pos, add)

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        pos = e.position()
        kind = self._drag[0]
        if kind == "move":
            _, start, orig = self._drag
            a0, b0 = self.unmap2d(start)
            a1, b1 = self.unmap2d(pos)
            da, db = a1 - a0, b1 - b0
            sn = self.snap or 0.01
            for fid, (a, b) in orig.items():
                fx = self.show.fixture(fid)
                na, nb = round((a + da) / sn) * sn, round((b + db) / sn) * sn
                if self.mode == "top":
                    fx.x, fx.y = na, nb
                else:
                    fx.x, fx.z = na, max(0.0, nb)
                self.fixtureMoved.emit(fid)
            self.layoutEdited.emit()
        elif kind == "orbit":
            _, start, yaw, pitch = self._drag
            self.yaw = yaw + (pos.x() - start.x()) * 0.008
            self.pitch = max(-0.1, min(1.45, pitch + (pos.y() - start.y()) * 0.006))
        elif kind == "band":
            self._drag = ("band", self._drag[1], pos, self._drag[3])
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag and self._drag[0] == "band":
            r = QRectF(self._drag[1], self._drag[2]).normalized()
            if r.width() > 4 and r.height() > 4:
                if not self._drag[3]:
                    self.fixtureClicked.emit(-1, False)
                for fid, q in self._screen_pos.items():
                    if r.contains(q):
                        self.fixtureClicked.emit(fid, True)
        self._drag = None
        self.update()

    def wheelEvent(self, e):
        self.dist = max(4.0, min(40.0, self.dist * (0.9 if e.angleDelta().y() > 0 else 1.1)))
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Tab:
            self.toggle_mode()
        else:
            super().keyPressEvent(e)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def toggle_mode(self) -> None:
        self.mode = {"3d": "top", "top": "front", "front": "3d"}[self.mode]
        self.update()

    def reset_camera(self) -> None:
        self.yaw, self.pitch, self.dist = 0.0, 0.30, 16.0
        self.update()

    def focusNextPrevChild(self, nxt):   # keep Tab for the view toggle
        return False
