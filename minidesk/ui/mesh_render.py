"""Vectorised rendering of fixture / truss meshes for the QPainter stage view."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPolygonF

from ..meshes import Mesh

LIGHT = np.array([0.35, -0.55, 0.76])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def rotx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rotz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


ROT_X_TO_Z = np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], dtype=float)   # maps +X onto +Z


class Camera:
    """Snapshot of the stage view camera, used to project numpy arrays."""

    def __init__(self, target, yaw, pitch, dist, width, height):
        self.target = np.array(target, dtype=float)
        c, s = math.cos(-yaw), math.sin(-yaw)
        ry = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        cp, sp = math.cos(pitch), math.sin(pitch)
        rp = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        self.R = rp @ ry
        self.dist = dist
        self.w, self.h = width, height
        self.f = min(width, height * 1.6) * 0.9

    def to_cam(self, P: np.ndarray) -> np.ndarray:
        c = (P - self.target) @ self.R.T
        c[..., 1] += self.dist
        return c

    def project(self, C: np.ndarray):
        d = np.maximum(C[..., 1], 1e-3)
        return self.w / 2 + self.f * C[..., 0] / d, self.h / 2 - self.f * C[..., 2] / d

    def px_size(self, P, size_m: float) -> float:
        c = self.to_cam(np.array(P, dtype=float))
        return self.f * size_m / max(c[1], 0.2)


def part_transforms(mesh: Mesh, pos, yaw_deg: float, tilt_deg: float, rot_deg: float, floor: bool,
                    fog: bool = False):
    """Return {part: (R, t, pivot)} so that world = t + R @ (v - pivot) + Rbody @ pivot."""
    P = np.array(pos, dtype=float)
    Rm = np.eye(3) if floor else rotx(math.pi)
    t = math.radians(tilt_deg)
    Rt = rotx(t) if floor else rotx(-t)
    Ry = rotz(math.radians(yaw_deg)) @ Rm
    Rb = rotz(math.radians(rot_deg)) @ Rm
    piv = np.array(mesh.pivot, dtype=float)
    has_head = "head" in mesh.parts
    out = {}
    for name in mesh.parts:
        if fog:
            out[name] = (rotz(math.radians(rot_deg)), P, np.zeros(3), np.zeros(3))
        elif name == "head" or not has_head:
            # head: tilt around the pivot, then pan / mount
            out[name] = (Ry @ Rt, P + Ry @ piv, piv, None)
        elif name == "yoke":
            out[name] = (Ry, P, np.zeros(3), None)
        else:
            out[name] = (Rb, P, np.zeros(3), None)
    return out


def lens_origin(mesh: Mesh, pos, direction, floor: bool, yaw_deg: float) -> np.ndarray:
    """Where the beam leaves the model (front of the head)."""
    head = mesh.parts.get("head")
    piv = np.array(mesh.pivot, dtype=float)
    Rm = np.eye(3) if floor else rotx(math.pi)
    Ry = rotz(math.radians(yaw_deg)) @ Rm
    front = float(head.V[:, 2].max() - piv[2]) if head is not None else 0.1
    return np.array(pos, dtype=float) + Ry @ piv + np.array(direction) * front


def mesh_faces(cam: Camera, mesh: Mesh, transforms: dict, emissive: QColor | None,
               outline: QColor | None, out: list) -> None:
    """Append visible faces (depth, QPolygonF, QColor, outline) to ``out``."""
    for name, part in mesh.parts.items():
        R, t, piv, _ = transforms[name]
        W = (part.V - piv) @ R.T + t
        Cw = (part.C - piv) @ R.T + t
        Nw = part.N @ R.T
        Vc = cam.to_cam(W)
        Cc = cam.to_cam(Cw)
        Nc = Nw @ cam.R.T
        facing = np.einsum("ij,ij->i", Nc, Cc) < 0
        if mesh.cull:
            vis = facing & (Cc[:, 1] > 0.25)
        else:
            vis = Cc[:, 1] > 0.25
            Nw = np.where(facing[:, None], Nw, -Nw)
        if not vis.any():
            continue
        shade = 0.38 + 0.62 * np.clip(Nw @ LIGHT, 0, 1)
        cols = (part.COL * shade[:, None]).clip(0, 255).astype(int)
        sx, sy = cam.project(Vc)
        for i in np.nonzero(vis)[0]:
            f = part.faces[i]
            poly = QPolygonF([QPointF(sx[j], sy[j]) for j in f])
            if part.EM[i] and emissive is not None:
                col = emissive
            else:
                c = cols[i]
                col = QColor(int(c[0]), int(c[1]), int(c[2]))
            out.append((float(Cc[i, 1]), poly, col, outline))


def truss_transform(start, axis: str):
    """Truss meshes are built along +X from the origin."""
    R = np.eye(3) if axis == "x" else ROT_X_TO_Z
    return {"base": (R, np.array(start, dtype=float), np.zeros(3), None)}
