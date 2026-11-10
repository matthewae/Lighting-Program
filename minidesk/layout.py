"""Automatic stage layout for imported fixtures.

The console file has no positions, so fixtures are placed on virtual trusses
using the group names (DEPAN/FRONT, BELAKANG/BACK, TENGAH/MID, ATAS/TOP,
TOWER/RIG, ...).  Users can drag fixtures afterwards in the top view.
"""
from __future__ import annotations

from .model import Show

ROW_RULES = [
    (("depan", "front", "dpn", "foh"), "front"),
    (("belakang", "back", "bel", "blk", "rear"), "back"),
    (("tengah", "mid", "center", "centre"), "mid"),
    (("atas", "top", "upper"), "top"),
    (("tower", "rig", "side", "samping", "kiri", "kanan"), "tower"),
    (("floor", "lantai", "bawah", "hazer", "haze", "fog", "smoke"), "floor"),
]


def _row_kind(name: str) -> str | None:
    n = name.lower()
    for keys, kind in ROW_RULES:
        if any(k in n.split() or k in n for k in keys):
            return kind
    return None


def auto_layout(show: Show) -> None:
    W, D = show.stage_width, show.stage_depth
    assigned: dict[int, str] = {}
    rows: dict[str, list[int]] = {}

    # smallest non-"ALL" group wins
    groups = sorted((g for g in show.groups if g.fixtures and not g.name.lower().startswith("all")),
                    key=lambda g: len(g.fixtures))
    for g in groups:
        for fid in g.fixtures:
            if fid not in assigned:
                assigned[fid] = g.name
                rows.setdefault(g.name, []).append(fid)
    for f in show.fixtures:
        if f.fid not in assigned:
            kind = show.ftype(f).kind
            key = "floor" if kind == "fog" else f"type:{kind}"
            assigned[f.fid] = key
            rows.setdefault(key, []).append(f.fid)

    used_levels: dict[tuple[float, float], int] = {}
    seq = 0
    for rname, fids in rows.items():
        fids.sort()
        kind = "floor" if rname == "floor" else _row_kind(rname)
        if kind is None and rname.startswith("type:"):
            kind = {"type:moving": "mid", "type:strobe": "top", "type:fresnel": "front"}.get(rname)
        mount = "hang"
        if kind == "front":
            y, z = 1.0, 5.5
        elif kind == "back":
            y, z = D - 0.6, 5.5
        elif kind == "mid":
            y, z = D / 2, 6.0
        elif kind == "top":
            y, z = D - 1.8, 6.5
        elif kind == "floor":
            y, z, mount = D - 0.4, 0.25, "floor"
        elif kind == "tower":
            half = (len(fids) + 1) // 2
            for i, fid in enumerate(fids):
                f = show.fixture(fid)
                side = -1 if i < half else 1
                k = i if i < half else i - half
                f.x, f.y, f.z, f.mount = side * (W / 2 + 0.3), D * 0.55, 1.5 + k * 1.0, "hang"
                f.rot, f.aim = -side * 90.0, 70.0
            continue
        else:
            y, z = 2.5 + seq * 1.2, 5.0
            seq += 1
        lvl = (round(y, 1), round(z, 1))
        n_same = used_levels.get(lvl, 0)
        used_levels[lvl] = n_same + 1
        y = min(D - 0.2, y + 0.6 * n_same) if kind != "back" else max(0.5, y - 0.6 * n_same)
        n = len(fids)
        span = W * 0.85
        for i, fid in enumerate(fids):
            f = show.fixture(fid)
            f.x = 0.0 if n == 1 else -span / 2 + span * i / (n - 1)
            f.y, f.z, f.mount = y, z, mount
            f.rot = 180.0 if kind == "front" else 0.0     # front truss lights the stage
            f.aim = 10.0 if mount == "floor" else (40.0 if kind == "front" else 25.0)
            if kind == "floor" and n > 1:
                f.x = -W / 2 + 0.8 + (W - 1.6) * i / (n - 1)
