"""3D meshes for fixture models: built-in low-poly models + OBJ / GLB / glTF / STL import.

Model convention (also used for imported files)
-----------------------------------------------
* units: metres (imported models can be auto-fitted)
* Z is up = away from the mounting surface; the model stands on the floor
* the light comes out of the head along **+Z** (pointing up) at tilt centre
* parts (OBJ ``o``/``g`` names, glTF node names):
    ``base``  fixed to the truss / floor
    ``yoke``  turns with pan
    ``head``  turns with pan and tilt around the pivot
  anything else belongs to ``base``; a model without a ``head`` turns as a whole
* materials whose name contains lens / emit / led / light / glass (or with an
  emissive colour) glow with the DMX colour and intensity
* optional OBJ comment ``# minidesk pivot x y z`` sets the tilt pivot
"""
from __future__ import annotations

import base64
import json
import math
import os
import struct
from dataclasses import dataclass, field

import numpy as np

EMISSIVE_WORDS = ("lens", "emit", "led", "light", "glass", "lamp")


@dataclass
class Part:
    name: str
    verts: list = field(default_factory=list)        # [(x, y, z)]
    faces: list = field(default_factory=list)        # [[i, j, k, ...]]
    colors: list = field(default_factory=list)       # per face (r, g, b) 0..255
    emissive: list = field(default_factory=list)     # per face bool

    # numpy caches (filled by finalize)
    V: np.ndarray | None = None
    N: np.ndarray | None = None      # face normals
    C: np.ndarray | None = None      # face centroids
    COL: np.ndarray | None = None
    EM: np.ndarray | None = None

    def add(self, verts, faces, color, emissive=False, orient=True, centre=None):
        """Add a convex primitive; faces are re-oriented to point away from its centre."""
        o = len(self.verts)
        self.verts.extend(verts)
        if orient and verts:
            vc = np.array(verts, dtype=float)
            cen = np.array(centre, dtype=float) if centre is not None else vc.mean(axis=0)
        for f in faces:
            if orient and verts and len(f) >= 3:
                p = vc[f]
                n = np.cross(p[1] - p[0], p[2] - p[0])
                if np.linalg.norm(n) < 1e-12 and len(f) > 3:
                    n = np.cross(p[2] - p[0], p[3] - p[0])
                if np.dot(n, p.mean(axis=0) - cen) < 0:
                    f = list(reversed(f))
            self.faces.append([o + i for i in f])
            self.colors.append(color)
            self.emissive.append(emissive)

    def finalize(self):
        self.V = np.array(self.verts, dtype=float).reshape(-1, 3)
        n, c = [], []
        for f in self.faces:
            p = self.V[f]
            c.append(p.mean(axis=0))
            nn = np.zeros(3)
            for k in range(len(f)):          # Newell's method: robust for polygons
                a, b = p[k], p[(k + 1) % len(f)]
                nn += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]),
                                (a[0] - b[0]) * (a[1] + b[1])])
            ln = np.linalg.norm(nn)
            n.append(nn / ln if ln > 1e-12 else np.array([0, 0, 1.0]))
        self.N = np.array(n).reshape(-1, 3)
        self.C = np.array(c).reshape(-1, 3)
        self.COL = np.array(self.colors, dtype=float).reshape(-1, 3)
        self.EM = np.array(self.emissive, dtype=bool)


@dataclass
class Mesh:
    name: str
    parts: dict = field(default_factory=dict)        # name -> Part
    pivot: tuple = (0.0, 0.0, 0.0)
    cull: bool = True                                 # built-in meshes have consistent winding

    def part(self, name: str) -> Part:
        if name not in self.parts:
            self.parts[name] = Part(name)
        return self.parts[name]

    def finalize(self) -> "Mesh":
        self.parts = {k: p for k, p in self.parts.items() if p.faces}
        for p in self.parts.values():
            p.finalize()
        return self

    @property
    def face_count(self) -> int:
        return sum(len(p.faces) for p in self.parts.values())

    def bounds(self):
        allv = np.concatenate([p.V for p in self.parts.values()]) if self.parts else np.zeros((1, 3))
        return allv.min(axis=0), allv.max(axis=0)

    def scaled(self, k: float) -> "Mesh":
        m = Mesh(self.name, pivot=tuple(np.array(self.pivot) * k), cull=self.cull)
        for name, p in self.parts.items():
            q = m.part(name)
            q.verts = [tuple(np.array(v) * k) for v in p.verts]
            q.faces, q.colors, q.emissive = p.faces, p.colors, p.emissive
        return m.finalize()


# ----------------------------------------------------------------- builders
def _box(cx, cy, cz, sx, sy, sz):
    x0, x1, y0, y1, z0, z1 = cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, cz - sz / 2, cz + sz / 2
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return v, f


def box(part: Part, c, s, color, emissive=False, top_emissive=None):
    v, f = _box(*c, *s)
    if top_emissive is None:
        part.add(v, f, color, emissive)
    else:
        part.add(v, [ff for i, ff in enumerate(f) if i != 1], color)
        part.add(v, [f[1]], top_emissive, True)


def frustum(part: Part, r0, r1, z0, z1, seg, color, cx=0.0, cy=0.0, cap0=True, cap1=True,
            cap1_color=None, cap1_emissive=False, axis="z"):
    """Cone frustum along Z (or X / Y) from radius r0 at z0 to r1 at z1."""
    def P(r, a, z):
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        if axis == "x":
            return (z, x, y)
        if axis == "y":
            return (y, z, x)
        return (x, y, z)
    ring0 = [P(r0, 2 * math.pi * i / seg, z0) for i in range(seg)]
    ring1 = [P(r1, 2 * math.pi * i / seg, z1) for i in range(seg)]
    v = ring0 + ring1
    cen = np.array(ring0 + ring1, dtype=float).mean(axis=0)
    faces = [[i, (i + 1) % seg, seg + (i + 1) % seg, seg + i] for i in range(seg)]
    part.add(v, faces, color, centre=cen)
    if cap0:
        part.add(v, [list(range(seg))], color, centre=cen)
    if cap1:
        part.add(v, [[seg + i for i in range(seg)]], cap1_color or color, cap1_emissive, centre=cen)


def cylinder(part, r, z0, z1, seg, color, **kw):
    frustum(part, r, r, z0, z1, seg, color, **kw)


DARK = (42, 44, 50)
BODY = (58, 61, 70)
METAL = (120, 124, 132)
TRUSS = (175, 178, 186)
LENS = (230, 230, 240)
DISPLAY = (20, 40, 80)


def _moving(name: str, base_w, base_d, base_h, arm_h, head_r, head_len, lens_r, seg, wash=False) -> Mesh:
    m = Mesh(name)
    b = m.part("base")
    box(b, (0, 0, base_h / 2), (base_w, base_d, base_h), BODY)
    box(b, (0, -base_d / 2 - 0.004, base_h * 0.55), (base_w * 0.35, 0.008, base_h * 0.45), DISPLAY)
    if seg >= 10:
        for s in (-1, 1):   # handles
            box(b, (s * (base_w / 2 + 0.012), 0, base_h * 0.6), (0.02, base_d * 0.5, 0.03), DARK)
    y = m.part("yoke")
    box(y, (0, 0, base_h + 0.02), (base_w * 0.9, base_d * 0.55, 0.04), DARK)
    pivot_z = base_h + 0.04 + arm_h * 0.62
    for s in (-1, 1):
        box(y, (s * (head_r + 0.035), 0, base_h + 0.04 + arm_h / 2), (0.045, base_d * 0.45, arm_h), DARK)
    h = m.part("head")
    zb, zf = pivot_z - head_len * 0.42, pivot_z + head_len * 0.58
    if wash:
        frustum(h, head_r * 0.75, head_r, zb, zf - 0.03, seg, BODY, cap1=False)
        cylinder(h, head_r * 1.02, zf - 0.03, zf, seg, DARK, cap0=False, cap1_color=LENS, cap1_emissive=True)
    else:
        frustum(h, head_r * 0.82, head_r, zb, zf - 0.025, seg, BODY, cap1=False)
        frustum(h, head_r, head_r * 1.05, zf - 0.025, zf, seg, DARK, cap0=False, cap1_color=DARK)
        cylinder(h, lens_r, zf, zf + 0.006, seg, LENS, cap0=False, cap1_color=LENS, cap1_emissive=True)
    if seg >= 10:
        for s in (-1, 1):   # tilt hubs
            frustum(h, 0.04, 0.04, s * head_r, s * (head_r + 0.03), 8, DARK, axis="x", cx=0, cy=pivot_z)
    m.pivot = (0.0, 0.0, pivot_z)
    return m


def build_model(kind: str, lod: int = 1) -> Mesh:
    """Built-in models. lod 1 = detailed, 0 = light (for far away fixtures)."""
    seg = 14 if lod else 6
    if kind == "beam":
        return _moving("beam", 0.34, 0.26, 0.13, 0.30, 0.095, 0.34, 0.07, seg).finalize()
    if kind == "spot":
        return _moving("spot", 0.40, 0.28, 0.14, 0.34, 0.115, 0.40, 0.08, seg).finalize()
    if kind == "hybrid":
        return _moving("hybrid", 0.44, 0.31, 0.16, 0.38, 0.13, 0.50, 0.09, seg).finalize()
    if kind == "wash":
        return _moving("wash", 0.40, 0.30, 0.14, 0.32, 0.15, 0.30, 0.13, seg, wash=True).finalize()
    m = Mesh(kind)
    b, y, h = m.part("base"), m.part("yoke"), m.part("head")
    if kind == "par":
        box(b, (0, 0, 0.015), (0.06, 0.06, 0.03), DARK)                 # clamp
        box(y, (0, 0, 0.035), (0.28, 0.05, 0.015), METAL)                # bracket
        for s in (-1, 1):
            box(y, (s * 0.135, 0, 0.11), (0.012, 0.05, 0.16), METAL)
        cylinder(h, 0.11, 0.06, 0.26, seg, BODY, cap1=False)
        if lod:
            for z in (0.09, 0.13, 0.17):                                  # cooling fins
                cylinder(h, 0.116, z, z + 0.01, seg, DARK, cap0=False, cap1=False)
        cylinder(h, 0.118, 0.26, 0.275, seg, DARK, cap0=False, cap1=False)
        cylinder(h, 0.10, 0.268, 0.272, seg, LENS, cap0=False, cap1_color=LENS, cap1_emissive=True)
        m.pivot = (0, 0, 0.16)
    elif kind == "fresnel":
        box(b, (0, 0, 0.015), (0.06, 0.06, 0.03), DARK)
        box(y, (0, 0, 0.035), (0.34, 0.05, 0.015), METAL)
        for s in (-1, 1):
            box(y, (s * 0.165, 0, 0.13), (0.012, 0.05, 0.2), METAL)
        box(h, (0, 0, 0.2), (0.28, 0.28, 0.3), BODY)
        cylinder(h, 0.11, 0.35, 0.37, seg, DARK, cap0=False, cap1_color=LENS, cap1_emissive=True)
        if lod:
            for ang in range(4):                                          # barn doors
                a = ang * math.pi / 2
                cx, cy = 0.15 * math.cos(a), 0.15 * math.sin(a)
                sx, sy = (0.01, 0.26) if ang % 2 == 0 else (0.26, 0.01)
                box(h, (cx, cy, 0.42), (sx, sy, 0.1), DARK)
        m.pivot = (0, 0, 0.2)
    elif kind == "strobe":
        box(b, (0, 0, 0.015), (0.06, 0.06, 0.03), DARK)
        box(y, (0, 0, 0.035), (0.5, 0.04, 0.015), METAL)
        for s in (-1, 1):
            box(y, (s * 0.24, 0, 0.08), (0.012, 0.04, 0.1), METAL)
        box(h, (0, 0, 0.11), (0.52, 0.14, 0.1), BODY, top_emissive=LENS)
        m.pivot = (0, 0, 0.11)
    elif kind == "ledbar":
        box(y, (0, 0, 0.02), (0.9, 0.04, 0.012), METAL)
        box(h, (0, 0, 0.07), (1.0, 0.07, 0.07), BODY)
        for i in range(8 if lod else 4):
            n = 8 if lod else 4
            cx = -0.44 + i * 0.88 / (n - 1)
            cylinder(h, 0.028, 0.105, 0.11, 8 if lod else 4, LENS, cx=cx, cap0=False,
                     cap1_color=LENS, cap1_emissive=True)
        m.pivot = (0, 0, 0.07)
    elif kind == "blinder":
        box(y, (0, 0, 0.03), (0.4, 0.04, 0.015), METAL)
        box(h, (0, 0, 0.13), (0.46, 0.12, 0.2), BODY)
        for s in (-1, 1):
            cylinder(h, 0.08, 0.23, 0.235, seg, LENS, cx=s * 0.11, cap0=False, cap1_color=LENS, cap1_emissive=True)
        m.pivot = (0, 0, 0.13)
    elif kind in ("fog", "hazer", "fog_vertical"):
        if kind == "fog_vertical":
            box(b, (0, 0, 0.16), (0.36, 0.36, 0.32), BODY)
            cylinder(b, 0.09, 0.32, 0.36, seg, DARK, cap1_color=DARK)
            cylinder(b, 0.035, 0.36, 0.40, 8, (25, 25, 28), cap1_color=(10, 10, 10))
            frustum(m.part("led"), 0.085, 0.085, 0.355, 0.362, seg, LENS, cap0=False, cap1_color=LENS,
                    cap1_emissive=True)
        else:
            w, d, hh = (0.56, 0.30, 0.28) if kind == "fog" else (0.46, 0.30, 0.26)
            box(b, (0, 0, hh / 2), (w, d, hh), BODY)
            box(b, (0, 0, hh + 0.04), (w * 0.5, 0.03, 0.02), DARK)        # handle
            for s in (-1, 1):
                box(b, (s * w * 0.25, 0, hh + 0.02), (0.02, 0.03, 0.04), DARK)
            frustum(b, 0.03, 0.04, 0, 0.08, 8, (25, 25, 28), cx=0, cy=hh * 0.6, axis="y")
            box(b, (w * 0.3, -d / 2 - 0.003, hh * 0.6), (0.08, 0.006, 0.04), DISPLAY)
        m.pivot = (0, 0, 0)
    else:
        box(h, (0, 0, 0.12), (0.24, 0.24, 0.24), BODY, top_emissive=LENS)
    return m.finalize()


_truss_cache: dict = {}


def truss_mesh(length: float, size: float = 0.29, lod: int = 1) -> Mesh:
    """Box truss along +X starting at 0 (for rigging). Cached per length."""
    key = (round(length * 4) / 4, size, lod)
    if key not in _truss_cache:
        _truss_cache[key] = _build_truss(*key)
    return _truss_cache[key]


def _build_truss(length: float, size: float, lod: int) -> Mesh:
    m = Mesh("truss")
    p = m.part("base")
    t = 0.03
    hs = size / 2 - t / 2
    for sy in (-1, 1):
        for sz in (-1, 1):
            box(p, (length / 2, sy * hs, sz * hs), (length, t, t), TRUSS)
    if lod:
        n = max(1, int(length / size))
        step = length / n
        for i in range(n):
            x = i * step + step / 2
            for sy in (-1, 1):       # verticals on the sides
                box(p, (x - step / 2 + 0.01, sy * hs, 0), (0.015, 0.015, size - t), TRUSS)
            for sz in (-1, 1):       # top / bottom rungs
                box(p, (x - step / 2 + 0.01, 0, sz * hs), (0.015, size - t, 0.015), TRUSS)
    return m.finalize()


BUILTIN = ["beam", "spot", "hybrid", "wash", "par", "fresnel", "strobe", "ledbar", "blinder",
           "fog", "fog_vertical", "hazer", "generic"]
BUILTIN_LABELS = {
    "beam": "Moving head – Beam (e.g. 230/280 beam)", "spot": "Moving head – Spot",
    "hybrid": "Moving head – Hybrid beam/spot/wash", "wash": "Moving head – Wash",
    "par": "LED PAR can", "fresnel": "Fresnel / profile with barn doors", "strobe": "Strobe bar",
    "ledbar": "LED bar", "blinder": "Blinder (2-lite)", "fog": "Fog machine",
    "fog_vertical": "Fog machine – vertical spray with LED", "hazer": "Hazer", "generic": "Generic box",
}


# ------------------------------------------------------------------ export
def write_obj(mesh: Mesh, path: str) -> None:
    base = os.path.splitext(path)[0]
    mtl_name = os.path.basename(base) + ".mtl"
    mats: dict[tuple, str] = {}
    lines = [f"# MiniDesk fixture model: {mesh.name}", "# units: metres, Z up, light along +Z",
             f"# minidesk pivot {mesh.pivot[0]:.4f} {mesh.pivot[1]:.4f} {mesh.pivot[2]:.4f}", f"mtllib {mtl_name}"]
    vo = 1
    for name, p in mesh.parts.items():
        lines.append(f"o {name}")
        for v in p.verts:
            lines.append(f"v {v[0]:.5f} {v[1]:.5f} {v[2]:.5f}")
        cur = None
        for f, col, em in zip(p.faces, p.colors, p.emissive):
            key = (tuple(col), em)
            if key not in mats:
                mats[key] = f"{'lens' if em else 'mat'}_{len(mats)}"
            if mats[key] != cur:
                cur = mats[key]
                lines.append(f"usemtl {cur}")
            lines.append("f " + " ".join(str(i + vo) for i in f))
        vo += len(p.verts)
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(os.path.dirname(path), mtl_name), "w") as fh:
        for (col, em), name in mats.items():
            r, g, b = (c / 255 for c in col)
            fh.write(f"newmtl {name}\nKd {r:.3f} {g:.3f} {b:.3f}\n")
            if em:
                fh.write(f"Ke {r:.3f} {g:.3f} {b:.3f}\n")
            fh.write("\n")


# ------------------------------------------------------------------ import
def _part_name(name: str) -> str:
    n = (name or "").lower()
    if "head" in n:
        return "head"
    if "yoke" in n or "arm" in n:
        return "yoke"
    return "base"


def _is_emissive(name: str) -> bool:
    n = (name or "").lower()
    return any(w in n for w in EMISSIVE_WORDS)


def load_obj(path: str) -> Mesh:
    mesh = Mesh(os.path.basename(path), cull=False)
    verts: list = []
    mats: dict[str, tuple] = {}
    mat_em: dict[str, bool] = {}
    folder = os.path.dirname(path)
    part = mesh.part("base")
    cur_col, cur_em = (150, 152, 160), False
    pivot = None
    local: dict[int, int] = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("# minidesk pivot"):
            try:
                pivot = tuple(float(x) for x in s.split()[3:6])
            except ValueError:
                pass
            continue
        if s[0] == "#":
            continue
        t = s.split()
        k = t[0]
        if k == "v" and len(t) >= 4:
            verts.append((float(t[1]), float(t[2]), float(t[3])))
        elif k in ("o", "g"):
            part = mesh.part(_part_name(" ".join(t[1:])))
            local = {}
        elif k == "mtllib":
            mp = os.path.join(folder, " ".join(t[1:]))
            if os.path.exists(mp):
                name = None
                for ml in open(mp, encoding="utf-8", errors="replace"):
                    mt = ml.split()
                    if not mt:
                        continue
                    if mt[0] == "newmtl":
                        name = " ".join(mt[1:])
                        mats[name] = (150, 152, 160)
                        mat_em[name] = _is_emissive(name)
                    elif mt[0] == "Kd" and name and len(mt) >= 4:
                        mats[name] = tuple(int(max(0, min(1, float(x))) * 255) for x in mt[1:4])
                    elif mt[0] == "Ke" and name and len(mt) >= 4 and any(float(x) > 0.05 for x in mt[1:4]):
                        mat_em[name] = True
        elif k == "usemtl":
            name = " ".join(t[1:])
            cur_col, cur_em = mats.get(name, (150, 152, 160)), mat_em.get(name, _is_emissive(name))
        elif k == "f" and len(t) >= 4:
            idx = []
            for tok in t[1:]:
                i = int(tok.split("/")[0])
                i = i - 1 if i > 0 else len(verts) + i
                if i not in local:
                    local[i] = len(part.verts)
                    part.verts.append(verts[i])
                idx.append(local[i])
            part.faces.append(idx)
            part.colors.append(cur_col)
            part.emissive.append(cur_em)
    mesh.finalize()
    mesh.pivot = pivot or _default_pivot(mesh)
    return mesh


def load_stl(path: str) -> Mesh:
    mesh = Mesh(os.path.basename(path), cull=False)
    p = mesh.part("head")
    data = open(path, "rb").read()
    tris = []
    if data[:5] == b"solid" and b"facet" in data[:2048]:
        cur = []
        for ln in data.decode("latin1").splitlines():
            t = ln.split()
            if t and t[0] == "vertex":
                cur.append(tuple(float(x) for x in t[1:4]))
                if len(cur) == 3:
                    tris.append(cur)
                    cur = []
    else:
        n = struct.unpack_from("<I", data, 80)[0]
        for i in range(n):
            o = 84 + i * 50 + 12
            tris.append([struct.unpack_from("<3f", data, o + 12 * k) for k in range(3)])
    for tri in tris:
        p.add(tri, [[0, 1, 2]], (160, 162, 170))
    mesh.finalize()
    mesh.pivot = _default_pivot(mesh)
    return mesh


def _quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def load_gltf(path: str) -> Mesh:
    """glTF 2.0 (.glb or .gltf with embedded / external buffers). Y-up is converted to Z-up."""
    raw = open(path, "rb").read()
    bins: list[bytes] = []
    if raw[:4] == b"glTF":
        off = 12
        gj = None
        while off < len(raw):
            ln, typ = struct.unpack_from("<I4s", raw, off)
            chunk = raw[off + 8:off + 8 + ln]
            if typ == b"JSON":
                gj = json.loads(chunk)
            elif typ == b"BIN\x00":
                bins.append(chunk)
            off += 8 + ln
    else:
        gj = json.loads(raw)
    buffers = []
    for i, b in enumerate(gj.get("buffers", [])):
        uri = b.get("uri")
        if uri is None:
            buffers.append(bins[0] if bins else b"")
        elif uri.startswith("data:"):
            buffers.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            buffers.append(open(os.path.join(os.path.dirname(path), uri), "rb").read())
    comp = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def accessor(i):
        a = gj["accessors"][i]
        bv = gj["bufferViews"][a["bufferView"]]
        buf = buffers[bv["buffer"]]
        fmt, size = comp[a["componentType"]]
        n = ncomp[a["type"]]
        stride = bv.get("byteStride", size * n)
        base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        out = []
        for k in range(a["count"]):
            vals = struct.unpack_from(f"<{n}{fmt}", buf, base + k * stride)
            out.append(vals if n > 1 else vals[0])
        return out

    mesh = Mesh(os.path.basename(path), cull=False)
    mats = gj.get("materials", [])

    def node_matrix(nd):
        if "matrix" in nd:
            return np.array(nd["matrix"], dtype=float).reshape(4, 4).T
        M = np.eye(4)
        S = np.diag(list(nd.get("scale", [1, 1, 1])) + [1])
        R = np.eye(4)
        R[:3, :3] = _quat_mat(nd.get("rotation", [0, 0, 0, 1]))
        T = np.eye(4)
        T[:3, 3] = nd.get("translation", [0, 0, 0])
        return M @ T @ R @ S

    yup = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float)

    def walk(ni, parent, pname):
        nd = gj["nodes"][ni]
        M = parent @ node_matrix(nd)
        name = nd.get("name", "") or pname
        if "mesh" in nd:
            part = mesh.part(_part_name(name))
            for prim in gj["meshes"][nd["mesh"]].get("primitives", []):
                if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                    continue
                pos = np.array(accessor(prim["attributes"]["POSITION"]), dtype=float)
                pos = (yup @ M @ np.c_[pos, np.ones(len(pos))].T).T[:, :3]
                idx = accessor(prim["indices"]) if "indices" in prim else list(range(len(pos)))
                col, em = (160, 162, 170), False
                if "material" in prim and prim["material"] < len(mats):
                    mt = mats[prim["material"]]
                    bc = mt.get("pbrMetallicRoughness", {}).get("baseColorFactor", [0.63, 0.64, 0.67, 1])
                    col = tuple(int(max(0, min(1, c)) * 255) for c in bc[:3])
                    em = _is_emissive(mt.get("name", "")) or any(c > 0.05 for c in mt.get("emissiveFactor", [0, 0, 0]))
                part.add([tuple(v) for v in pos], [list(idx[i:i + 3]) for i in range(0, len(idx) - 2, 3)], col, em)
        for c in nd.get("children", []):
            walk(c, M, name)

    scene = gj.get("scenes", [{}])[gj.get("scene", 0)] if gj.get("scenes") else {"nodes": range(len(gj.get("nodes", [])))}
    for ni in scene.get("nodes", []):
        walk(ni, np.eye(4), "")
    mesh.finalize()
    mesh.pivot = _default_pivot(mesh)
    return mesh


def _default_pivot(mesh: Mesh):
    head = mesh.parts.get("head")
    if head is None or head.V is None or not len(head.V):
        return (0.0, 0.0, 0.0)
    lo, hi = head.V.min(axis=0), head.V.max(axis=0)
    return tuple(float(x) for x in (lo + hi) / 2)


def load_model(path: str) -> Mesh:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        m = load_obj(path)
    elif ext in (".glb", ".gltf"):
        m = load_gltf(path)
    elif ext == ".stl":
        m = load_stl(path)
    else:
        raise ValueError(f"Unsupported model format: {ext} (use OBJ, GLB/glTF or STL)")
    if not m.parts:
        raise ValueError("The model contains no polygons")
    return m


TYPICAL_SIZE = {"beam": 0.55, "spot": 0.7, "hybrid": 0.7, "wash": 0.6, "par": 0.3, "fresnel": 0.45,
                "strobe": 0.55, "ledbar": 1.0, "blinder": 0.46, "fog": 0.56, "fog_vertical": 0.4,
                "hazer": 0.46, "generic": 0.3}


def fit_scale(mesh: Mesh, kind: str) -> float:
    """Scale that makes an imported model about as big as a real fixture of that kind
    (handles models exported in mm or cm)."""
    lo, hi = mesh.bounds()
    size = float(max(hi - lo)) or 1.0
    return TYPICAL_SIZE.get(kind, 0.4) / size


# ------------------------------------------------------------------ cache
_cache: dict = {}


def get_mesh(model: str, kind: str, scale: float = 1.0, lod: int = 1) -> Mesh | None:
    """model = built-in name or a file path. Results are cached."""
    key = (model or kind, kind, round(scale, 5), lod)
    if key in _cache:
        return _cache[key]
    name = model or default_model(kind)
    try:
        if name in BUILTIN:
            m = build_model(name, lod)
        else:
            base = load_model(name)
            k = fit_scale(base, kind) * scale
            m = base.scaled(k)
            if lod == 0 and m.face_count > 400:
                m = build_model(default_model(kind), 0)     # far away: cheap stand-in
    except Exception:
        m = build_model(default_model(kind), lod)
    _cache[key] = m
    return m


def default_model(kind: str) -> str:
    return {"beam": "beam", "spot": "spot", "wash": "wash", "par": "par", "fresnel": "fresnel",
            "strobe": "strobe", "ledbar": "ledbar", "blinder": "blinder", "fog": "fog"}.get(kind, "generic")


def clear_cache() -> None:
    _cache.clear()
