"""Truss models: turn a (heavy) truss mesh into a light tube skeleton.

A real truss model has thousands of polygons per segment, far too many to repeat
along every truss line. Each segment is analysed once:

* the main frame (chords + end plates) -> 4 chord tubes found from the cross-section
* every brace / diagonal -> one tube from its principal axis and radius

The result (segment lengths + tubes in metres) is cached in ~/.minidesk/cache and drawn
as thick lines, so the stage keeps the look of the real truss at full speed.
Expected input: one OBJ group per segment (e.g. 10 ft, 8 ft, 5 ft pieces), any orientation.
"""
from __future__ import annotations

import json
import os

import numpy as np

from .meshes import resolve

CACHE = os.path.join(os.path.expanduser("~"), ".minidesk", "cache")


def _unit_scale(width: float) -> float:
    if 10 <= width <= 14.5:        # inches (12" box truss)
        return 0.0254
    if 25 <= width <= 45:          # centimetres
        return 0.01
    if 200 <= width <= 450:        # millimetres
        return 0.001
    if 0.15 <= width <= 0.6:       # metres
        return 1.0
    return 0.30 / width


def _read_obj_groups(path: str) -> dict:
    verts, groups, cur = [], {}, "default"
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if ln.startswith("v "):
                t = ln.split()
                verts.append((float(t[1]), float(t[2]), float(t[3])))
            elif ln.startswith(("g ", "o ")):
                cur = ln.split(None, 1)[1].strip() or "default"
            elif ln.startswith("f "):
                idx = []
                for tok in ln.split()[1:]:
                    i = int(tok.split("/")[0])
                    idx.append(i - 1 if i > 0 else len(verts) + i)
                groups.setdefault(cur, []).append(idx)
    return {"V": np.array(verts, dtype=float), "groups": groups}


def _components(faces: list) -> list:
    par: dict = {}

    def find(a):
        par.setdefault(a, a)
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for f in faces:
        r = find(f[0])
        for i in f[1:]:
            q = find(i)
            if q != r:
                par[q] = r
    comp: dict = {}
    for f in faces:
        comp.setdefault(find(f[0]), set()).update(f)
    return [sorted(v) for v in comp.values()]


def analyse(path: str) -> dict:
    """Return {"width": m, "segments": [{"length": m, "chords": [...], "braces": [...]}]}.
    Tubes are (x0, y0, z0, x1, y1, z1, radius) with X along the truss, Y/Z centred."""
    data = _read_obj_groups(path) if path.lower().endswith(".obj") else _from_mesh(path)
    V = data["V"]
    segs, widths = [], []
    for name, faces in data["groups"].items():
        vids = sorted({i for f in faces for i in f})
        P = V[vids]
        ext = P.max(axis=0) - P.min(axis=0)
        main = int(np.argmax(ext))
        cross = [k for k in range(3) if k != main]
        length = float(ext[main])
        width = float(np.median(ext[cross]))
        if length < 1.8 * width:          # corner block / cube
            continue
        lo = P.min(axis=0)
        centre = (P.min(axis=0) + P.max(axis=0)) / 2
        widths.append(width)

        def to_local(Q):
            return np.c_[Q[:, main] - lo[main], Q[:, cross[0]] - centre[cross[0]], Q[:, cross[1]] - centre[cross[1]]]
        chords, braces = [], []
        for comp in _components(faces):
            Q = to_local(V[comp])
            span = Q[:, 0].max() - Q[:, 0].min()
            if span > 0.85 * length:          # main frame: 4 corner chords
                for sy in (-1, 1):
                    for sz in (-1, 1):
                        m = (Q[:, 1] * sy > width * 0.2) & (Q[:, 2] * sz > width * 0.2)
                        if m.sum() < 4:
                            continue
                        C = Q[m]
                        cy, cz = float(np.median(C[:, 1])), float(np.median(C[:, 2]))
                        r = float(min(width * 0.12, max(np.ptp(C[:, 1]), np.ptp(C[:, 2])) / 2))
                        chords.append((0.0, cy, cz, length, cy, cz, r))
                continue
            mu = Q.mean(axis=0)
            _u, _s, vt = np.linalg.svd(Q - mu, full_matrices=False)
            ax = vt[0]
            pr = (Q - mu) @ ax
            r = float(np.linalg.norm((Q - mu) - np.outer(pr, ax), axis=1).mean())
            a, b = mu + ax * pr.min(), mu + ax * pr.max()
            braces.append((*map(float, a), *map(float, b), r))
        segs.append({"length": length, "chords": chords, "braces": braces})
    if not segs:
        raise ValueError("No truss segments found (expect one group/object per straight segment)")
    width = float(np.median(widths))
    k = _unit_scale(width)

    def sc(t):
        return [round(x * k, 5) for x in t]
    out = {"width": width * k, "segments": []}
    for sgm in sorted(segs, key=lambda s: -s["length"]):
        out["segments"].append({"length": sgm["length"] * k, "chords": [sc(t) for t in sgm["chords"]],
                                "braces": [sc(t) for t in sgm["braces"]]})
    return out


def _from_mesh(path: str) -> dict:
    from .meshes import load_model
    m = load_model(path)
    verts, groups, off = [], {}, 0
    for name, p in m.parts.items():
        verts.extend(p.verts)
        for comp_i, f in enumerate(p.faces):
            groups.setdefault(name, []).append([off + i for i in f])
        off += len(p.verts)
    return {"V": np.array(verts, dtype=float), "groups": groups}


_mem: dict = {}


def load(model: str) -> dict | None:
    """Cached analysis of a truss model ('' / 'builtin' = None)."""
    if not model or model == "builtin":
        return None
    path = resolve(model)
    if not os.path.exists(path):
        return None
    st = os.stat(path)
    key = f"{os.path.basename(path)}-{st.st_size}-{int(st.st_mtime)}"
    if key in _mem:
        return _mem[key]
    cfile = os.path.join(CACHE, key + ".json")
    data = None
    try:
        with open(cfile, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        try:
            data = analyse(path)
            os.makedirs(CACHE, exist_ok=True)
            with open(cfile, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        except Exception:
            data = None
    _mem[key] = data
    return data


def tile(length: float, segments: list) -> list:
    """Choose segments to cover ``length``: list of (offset, segment)."""
    if not segments:
        return []
    segs = sorted(segments, key=lambda s: -s["length"])
    out, pos = [], 0.0
    while pos < length - 0.05 and len(out) < 200:
        rest = length - pos
        fit = [s for s in segs if s["length"] <= rest + 0.05]
        s = fit[0] if fit else segs[-1]
        out.append((pos, s))
        pos += s["length"]
    return out
