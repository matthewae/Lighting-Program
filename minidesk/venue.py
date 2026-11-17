"""Venue layout presets: the real rig of a known hall.

GMS hall (taken from the venue photos):

* back wall with a grey projection screen (about 10 m x 3.8 m) right behind the stage
* BACK bar  – black pipe about 0.5 m in front of the wall, just above the screen:
      PAR PAR MH STRB MH PAR | PAR MH STRB MH PAR PAR      (PAR BELAKANG, BEAM BEL, STRB ATAS)
* FRONT bar – black pipe one layer further downstage:
      PAR MH PAR MH PAR PAR | PAR PAR MH PAR MH PAR        (PAR DEPAN, BEAM ATAS)
* two black box-truss towers left/right of the screen, strobe on top and two PARs below
                                                           (STRB TOWER, PAR TOWER)
* FOH pipe above the audience with 10 fresnels aimed at the stage (ALL FRESNEL)

X positions were measured on the front photos with the screen width as the scale, then
made symmetric.  Coordinates: x = left(-)/right(+) of centre, y = metres from the stage
front edge towards the back wall (negative = above the audience), z = height.
"""
from __future__ import annotations

import math

from .model import Fixture, Show

GMS = "GMS hall"

# stage
STAGE_W, STAGE_D, STAGE_H = 14.0, 6.0, 6.0
WALL_Y = STAGE_D + 0.5                       # the visualizer's back wall plane
SCREEN = {"width": 10.0, "height": 3.8, "z": 0.0, "y": WALL_Y - 0.04}

# rig positions (metres)
BACK_Y, BACK_Z = 6.0, 4.2
FRONT_Y, FRONT_Z = 4.8, 4.55
TOWER_X, TOWER_Y, TOWER_TOP = 5.95, 6.1, 4.0
FOH_Y, FOH_Z = -4.0, 6.2

BACK_PAR_X = [-4.85, -3.85, -0.55, 0.55, 3.85, 4.85]
BACK_MH_X = [-3.2, -1.5, 1.5, 3.2]
BACK_STROBE_X = [-2.35, 2.35]
FRONT_PAR_X = [-5.1, -3.65, -2.1, -0.86, 0.86, 2.1, 3.65, 5.1]
FRONT_MH_X = [-4.35, -2.8, 2.8, 4.35]
FOH_X = [round(-5.85 + 1.3 * i, 2) for i in range(10)]

# console patches that are not lights in this hall
NOT_IN_RIG = ("DSK-1500VS",)

REQUIRED = {"PAR BELAKANG": 6, "PAR DEPAN": 8, "BEAM BEL": 4, "BEAM ATAS": 4,
            "STRB ATAS": 2, "STRB TOWER": 2, "PAR TOWER": 4}


def aim_at(f: Fixture, tx: float, ty: float, tz: float) -> None:
    """Point a fixed fixture at a target (sets rot = yaw and aim = tilt from down/up)."""
    dx, dy, dz = tx - f.x, ty - f.y, tz - f.z
    n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    dx, dy, dz = dx / n, dy / n, dz / n
    floor = f.mount == "floor"
    f.aim = round(math.degrees(math.acos(max(-1.0, min(1.0, dz if floor else -dz)))), 1)
    f.rot = round(math.degrees(math.atan2(dx, -dy)), 1) if math.hypot(dx, dy) > 1e-6 else 0.0


def _group(show: Show, *names: str) -> list[int]:
    want = {n.upper() for n in names}
    for g in show.groups:
        if g.name.strip().upper() in want:
            return sorted(g.fixtures)
    return []


def matches_gms(show: Show) -> bool:
    for name, n in REQUIRED.items():
        if len(_group(show, name)) != n:
            return False
    return True


def rigging_gms() -> list[dict]:
    return [
        {"kind": "pipe", "name": "Back bar (near the wall)", "colour": "black",
         "a": [-5.6, BACK_Y, BACK_Z + 0.05], "b": [5.6, BACK_Y, BACK_Z + 0.05]},
        {"kind": "pipe", "name": "Front bar", "colour": "black",
         "a": [-5.9, FRONT_Y, FRONT_Z + 0.05], "b": [5.9, FRONT_Y, FRONT_Z + 0.05]},
        {"kind": "pipe", "name": "FOH bar (fresnels)", "colour": "black",
         "a": [-6.5, FOH_Y, FOH_Z + 0.05], "b": [6.5, FOH_Y, FOH_Z + 0.05]},
        {"kind": "truss", "name": "Tower left", "colour": "black",
         "a": [-TOWER_X, TOWER_Y, 0.0], "b": [-TOWER_X, TOWER_Y, TOWER_TOP]},
        {"kind": "truss", "name": "Tower right", "colour": "black",
         "a": [TOWER_X, TOWER_Y, 0.0], "b": [TOWER_X, TOWER_Y, TOWER_TOP]},
    ]


def apply_gms(show: Show) -> list[str]:
    """Place every fixture like the real GMS hall rig.  Returns notes about guesses."""
    notes: list[str] = []
    show.stage_width, show.stage_depth, show.stage_height = STAGE_W, STAGE_D, STAGE_H
    show.screen = dict(SCREEN)
    show.rigging = rigging_gms()
    show.venue = GMS
    placed: set[int] = set()

    def put(fid, x, y, z, mount="hang", target=None, rot=0.0, aim=0.0):
        f = show.fixture(fid)
        if f is None:
            return
        f.x, f.y, f.z, f.mount = x, y, z, mount
        if target is not None:
            aim_at(f, *target)
        else:
            f.rot, f.aim = rot, aim
        placed.add(fid)

    def row(fids, xs, y, z, target=None, **kw):
        for fid, x in zip(fids, xs):
            put(fid, x, y, z, target=target(x) if target else None, **kw)

    # back bar (layer closest to the wall)
    row(_group(show, "PAR BELAKANG"), BACK_PAR_X, BACK_Y, BACK_Z, target=lambda x: (x, 2.5, 0.0))
    row(_group(show, "BEAM BEL", "BEAM BELAKANG"), BACK_MH_X, BACK_Y, BACK_Z)
    row(_group(show, "STRB ATAS"), BACK_STROBE_X, BACK_Y, BACK_Z, target=lambda x: (x, -3.0, 1.5))
    # front bar (one layer downstage)
    row(_group(show, "PAR DEPAN"), FRONT_PAR_X, FRONT_Y, FRONT_Z, target=lambda x: (x, 2.0, 0.0))
    row(_group(show, "BEAM ATAS", "BEAM DEPAN"), FRONT_MH_X, FRONT_Y, FRONT_Z)
    # towers: strobe on the front face at the top, two PARs on the inner side below it
    strobes = _group(show, "STRB TOWER")
    for fid, side in zip(strobes, (-1, 1)):
        put(fid, side * TOWER_X, TOWER_Y - 0.22, 3.35, target=(side * 3.0, -4.0, 2.0))
    pars = _group(show, "PAR TOWER")
    half = len(pars) // 2
    for i, fid in enumerate(pars):
        side = -1 if i < half else 1
        upper = (i % half) == 0 if half else True
        x = side * (TOWER_X - 0.3)
        if upper:
            put(fid, x, TOWER_Y - 0.1, 3.4, target=(-side * 1.5, 2.5, 1.2))   # cross light
        else:
            put(fid, x, TOWER_Y - 0.1, 2.75, target=(-side * 0.5, 3.5, 1.0))
    # FOH fresnels above the audience, aimed at the stage
    fres = _group(show, "ALL FRESNEL") or sorted(f.fid for f in show.fixtures
                                                 if show.ftype(f).kind == "fresnel")
    row(fres, FOH_X, FOH_Y, FOH_Z, target=lambda x: (x * 0.8, 2.2, 1.6))

    # everything else is not part of the visible rig
    others = [f for f in show.fixtures if f.fid not in placed]
    fog_spots = [(-5.4, 6.2), (5.4, 6.2), (-4.6, 6.2), (4.6, 6.2)]
    uplight_x = [-3.75, -1.25, 1.25, 3.75, -4.6, 4.6]
    store, hidden = 0, []
    for f in show.fixtures:
        f.hidden = False
    for f in others:
        ft = show.ftype(f)
        if not f.patched or any(n in ft.name.upper() for n in NOT_IN_RIG):
            # unpatched console entries and patches that are not lights in this hall (the units at
            # the stage edge in the photos are monitor speakers) – hidden in the stage view only,
            # the console patch itself is left untouched
            col, r = store % 3, store // 3
            put(f.fid, -STAGE_W / 2 - 1.0 - 0.8 * col, 0.4 + 0.8 * r, 0.0, mount="floor", rot=0.0, aim=0.0)
            store += 1
            f.hidden = True
            hidden.append(f.fid)
            continue
        if ft.kind == "fog" and fog_spots:
            x, y = fog_spots.pop(0)
            put(f.fid, x, y, 0.0, mount="floor", rot=180.0, aim=0.0)
        elif not ft.is_moving and uplight_x:
            x = uplight_x.pop(0)
            put(f.fid, x, WALL_Y - 0.3, 0.0, mount="floor", target=(x, WALL_Y, 3.0))
            notes.append(f"#{f.fid} {f.name}: placed as an uplight on the screen (not visible in the photos)")
        else:
            put(f.fid, 0.0, 3.0, 0.0, mount="floor", rot=0.0, aim=0.0)
            notes.append(f"#{f.fid} {f.name}: position unknown, placed centre stage")
    if hidden:
        notes.append("Hidden in the stage view (not part of the rig, patch unchanged): "
                     + ", ".join(f"#{i}" for i in hidden))
    return notes


VENUES = {GMS: apply_gms}


def auto_apply(show: Show) -> bool:
    """Apply a venue preset when the show's groups identify the venue."""
    if matches_gms(show):
        apply_gms(show)
        return True
    return False
