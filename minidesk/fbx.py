"""Minimal reader for binary FBX (7.x) meshes – enough for fixture models.

Reads Geometry (vertices + polygons), Model hierarchy with local translation /
rotation / scaling (+ pre-rotation and geometric offsets), material diffuse
colours and the scene's up axis. Animation, skinning and textures are ignored.
ASCII FBX is not supported (re-export as binary or OBJ/GLB).
"""
from __future__ import annotations

import math
import struct
import zlib

import numpy as np


class Node:
    __slots__ = ("name", "props", "children")

    def __init__(self, name, props, children):
        self.name, self.props, self.children = name, props, children

    def find(self, name):
        return next((c for c in self.children if c.name == name), None)

    def all(self, name):
        return [c for c in self.children if c.name == name]


def _read_props(d: bytes, o: int, n: int):
    props = []
    for _ in range(n):
        t = chr(d[o])
        o += 1
        if t == "Y":
            props.append(struct.unpack_from("<h", d, o)[0]); o += 2
        elif t == "C":
            props.append(bool(d[o])); o += 1
        elif t == "I":
            props.append(struct.unpack_from("<i", d, o)[0]); o += 4
        elif t == "F":
            props.append(struct.unpack_from("<f", d, o)[0]); o += 4
        elif t == "D":
            props.append(struct.unpack_from("<d", d, o)[0]); o += 8
        elif t == "L":
            props.append(struct.unpack_from("<q", d, o)[0]); o += 8
        elif t in "fdlib":
            ln, enc, clen = struct.unpack_from("<III", d, o)
            o += 12
            raw = d[o:o + clen]
            o += clen
            if enc == 1:
                raw = zlib.decompress(raw)
            dt = {"f": "<f4", "d": "<f8", "l": "<i8", "i": "<i4", "b": "u1"}[t]
            props.append(np.frombuffer(raw, dtype=dt, count=ln))
        elif t in "SR":
            ln = struct.unpack_from("<I", d, o)[0]
            o += 4
            props.append(d[o:o + ln] if t == "R" else d[o:o + ln].decode("utf-8", "replace"))
            o += ln
        else:
            raise ValueError(f"FBX: unknown property type {t!r}")
    return props, o


def parse(data: bytes) -> Node:
    if data[:20] != b"Kaydara FBX Binary  ":
        raise ValueError("Only binary FBX is supported (export as FBX binary, OBJ or GLB)")
    version = struct.unpack_from("<I", data, 23)[0]
    wide = version >= 7500
    hdr = 25 if wide else 13

    def node(o):
        if wide:
            end, nprops, plen = struct.unpack_from("<QQQ", data, o)
            o += 24
        else:
            end, nprops, plen = struct.unpack_from("<III", data, o)
            o += 12
        if end == 0:
            return None, o + 1
        nl = data[o]
        name = data[o + 1:o + 1 + nl].decode("latin1")
        o += 1 + nl
        props, o2 = _read_props(data, o, nprops)
        o = o + plen
        children = []
        while o < end - hdr:
            c, o = node(o)
            if c is None:
                break
            children.append(c)
        return Node(name, props, children), end

    root, o = [], 27
    while o < len(data) - hdr:
        n, o2 = node(o)
        if n is None:
            break
        root.append(n)
        o = o2
    return Node("root", [], root)


def _p70(model: Node) -> dict:
    out = {}
    p = model.find("Properties70")
    if p:
        for c in p.all("P"):
            if c.props:
                out[c.props[0]] = c.props[4:]
    return out


def _euler(r, order=0):
    x, y, z = (math.radians(a) for a in r)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx      # eEulerXYZ: X first


def _mat(t=(0, 0, 0), r=(0, 0, 0), s=(1, 1, 1), pre=(0, 0, 0)):
    M = np.eye(4)
    M[:3, :3] = _euler(pre) @ _euler(r) @ np.diag(s)
    M[:3, 3] = t
    return M


def load(path: str):
    """Return (objects, up_axis, unit_cm) where objects = [(name, verts(n,3) world, faces, colour)]."""
    root = parse(open(path, "rb").read())
    up, unit = 1, 1.0
    gs = root.find("GlobalSettings")
    if gs:
        p = _p70(gs)
        up = int(p.get("UpAxis", [1])[0])
        unit = float(p.get("UnitScaleFactor", [1.0])[0])
    objs = root.find("Objects")
    if objs is None:
        raise ValueError("FBX: no objects")
    geoms, models, mats = {}, {}, {}
    for n in objs.children:
        if n.name == "Geometry" and n.find("Vertices") is not None:
            geoms[n.props[0]] = n
        elif n.name == "Model":
            models[n.props[0]] = n
        elif n.name == "Material":
            mats[n.props[0]] = n
    parent, geo_of, mat_of = {}, {}, {}
    conns = root.find("Connections")
    for c in (conns.all("C") if conns else []):
        if len(c.props) < 3 or c.props[0] != "OO":
            continue
        a, b = c.props[1], c.props[2]
        if a in geoms and b in models:
            geo_of.setdefault(b, []).append(a)
        elif a in models and b in models:
            parent[a] = b
        elif a in mats and b in models:
            mat_of.setdefault(b, []).append(a)

    local = {}
    for mid, m in models.items():
        p = _p70(m)
        local[mid] = (_mat(p.get("Lcl Translation", (0, 0, 0)), p.get("Lcl Rotation", (0, 0, 0)),
                           p.get("Lcl Scaling", (1, 1, 1)), p.get("PreRotation", (0, 0, 0))),
                      _mat(p.get("GeometricTranslation", (0, 0, 0)), p.get("GeometricRotation", (0, 0, 0)),
                           p.get("GeometricScaling", (1, 1, 1))))

    def world(mid, depth=0):
        M = local[mid][0]
        if mid in parent and depth < 64:
            return world(parent[mid], depth + 1) @ M
        return M

    def name_of(mid):
        return models[mid].props[1].split("\x00")[0]

    def path_names(mid):
        names = []
        while mid is not None and len(names) < 64:
            names.append(name_of(mid))
            mid = parent.get(mid)
        return names

    out = []
    for mid, gids in geo_of.items():
        W = world(mid) @ local[mid][1]
        colour = (160, 162, 170)
        for matid in mat_of.get(mid, []):
            mp = _p70(mats[matid])
            dc = mp.get("DiffuseColor") or mp.get("Diffuse")
            if dc and len(dc) >= 3:
                colour = tuple(int(max(0, min(1, float(x))) * 255) for x in dc[:3])
            break
        mat_names = [mats[i].props[1].split("\x00")[0] for i in mat_of.get(mid, [])]
        for gid in gids:
            g = geoms[gid]
            V = np.asarray(g.find("Vertices").props[0], dtype=float).reshape(-1, 3)
            V = (W @ np.c_[V, np.ones(len(V))].T).T[:, :3]
            idx = g.find("PolygonVertexIndex").props[0]
            faces, cur = [], []
            for i in idx:
                i = int(i)
                if i < 0:
                    cur.append(~i)
                    faces.append(cur)
                    cur = []
                else:
                    cur.append(i)
            out.append({"name": name_of(mid), "path": path_names(mid), "verts": V, "faces": faces,
                        "colour": colour, "materials": mat_names})
    return out, up, unit
