"""Companion project data for console (.SHO) shows.

The console file has no place for stage positions, 3D models, effects or
MiniDesk-only cue edits.  Those are stored in a small JSON file in the user's
profile (``~/.minidesk/projects``) so the USB stick only contains the console
file, and are re-applied when the same .SHO is opened again.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict

from .model import OutputConfig, Playback, Preset, Show

HOME = os.path.join(os.path.expanduser("~"), ".minidesk")
PROJECTS = os.path.join(HOME, "projects")
BACKUPS = os.path.join(HOME, "backups")


def _key(show: Show) -> str:
    base = os.path.basename(show.source_path or show.name).upper()
    return base.replace(" ", "_")


def path_for(show: Show) -> str:
    return os.path.join(PROJECTS, _key(show) + ".json")


def _steps_hash(pb: Playback) -> str:
    return hashlib.sha1(json.dumps([s.to_json() for s in pb.steps], sort_keys=True).encode()).hexdigest()


def remember_imported(show: Show) -> None:
    """Call right after import: remembers the console's own steps per playback."""
    show.console_info["_step_hash"] = {f"{p.bank}:{p.slot}": _steps_hash(p) for p in show.playbacks if p.slot >= 0}
    show.console_info["_preset_slots"] = [p.slot for p in show.presets if p.slot >= 0]


def save(show: Show) -> str:
    os.makedirs(PROJECTS, exist_ok=True)
    base_hash = show.console_info.get("_step_hash", {})
    data = {
        "stage": [show.stage_width, show.stage_depth, show.stage_height],
        "truss_model": show.truss_model,
        "positions": {str(f.slot if f.slot >= 0 else -f.fid): [f.x, f.y, f.z, f.mount, f.rot, f.aim]
                      for f in show.fixtures},
        "types": {k: {"kind": t.kind, "beam_angle": t.beam_angle, "pan_range": t.pan_range,
                      "tilt_range": t.tilt_range, "model": t.model, "model_scale": t.model_scale,
                      "channels": [[c.attr, c.default, c.ranges] for c in t.channels]}
                  for k, t in show.types.items()},
        "output": asdict(show.output),
        "playbacks": {},
        "user_playbacks": [p.to_json() for p in show.playbacks if p.slot < 0],
        "user_presets": [p.to_json() for p in show.presets if p.slot < 0],
        "console_presets": {str(p.slot): {"category": p.category} for p in show.presets if p.slot >= 0},
        "deleted_presets": [s for s in show.console_info.get("_preset_slots", [])
                            if s not in {p.slot for p in show.presets}],
    }
    for p in show.playbacks:
        if p.slot < 0:
            continue
        key = f"{p.bank}:{p.slot}"
        entry = {"mode": p.mode, "speed": p.speed, "fade": p.fade}
        if base_hash.get(key) != _steps_hash(p):          # edited in MiniDesk
            entry["base"] = base_hash.get(key)
            entry["steps"] = [s.to_json() for s in p.steps]
        data["playbacks"][key] = entry
    path = path_for(show)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)
    return path


def load(show: Show) -> bool:
    """Apply companion data to a freshly imported console show."""
    path = path_for(show)
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    from .model import Step
    st = data.get("stage")
    if st:
        show.stage_width, show.stage_depth, show.stage_height = st
    show.truss_model = data.get("truss_model", show.truss_model)
    pos = data.get("positions", {})
    for f in show.fixtures:
        v = pos.get(str(f.slot if f.slot >= 0 else -f.fid))
        if v:
            f.x, f.y, f.z, f.mount, f.rot, f.aim = v
    for k, t in data.get("types", {}).items():
        ft = show.types.get(k)
        if not ft:
            continue
        ft.kind, ft.beam_angle = t.get("kind", ft.kind), t.get("beam_angle", ft.beam_angle)
        ft.pan_range, ft.tilt_range = t.get("pan_range", ft.pan_range), t.get("tilt_range", ft.tilt_range)
        from .meshes import BUILTIN, resolve
        if t.get("model") and (t["model"] in BUILTIN or os.path.exists(resolve(t["model"]))):
            ft.model = t["model"]
        ft.model_scale = t.get("model_scale", ft.model_scale)
        chans = t.get("channels", [])
        if len(chans) == len(ft.channels):
            for c, row in zip(ft.channels, chans):
                c.attr, c.default = row[0], row[1]
                if len(row) > 2:
                    c.ranges = row[2] or []
    if "output" in data:
        show.output = OutputConfig(**{k: v for k, v in data["output"].items()
                                      if k in OutputConfig.__dataclass_fields__})
    base_hash = show.console_info.get("_step_hash", {})
    for p in show.playbacks:
        e = data.get("playbacks", {}).get(f"{p.bank}:{p.slot}")
        if not e:
            continue
        p.mode, p.speed, p.fade = e.get("mode", p.mode), e.get("speed", p.speed), e.get("fade", p.fade)
        # only re-apply edited steps if the console's cues did not change since
        if "steps" in e and e.get("base") == base_hash.get(f"{p.bank}:{p.slot}"):
            p.steps = [Step.from_json(s) for s in e["steps"]]
    meta = data.get("console_presets", {})
    gone = set(data.get("deleted_presets", []))
    show.presets = [p for p in show.presets if p.slot not in gone]
    for p in show.presets:
        if str(p.slot) in meta:
            p.category = meta[str(p.slot)].get("category", p.category)
    show.presets += [Preset.from_json(d) for d in data.get("user_presets", [])]
    num = max((p.number for p in show.playbacks), default=0)
    for d in data.get("user_playbacks", []):
        pb = Playback.from_json(d)
        if any(p.number == pb.number for p in show.playbacks):
            num += 1
            pb.number = num
        show.playbacks.append(pb)
    return True
