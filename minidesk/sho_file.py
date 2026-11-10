"""Read/modify/write CODE MINI 1000T ``.SHO`` files.

The file is edited *in place*: the original decompressed image is kept and only
the fields MiniDesk understands are changed, so everything else (cues, presets,
effects, console settings) stays byte-for-byte identical.  An unchanged show is
saved as an identical file.

Written back into the .SHO
    * fixture names, fixture type (from the console library), DMX address /
      universe, patch / unpatch, new fixtures of console library types
    * the console's per DMX channel ownership tables
    * group names, members and member order; new and deleted groups
    * playback and fixed playback names
    * header CRC32

Kept only in MiniDesk (companion file): stage positions, visual models,
effects, step contents/timing edits, user playbacks.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import tempfile
import time
import zlib
from dataclasses import dataclass, field

from . import sho_import as S
from .model import Show

NAME_MAX = 16          # conservative: console displays short names


@dataclass
class SaveReport:
    written: list[str] = field(default_factory=list)
    not_saved: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    verified: bool = False
    path: str = ""
    backup: str = ""

    def text(self) -> str:
        out = []
        if self.errors:
            out.append("ERRORS – file NOT saved:\n  " + "\n  ".join(self.errors))
            return "\n".join(out)
        out.append(f"Saved to console file: {self.path}")
        out.append("Verification: " + ("OK – file re-read, CRC valid, content matches"
                                       if self.verified else "FAILED"))
        if self.written:
            out.append(f"Changes written ({len(self.written)}):\n  " + "\n  ".join(self.written[:40])
                       + ("\n  …" if len(self.written) > 40 else ""))
        else:
            out.append("No console-relevant changes – file content unchanged.")
        if self.not_saved:
            out.append("Kept in MiniDesk only (the console file format has no place for these):\n  "
                       + "\n  ".join(self.not_saved[:20]))
        if self.backup:
            out.append(f"Backup of the previous file: {self.backup}")
        return "\n".join(out)


def _enc_name(name: str, length: int = 20) -> bytes:
    b = name.strip()[:NAME_MAX].encode("latin1", "replace")
    return b.ljust(length, b"\0")[:length]


def step_signature(show: Show) -> dict:
    """Snapshot of things that cannot be written back, to detect edits."""
    return {
        "playbacks": {f"{p.bank}:{p.slot}": json.dumps([s.to_json() for s in p.steps], sort_keys=True)
                      for p in show.playbacks if p.slot >= 0},
        "pb_meta": {f"{p.bank}:{p.slot}": [p.mode, p.speed, p.fade] for p in show.playbacks if p.slot >= 0},
        "user_pbs": len([p for p in show.playbacks if p.slot < 0]),
    }


class ShoDocument:
    def __init__(self, path: str, raw: bytes):
        self.path = path
        self.raw = raw
        self.data = bytearray(S.decompress(raw))
        self.signature: dict = {}

    @classmethod
    def open(cls, path: str) -> "ShoDocument":
        with open(path, "rb") as fh:
            return cls(path, fh.read())

    # ------------------------------------------------------------ container
    def stored_crc(self) -> int:
        return struct.unpack_from("<I", self.data, S.HDR_CRC)[0]

    def compute_crc(self) -> int:
        return zlib.crc32(bytes(self.data[0x40:])) & 0xFFFFFFFF

    def crc_ok(self) -> bool:
        return self.stored_crc() == self.compute_crc()

    def encode(self) -> bytes:
        struct.pack_into("<I", self.data, S.HDR_CRC, self.compute_crc())
        return struct.pack(">I", len(self.data)) + zlib.compress(bytes(self.data), 1)

    # -------------------------------------------------------------- helpers
    def _u16(self, o: int) -> int:
        return struct.unpack_from("<H", self.data, o)[0]

    def _put(self, o: int, b: bytes) -> bool:
        if bytes(self.data[o:o + len(b)]) != b:
            self.data[o:o + len(b)] = b
            return True
        return False

    def _put_name(self, o: int, length: int, name: str) -> bool:
        """Write a name only if it differs from what the console stored (ignores padding)."""
        if S._text(bytes(self.data[o:o + length])) == name.strip():
            return False
        return self._put(o, _enc_name(name, length))

    def _put16(self, o: int, v: int) -> bool:
        return self._put(o, struct.pack("<H", v))

    # ---------------------------------------------------------------- apply
    def validate(self, show: Show) -> list[str]:
        err = []
        used: dict[int, int] = {}
        for fx in show.fixtures:
            ft = show.types.get(fx.type_key)
            if ft is None:
                err.append(f"Fixture {fx.fid}: unknown type")
                continue
            if ft.lib_index < 0:
                err.append(f"Fixture {fx.fid} '{fx.name}': type '{ft.name}' is not in the console library "
                           "(create the profile on the console first, or use one of its fixture types)")
            if fx.patched:
                n = len(ft.channels)
                start = fx.universe * 512 + fx.address - 1
                if fx.universe > 3:
                    err.append(f"Fixture {fx.fid}: universe {fx.universe + 1} – the console has 4 universes")
                if fx.address + n - 1 > 512:
                    err.append(f"Fixture {fx.fid}: address {fx.address} + {n} channels crosses the universe end")
                for c in range(start, start + n):
                    if c in used:
                        err.append(f"Fixture {fx.fid} overlaps fixture {used[c]} at DMX "
                                   f"{c // 512 + 1}.{c % 512 + 1:03d}")
                        break
                    used[c] = fx.fid
        old = {i for i in range(S.MAX_FIXTURES) if self.data[S.FIX_TYPES + i] != 0xFF}
        have = {fx.slot for fx in show.fixtures if fx.slot >= 0}
        for i in sorted(old - have):
            err.append(f"Console fixture #{i + 1} was deleted – deleting fixtures is not supported "
                       "for console files, unpatch it instead (address 0)")
        slots = [fx.slot for fx in show.fixtures if fx.slot >= 0]
        if len(slots) != len(set(slots)):
            err.append("Two fixtures use the same console slot")
        new = [fx for fx in show.fixtures if fx.slot < 0]
        free = S.MAX_FIXTURES - len(have)
        if len(new) > free:
            err.append("Not enough free fixture slots in the console file")
        return err

    def apply(self, show: Show, rep: SaveReport) -> None:
        d = self.data
        # -- assign slots to new fixtures (prefer fid-1, like the console numbering)
        used = {fx.slot for fx in show.fixtures if fx.slot >= 0}
        for fx in show.fixtures:
            if fx.slot < 0:
                cand = fx.fid - 1
                if not (0 <= cand < S.MAX_FIXTURES) or cand in used or d[S.FIX_TYPES + cand] != 0xFF:
                    cand = next(i for i in range(S.MAX_FIXTURES)
                                if i not in used and d[S.FIX_TYPES + i] == 0xFF)
                fx.slot = cand
                used.add(cand)
                rep.written.append(f"New fixture {fx.fid} '{fx.name}' -> console slot {cand + 1}")
        # -- fixtures
        patch_changed = False
        for fx in show.fixtures:
            i = fx.slot
            ft = show.types[fx.type_key]
            n = len(ft.channels)
            tag = f"Fixture {i + 1} '{fx.name}'"
            if self._put(S.FIX_TYPES + i, bytes([ft.lib_index])):
                rep.written.append(f"{tag}: type -> {ft.name}")
                patch_changed = True
            if self._put(S.FIX_COUNTS + i, bytes([n])):
                patch_changed = True
            self._put(S.FIX_EXISTS + i, b"\xff")
            no = S.FIX_NAMES + i * S.FIX_NAME_LEN
            placeholder = not S._text(bytes(d[no:no + S.FIX_NAME_LEN])) and fx.name == ft.name
            if not placeholder and self._put_name(no, S.FIX_NAME_LEN, fx.name):
                rep.written.append(f"{tag}: name")
            addr = fx.universe * 512 + fx.address - 1 if fx.patched else 0xFFFF
            old = self._u16(S.PATCH_ADDR + i * S.PATCH_STRIDE)
            if old != addr:
                self._put16(S.PATCH_ADDR + i * S.PATCH_STRIDE, addr)
                rep.written.append(f"{tag}: " + (f"address -> {fx.universe + 1}.{fx.address:03d}"
                                                 if fx.patched else "unpatched"))
                patch_changed = True
            self._put(S.FIX_PATCHED + i, b"\xff" if fx.patched else b"\x00")
        # -- per DMX channel tables
        if patch_changed:
            owner = [0xFFFF] * S.DMX_CHANNELS
            chidx = {}
            for fx in show.fixtures:
                if fx.patched:
                    start = fx.universe * 512 + fx.address - 1
                    for c in range(len(show.types[fx.type_key].channels)):
                        owner[start + c] = fx.slot
                        chidx[start + c] = c
            for c in range(S.DMX_CHANNELS):
                self._put16(S.DMX_OWNER + 2 * c, owner[c])
                if c in chidx:
                    self._put(S.DMX_CHIDX + c, bytes([chidx[c]]))
        # -- groups
        fid_slot = {fx.fid: fx.slot for fx in show.fixtures}
        old_groups = {g for g in range(S.MAX_GROUPS) if self._group_used(g)}
        taken = {g.slot for g in show.groups if g.slot >= 0}
        for g in show.groups:
            if g.slot < 0:
                g.slot = next(k for k in range(S.MAX_GROUPS) if k not in taken and k not in old_groups)
                taken.add(g.slot)
                rep.written.append(f"New group {g.slot + 1} '{g.name}'")
            self._write_group(g.slot, g.name, [fid_slot[f] for f in g.fixtures if f in fid_slot], rep)
        for k in sorted(old_groups - taken):
            self._write_group(k, "", [], rep)
            rep.written.append(f"Group {k + 1} deleted")
        # -- playback names
        for pb in show.playbacks:
            if pb.slot < 0:
                continue
            table = S.FIXED_TABLE if pb.bank == "Fixed" else S.PB_TABLE
            o = table + pb.slot * S.PB_STRIDE
            if self._put_name(o + 0x2C, 20, pb.name):
                rep.written.append(f"{pb.bank} playback {pb.slot + 1}: name -> {pb.name}")
        # -- preset names
        for pr in getattr(show, "presets", []):
            if pr.slot >= 0 and self._put_name(S.PRESET_TABLE + pr.slot * S.PB_STRIDE + 0x2C, 20, pr.name):
                rep.written.append(f"Preset {pr.slot + 1}: name -> {pr.name}")

    def _group_used(self, g: int) -> bool:
        no = S.GROUP_NAMES + g * S.GROUP_NAME_LEN
        mo = S.GROUP_MASKS + g * S.GROUP_MASK_STRIDE
        return any(self.data[no:no + S.GROUP_NAME_LEN]) or any(self.data[mo:mo + S.MAX_FIXTURES])

    def _write_group(self, g: int, name: str, members: list[int], rep: SaveReport) -> None:
        tag = f"Group {g + 1} '{name}'"
        no = S.GROUP_NAMES + g * S.GROUP_NAME_LEN
        if name == f"Group {g + 1}" and not S._text(bytes(self.data[no:no + S.GROUP_NAME_LEN])):
            name = ""          # importer placeholder for an unnamed console group
        if self._put_name(no, S.GROUP_NAME_LEN, name) and name:
            rep.written.append(f"{tag}: name")
        mask = bytearray(S.MAX_FIXTURES)
        for m in members:
            mask[m] = 0xFF
        changed = self._put(S.GROUP_MASKS + g * S.GROUP_MASK_STRIDE, bytes(mask))
        cur = S.ShoReader(self.data).group_list(g)
        if cur != members:
            lo = S.GROUP_LISTS + g * S.GROUP_LIST_STRIDE
            lst = b"".join(struct.pack("<H", m) for m in members)
            self.data[lo:lo + S.GROUP_LIST_STRIDE] = lst.ljust(S.GROUP_LIST_STRIDE, b"\xff")
            changed = True
        if changed and name:
            rep.written.append(f"{tag}: members ({len(members)})")

    # ------------------------------------------------------------------ save
    def unsupported_changes(self, show: Show) -> list[str]:
        notes = []
        sig = step_signature(show)
        old = self.signature or {}
        for k, v in sig["playbacks"].items():
            if old.get("playbacks", {}).get(k) not in (None, v):
                notes.append(f"Step contents / effects of playback {k}")
        for k, v in sig["pb_meta"].items():
            if old.get("pb_meta", {}).get(k) not in (None, v):
                notes.append(f"Mode / speed / fade of playback {k}")
        if sig["user_pbs"]:
            notes.append(f"{sig['user_pbs']} playback(s) created in MiniDesk")
        notes.append("Stage positions and fixture visual models")
        return notes

    def save(self, show: Show, path: str | None = None, backup_dir: str | None = None) -> SaveReport:
        rep = SaveReport(path=path or self.path)
        rep.errors = self.validate(show)
        if rep.errors:
            return rep
        before = bytes(self.data)
        try:
            self.apply(show, rep)
        except Exception as e:        # never leave a half-modified image behind
            self.data[:] = before
            rep.errors.append(f"Internal error while writing: {e}")
            return rep
        blob = self.encode()
        target = rep.path
        if os.path.exists(target) and backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            base = os.path.basename(target)
            rep.backup = os.path.join(backup_dir, f"{time.strftime('%Y%m%d-%H%M%S')}-{base}")
            shutil.copy2(target, rep.backup)
        folder = os.path.dirname(os.path.abspath(target))
        fd, tmp = tempfile.mkstemp(prefix=".md-", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            rep.errors.append(f"Could not write {target}: {e}")
            return rep
        rep.verified = self.verify(target, show)
        self.path, self.raw = target, blob
        rep.not_saved = self.unsupported_changes(show)
        return rep

    def verify(self, path: str, show: Show) -> bool:
        """Re-read the written file and compare it with the model."""
        with open(path, "rb") as fh:
            raw = fh.read()
        data = S.decompress(raw)
        if data != bytes(self.data):
            return False
        if struct.unpack_from("<I", data, S.HDR_CRC)[0] != zlib.crc32(data[0x40:]) & 0xFFFFFFFF:
            return False
        rd = S.ShoReader(data)
        fx_file = {i: (name, t, addr) for i, name, t, addr in rd.fixtures()}
        for fx in show.fixtures:
            ft = show.types[fx.type_key]
            addr = fx.universe * 512 + fx.address - 1 if fx.patched else -1
            got = fx_file.get(fx.slot)
            if got is None or got[1:] != (ft.lib_index, addr):
                return False
            if got[0] not in (fx.name.strip(), fx.name.strip()[:NAME_MAX]) and not (got[0] == "" and fx.name == ft.name):
                return False
        g_file = {g: (n, m) for g, n, m in rd.groups()}
        fid_slot = {fx.fid: fx.slot for fx in show.fixtures}
        for g in show.groups:
            name, members = g_file.get(g.slot, ("", []))
            if members != [fid_slot[f] for f in g.fixtures if f in fid_slot]:
                return False
            if g.name.strip() and name not in (g.name.strip(), g.name.strip()[:NAME_MAX], f"Group {g.slot + 1}"):
                return False
        return True
