"""Importer for CODE MINI 1000T / MINI 1000T PRO show files (``*.SHO``).

The console stores its show as a Qt ``qCompress`` blob: a 4 byte big-endian
uncompressed length followed by a zlib stream.  The decompressed image starts
with the magic ``SHOWMINI1000`` and is a fixed-layout memory dump.  The
offsets below were worked out from real show files; everything is read-only,
the original file is never modified.

What is imported
----------------
* console network settings (IP / netmask) -> used as Art-Net hint
* fixture library (name, manufacturer, channel names, wheel/slot table)
* patch: fixture name, type, DMX address
* groups (names and members)
* playbacks and fixed playbacks (names, default speed) with their steps
  (beta: step contents are decoded from the console's block heap; verify
  important cues against the console using Art-Net input)
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

from .model import Channel, Fixture, FixtureType, Group, Playback, Show, Step

MAGIC = b"SHOWMINI1000"

# --- layout constants (offsets in the decompressed image) -------------------
NET_IP = 0x1520
LIB_FIRST = 0x1571            # name of the first library entry
LIB_STRIDE = 0x8B3
LIB_END = 0x6E000
LIB_NAME_LEN, LIB_MAN_LEN = 20, 14
LIB_CHCOUNT = 34              # relative to name
LIB_SLOTS = 0x203             # 40 x (coarse, fine) channel numbers, 1 based
LIB_NSLOTS = 40
LIB_CHNAMES = 0x4D3           # 12 chars per channel name
LIB_CHNAME_LEN = 12
LIB_MAXCH = 40

GROUP_MASKS = 0x6E449         # 512 bytes per group, one byte per fixture
GROUP_MASK_STRIDE = 0x200
GROUP_NAMES = 0xA0449
GROUP_NAME_LEN = 20
MAX_GROUPS = 400             # mask/name/list tables each hold 400 entries
GROUP_LISTS = 0x515E68        # u16 fixture order list per group, 0xFFFF terminated
GROUP_LIST_STRIDE = 0x400
FIX_COUNTS = 0xD4B89          # channel count per fixture
FIX_EXISTS = 0xD4D89          # 0xFF = slot used
FIX_PATCHED = 0xA2389         # 0xFF = fixture patched
DMX_CHIDX = 0xD7F8C           # per DMX channel: channel number inside fixture
DMX_OWNER = 0xD878C           # per DMX channel: u16 fixture index (0xFFFF = free)
DMX_CHANNELS = 2048           # 4 universes
HDR_CRC = 0x3C                # CRC32 of data[0x40:]

PATCH_ADDR = 0xA2589          # u16 address (0 based), stride 0x190
PATCH_STRIDE = 0x190
FIX_NAMES = 0xD4F89
FIX_NAME_LEN = 20
FIX_TYPES = 0xD7789           # one byte per fixture, 0xFF = empty
MAX_FIXTURES = 512

PB_TABLE = 0xD9C60            # 64 byte playback records
PB_COUNT = 600
FIXED_TABLE = 0xEFA60
FIXED_COUNT = 300
PB_STRIDE = 0x40

STEP_BASE = 0x115E5E          # start of the 0xC0 byte block heap
STEP_BLOCK = 0xC0
STEP_HEAP_END = 0x20E000
HDR_SIG = bytes.fromhex("01000100000000ff")

CODE_A, CODE_B, PAGES = 0x191, 0x1A5, 20   # wheel A/B codes, 20 pages


class ShoFormatError(ValueError):
    pass


@dataclass
class LibEntry:
    name: str
    manufacturer: str
    channel_names: list[str]
    slots: list[tuple[int, int]]          # per wheel slot: (coarse ch, fine ch), 1 based


@dataclass
class ImportReport:
    fixtures: int = 0
    types: int = 0
    groups: int = 0
    playbacks: int = 0
    steps: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        s = (f"{self.types} fixture types, {self.fixtures} fixtures, {self.groups} groups, "
             f"{self.playbacks} playbacks, {self.steps} steps")
        if self.warnings:
            s += "\n" + "\n".join(self.warnings[:20])
        return s


def decompress(raw: bytes) -> bytes:
    if raw[:12] == MAGIC:
        return raw
    if len(raw) < 8:
        raise ShoFormatError("File too small")
    size = struct.unpack(">I", raw[:4])[0]
    try:
        data = zlib.decompress(raw[4:])
    except zlib.error as e:
        raise ShoFormatError(f"Not a MINI 1000 show file (zlib: {e})") from e
    if len(data) != size:
        raise ShoFormatError("Decompressed size mismatch")
    if data[:12] != MAGIC:
        raise ShoFormatError("Missing SHOWMINI1000 signature")
    return data


def _text(b: bytes) -> str:
    return b.split(b"\0")[0].decode("latin1").strip()


def _u16(d: bytes, o: int) -> int:
    return struct.unpack_from("<H", d, o)[0]


class ShoReader:
    def __init__(self, data: bytes):
        self.d = data

    # ---------------------------------------------------------------- basics
    def network(self) -> dict:
        d = self.d
        ip = ".".join(str(b) for b in d[NET_IP:NET_IP + 4])
        mask = ".".join(str(b) for b in d[NET_IP + 4:NET_IP + 8])
        return {"ip": ip, "netmask": mask}

    def library(self) -> list[LibEntry | None]:
        d, out = self.d, []
        o = LIB_FIRST
        while o + LIB_STRIDE <= LIB_END:
            name = _text(d[o:o + LIB_NAME_LEN])
            if not name or not name.isprintable():
                out.append(None)
                o += LIB_STRIDE
                continue
            man = _text(d[o + LIB_NAME_LEN:o + LIB_NAME_LEN + LIB_MAN_LEN])
            n = d[o + LIB_CHCOUNT]
            n = max(1, min(n, LIB_MAXCH))
            names = []
            for i in range(n):
                p = o + LIB_CHNAMES + i * LIB_CHNAME_LEN
                names.append(_text(d[p:p + LIB_CHNAME_LEN]))
            slots = [(d[o + LIB_SLOTS + 2 * i], d[o + LIB_SLOTS + 2 * i + 1]) for i in range(LIB_NSLOTS)]
            out.append(LibEntry(name, man, names, slots))
            o += LIB_STRIDE
        # trim trailing empty entries
        while out and out[-1] is None:
            out.pop()
        return out

    def fixtures(self) -> list[tuple[int, str, int, int]]:
        """Return (index, name, type index, 0 based address or -1)."""
        d, out = self.d, []
        for i in range(MAX_FIXTURES):
            t = d[FIX_TYPES + i]
            if t == 0xFF:
                continue
            name = _text(d[FIX_NAMES + i * FIX_NAME_LEN:FIX_NAMES + (i + 1) * FIX_NAME_LEN])
            addr = _u16(d, PATCH_ADDR + i * PATCH_STRIDE)
            out.append((i, name, t, -1 if addr == 0xFFFF else addr))
        return out

    def group_list(self, g: int) -> list[int]:
        o = GROUP_LISTS + g * GROUP_LIST_STRIDE
        out = []
        for k in range(MAX_FIXTURES):
            v = _u16(self.d, o + 2 * k)
            if v == 0xFFFF:
                break
            out.append(v)
        return out

    def groups(self) -> list[tuple[int, str, list[int]]]:
        """Return (slot, name, member fixture indices in console order)."""
        d, out = self.d, []
        for g in range(MAX_GROUPS):
            mo = GROUP_MASKS + g * GROUP_MASK_STRIDE
            no = GROUP_NAMES + g * GROUP_NAME_LEN
            name = _text(d[no:no + GROUP_NAME_LEN])
            members = [i for i in range(MAX_FIXTURES) if d[mo + i]]
            if name and not name.isprintable():
                name = ""
            if name or members:
                order = [i for i in self.group_list(g) if i in members]
                order += [i for i in members if i not in order]
                out.append((g, name or f"Group {g + 1}", order))
        return out

    # ------------------------------------------------------------- playbacks
    def playback_records(self):
        d = self.d
        for table, count, bank in ((FIXED_TABLE, FIXED_COUNT, "Fixed"), (PB_TABLE, PB_COUNT, "Playback")):
            for i in range(count):
                o = table + i * PB_STRIDE
                if o + PB_STRIDE > len(d) or d[o] == 0:
                    continue
                speed_ms = _u16(d, o + 0x0B)
                first, last = _u16(d, o + 0x12), _u16(d, o + 0x14)
                name = _text(d[o + 0x2C:o + 0x40])
                yield bank, i, name, speed_ms, first, last

    def _block(self, k: int) -> int:
        return STEP_BASE + k * STEP_BLOCK

    def _parse_step(self, buf: bytes, q: int, valid_fx: set[int]):
        entries = []
        while q + 4 <= len(buf):
            fx, order = struct.unpack_from("<HH", buf, q)
            if fx not in valid_fx or order >= MAX_FIXTURES:
                break
            q += 4
            pairs, ok = [], True
            while q + 2 <= len(buf):
                c = _u16(buf, q)
                q += 2
                if c == 0xFFFE:
                    break
                if not (CODE_A <= c < CODE_B + PAGES) or q + 2 > len(buf):
                    ok = False
                    break
                pairs.append((c, _u16(buf, q)))
                q += 2
            if not ok:
                break
            entries.append((fx, order, pairs))
            if buf[q:q + 2] == b"\xff\xff":
                break
        return entries

    def playback_steps(self, first: int, last: int, valid_fx: set[int]):
        """Decode the steps of the playback object starting at block ``first``."""
        d = self.d
        h = self._block(first)
        if h + STEP_BLOCK > min(len(d), STEP_HEAP_END) or d[h + 8:h + 16] != HDR_SIG:
            return None, []
        obj_blocks = _u16(d, h + 6)
        times = (_u16(d, h + 0x23), _u16(d, h + 0x29))
        steps = []

        def scan(blocks, only_first=False):
            for k in blocks:
                b = self._block(k)
                if b + STEP_BLOCK > STEP_HEAP_END:
                    break
                if d[b + 2:b + 4] == b"\xff\xff" and d[b + 8:b + 16] != HDR_SIG:
                    ents = self._parse_step(d[b:b + STEP_BLOCK * 48], 4, valid_fx)
                    if ents:
                        steps.append(ents)
                        if only_first:
                            return

        scan(range(first + 1, first + max(obj_blocks, 1)))
        if not steps:   # small objects sometimes keep their data right after the header run
            scan(range(first + max(obj_blocks, 1), min(last, first + obj_blocks + 3) + 1), only_first=True)
        return times, steps


# ---------------------------------------------------------------------------
def _code_to_slot(code: int) -> int:
    if CODE_A <= code < CODE_A + PAGES:
        return 2 * (code - CODE_A)
    return 2 * (code - CODE_B) + 1


def build_type(entry: LibEntry) -> FixtureType:
    chans = [Channel.make(n or f"Ch {i + 1}") for i, n in enumerate(entry.channel_names)]
    # 16 bit fine channels from the wheel slot table
    for coarse, fine in entry.slots:
        if coarse and fine and fine <= len(chans) and coarse <= len(chans):
            base = chans[coarse - 1].attr
            if base in ("pan", "tilt"):
                chans[fine - 1].attr = base + "_fine"
                chans[fine - 1].default = 0
                if not entry.channel_names[fine - 1]:
                    chans[fine - 1].name = chans[coarse - 1].name + " Fine"
            elif not entry.channel_names[fine - 1]:
                chans[fine - 1].name = chans[coarse - 1].name + " Fine"
                chans[fine - 1].attr = "none"
    ft = FixtureType(name=entry.name, manufacturer=entry.manufacturer, channels=chans)
    ft.guess_kind()
    return ft


def import_sho(path: str) -> tuple[Show, ImportReport]:
    with open(path, "rb") as fh:
        raw = fh.read()
    show, rep = import_sho_bytes(raw, name=path.replace("\\", "/").split("/")[-1])
    show.source_path = path
    return show, rep


def import_sho_bytes(raw: bytes, name: str = "MINI1000") -> tuple[Show, ImportReport]:
    data = decompress(raw)
    rd = ShoReader(data)
    rep = ImportReport()
    show = Show(name=name.rsplit(".", 1)[0])
    show.console_info = {"console": "CODE MINI 1000T", **rd.network()}

    lib = rd.library()
    type_keys: dict[int, str] = {}
    for idx, e in enumerate(lib):
        if e is None:
            continue
        ft = build_type(e)
        key = ft.key
        n = 2
        while key in show.types:      # duplicate names in the library
            ft.name = f"{e.name} ({n})"
            key = ft.key
            n += 1
        ft.lib_index = idx
        show.add_type(ft)
        type_keys[idx] = key
    rep.types = len(show.types)

    idx_to_fid: dict[int, int] = {}
    for i, fname, t, addr in rd.fixtures():
        if t not in type_keys:
            rep.warnings.append(f"Fixture {i + 1}: unknown library type {t}")
            continue
        ft = show.types[type_keys[t]]
        fid = i + 1
        uni, a = (addr // 512, addr % 512 + 1) if addr >= 0 else (0, 0)
        show.fixtures.append(Fixture(fid=fid, name=fname or ft.name, type_key=ft.key,
                                     universe=uni, address=a, slot=i))
        idx_to_fid[i] = fid
    rep.fixtures = len(show.fixtures)

    for gslot, gname, members in rd.groups():
        fids = [idx_to_fid[m] for m in members if m in idx_to_fid]
        show.groups.append(Group(name=gname, fixtures=fids, slot=gslot))
    rep.groups = len(show.groups)

    # slot tables per type key for step decoding
    slot_tab = {type_keys[i]: lib[i].slots for i in type_keys}
    valid_fx = set(idx_to_fid)
    number = 0
    for bank, i, pname, speed_ms, first, last in rd.playback_records():
        number += 1
        times, raw_steps = rd.playback_steps(first, last, valid_fx)
        pb = Playback(name=pname or f"{bank} {i + 1}", bank=bank, number=number,
                      speed=max(0.05, (speed_ms or 1000) / 1000.0),
                      source=f"{bank} #{i + 1} blocks {first}-{last}", slot=i)
        if times:
            t_a, t_b = times
            if t_b:
                pb.fade = t_b / 1000.0
            if t_a:
                pb.speed = t_a / 1000.0
        for sn, ents in enumerate(raw_steps):
            st = Step(name=f"Step {sn + 1}")
            for fx, _order, pairs in ents:
                fid = idx_to_fid[fx]
                fixture = show.fixture(fid)
                ft = show.types[fixture.type_key]
                slots = slot_tab[ft.key]
                vals = st.values.setdefault(fid, {})
                for code, v in pairs:
                    coarse, fine = slots[_code_to_slot(code)]
                    if not coarse or coarse > len(ft.channels):
                        continue
                    if v > 255:
                        if fine and fine <= len(ft.channels) and v != 0xFFFF:
                            vals[coarse - 1] = v >> 8
                            vals[fine - 1] = v & 0xFF
                        continue
                    vals[coarse - 1] = v
                    if fine and fine <= len(ft.channels):
                        vals.setdefault(fine - 1, 0)
            if st.values:
                pb.steps.append(st)
        pb.mode = "chase" if len(pb.steps) > 1 else "cuelist"
        rep.steps += len(pb.steps)
        show.playbacks.append(pb)
    rep.playbacks = len(show.playbacks)

    from .layout import auto_layout
    auto_layout(show)
    return show, rep
