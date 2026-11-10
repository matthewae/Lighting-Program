# CODE MINI 1000T `.SHO` show file – notes

Worked out from a real show file (`samples/GMS_MATT.SHO`). All offsets are in the
**decompressed** image. Integers are little endian unless noted.

## Container

| Offset | Size | Content |
|---|---|---|
| 0 | 4 | uncompressed size, **big endian** (Qt `qCompress` header) |
| 4 | … | zlib stream |

The decompressed image (~6.8 MB) starts with `SHOWMINI1000` and ends with `EXTD`.
The console compresses with zlib **level 1** – recompressing an unchanged image with level 1
reproduces the original file byte for byte.

| Header offset | Content |
|---|---|
| `0x20` / `0x24` | section 2 offset (`0x5DDE68`) / size |
| `0x28` / `0x2C` | section 3 offset / size |
| `0x30` / `0x34` | `EXTD` offset / size |
| `0x3C` | **CRC32 of `data[0x40:]`** (little endian) – must be updated after any change |

## Tables

| Offset | Layout | Meaning |
|---|---|---|
| `0x1520` | 4+4 bytes | console IP and netmask |
| `0x1571` | records of `0x8B3` bytes | fixture library (see below) |
| `0x6E449` | 512 bytes per group, 400 groups | group membership, one byte per fixture index (`0xFF` = member) |
| `0x515E68` | 0x400 bytes per group | member order: u16 fixture indices, `0xFFFF` terminated |
| `0xA0449` | 20 bytes per group | group names |
| `0xA2589` | `0x190` bytes per fixture | patch; first u16 = absolute DMX address 0..2047 (universe×512 + address−1), `0xFFFF` = unpatched |
| `0xD4B89` | 1 byte per fixture | channel count |
| `0xD4F89` | 20 bytes per fixture | fixture (user) names, 512 slots |
| `0xD7789` | 1 byte per fixture | library index of each fixture (`0xFF` = empty slot) |
| `0xA2389` | 1 byte per fixture | `0xFF` = patched |
| `0xD4D89` | 1 byte per fixture | `0xFF` = slot in use |
| `0xD7F8C` | 1 byte per DMX channel (2048) | channel number inside the fixture (stale for free channels) |
| `0xD878C` | u16 per DMX channel (2048) | fixture index that owns the DMX channel, `0xFFFF` = free |
| `0xD9C60` | 600 × 64 bytes | playbacks ("PlayBack001" …) |
| `0xEFA60` | 64 byte records | fixed playbacks (Ambience, Greeter, …) |
| `0x115E5E` | 0xC0 byte blocks | heap holding playback/step data |

### Library record (relative to the name)

| Rel. offset | Content |
|---|---|
| 0 | name, 20 chars |
| 20 | manufacturer, 14 chars |
| 34 | channel count |
| `0x203` | 40 slots × (coarse channel, fine channel), 1 based – the console's wheel layout: slot `2p` = wheel A of page `p`, slot `2p+1` = wheel B |
| `0x4D3` | channel names, 12 chars each |

### Playback record (64 bytes)

| Rel. offset | Content |
|---|---|
| 0 | flags (0 = empty) |
| `0x0B` | u16 default speed (ms) |
| `0x12` / `0x14` | u16 first / last heap block |
| `0x2A` | u16 (level / flags) |
| `0x2C` | name, 20 chars |

### Heap

Block `k` lives at `0x115E5E + k*0xC0`. An object header block has the bytes
`01 00 01 00 00 00 00 ff` at +8; +4 = owner playback index, +6 = number of blocks of
the object, +0x23 / +0x29 = times in ms. Step data starts on a block boundary with
`?? ?? ff ff`, followed by fixture entries:

```
u16 fixture index, u16 selection order,
  (u16 code, u16 value)*   code 0x191+p = wheel A page p, 0x1A5+p = wheel B page p
u16 0xFFFE                 end of fixture entry
...                        next fixture entry, or 0xFFFF = end of step
```

The code is mapped to a channel through the library slot table. Values above 255 are
16 bit (coarse/fine) for slots that have a fine channel.

Unused blocks keep stale data, so step decoding is best effort.
