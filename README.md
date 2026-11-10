# MiniDesk – Lighting programmer & visualizer untuk CODE MINI 1000T / MINI 1000T PRO

Aplikasi Python (PySide6/Qt) untuk **programming lighting** dengan gaya *dot2 onPC* / *QLC+*,
dilengkapi **visualizer 3D** sehingga Anda bisa melihat apa yang sedang di-setting dan bagaimana
playback berjalan – dan **kompatibel dengan console CODE MINI 1000T / MINI 1000T PRO**:

| Fitur kompatibilitas | Keterangan |
|---|---|
| Import file show console (`*.SHO`) | Library fixture (nama, merk, nama channel, tabel wheel A/B), patch DMX, tipe tiap fixture, group, playback + fixed playback (Ambience, Greeter, Sermon, …) beserta step/cue-nya |
| Visualizer live dari console | Terima DMX dari console via **Art-Net** (console punya port network – IP di file contoh: `192.168.0.231`) atau via interface **USB DMX (ENTTEC DMX USB Pro) mode input** |
| Output ke lampu | Art-Net, sACN (E1.31) dan ENTTEC DMX USB Pro |

![Programmer + visualizer](docs/screenshot_programmer.png)

![Visualizer mengikuti DMX live dari console (Art-Net)](docs/screenshot_console_live.png)

> File console **tidak pernah diubah** – import bersifat read-only. Hasil kerja disimpan sebagai
> `*.mdshow` (JSON).

## Fitur

- **Visualizer 3D** (drag = orbit, scroll = zoom, klik = pilih fixture) dengan beam berwarna,
  light-pool di lantai/dinding, pan/tilt moving head (termasuk 16-bit fine), zoom/frost, strobe/shutter,
  efek haze/fog (fog machine di patch ikut menambah haze), dan **Top view** untuk menggeser posisi
  fixture (tombol *3D / Top* atau tombol `Tab` di visualizer).
- **Fixtures / Groups sheet**: tombol group (dari console) + grid fixture dengan warna output live.
- **Programmer**: fader per channel dikelompokkan *Intensity / Position / Color / Beam / Other*,
  tombol intensitas cepat (0 … Full), *Highlight*, color picker & swatch (RGB/RGBW, CMY, atau
  color wheel), XY pad pan/tilt.
- **Executor bar** (seperti executor wing dot2): fader level, GO, back, pause, stop, Flash,
  halaman executor, filter (All / With steps / Fixed / Playback / User).
- **Playback engine**: mode *chase* (otomatis maju sesuai speed) dan *cuelist* (maju dengan GO),
  crossfade per step, intensitas **HTP** + atribut lain **LTP**, Grand Master & Blackout.
- **Cue editor**: ubah nama/mode/speed/fade, edit fade & hold per step, urutkan, hapus,
  *Load → programmer*, *Merge steps → 1 scene*, buat/hapus playback.
- **Store** dari programmer ke executor (add / merge / overwrite).
- **Patch**: tambah fixture (termasuk tipe generik bawaan), ubah address/universe/posisi,
  editor tipe fixture (atribut tiap channel, beam angle, range pan/tilt), auto layout panggung.
- **DMX monitor** 512 channel (output program, input console, atau yang tampil di visualizer).
- **Command line gaya dot2**:

```
fixture 1 thru 8 at 50
f 1 + 3 + 5 at full
group 7 at 75
group 7 red 255
pan 128
go 3          back 3          off 3          goto 3 2
store 5       store 5 /merge  store 5 /overwrite
clear         blackout        highlight
```

## Instalasi

Butuh Python 3.10 atau lebih baru (Windows / macOS / Linux).

```bash
pip install -r requirements.txt
```

## Menjalankan

```bash
python -m minidesk
```

Langsung membuka file console:

```bash
python -m minidesk samples/GMS_MATT.SHO
```

Windows: klik dua kali `run_windows.bat`. Linux/macOS: `./run.sh`.

## Alur kerja dengan console CODE MINI 1000T

### A. Lihat apa yang sedang diprogram di console (visualizer live)

1. Simpan show di console, salin file `.SHO` ke PC, lalu **Import MINI 1000 .SHO** (Ctrl+I).
   Fixture, patch, group dan playback langsung muncul; posisi fixture diatur otomatis dari nama
   group (DEPAN/FRONT, BELAKANG/BACK, TENGAH, ATAS/TOP, TOWER, …) – geser di *Top view* bila perlu,
   lalu **Save** sebagai `.mdshow`.
2. Hubungkan PC dan console ke jaringan yang sama (mis. PC `192.168.0.10`, subnet `255.255.255.0`;
   console di file contoh memakai `192.168.0.231`) dan aktifkan output Art-Net di console.
   Alternatif tanpa jaringan: sambungkan output DMX console ke interface ENTTEC DMX USB Pro
   (mode receive).
3. Buka **DMX I/O…** → *Input mode* = `artnet` (universe 0) atau `enttec` + port USB.
4. *Visualizer source* = `auto`: begitu data console masuk, status bar menampilkan
   **LIVE from &lt;IP console&gt;** dan visualizer mengikuti apa pun yang Anda mainkan di console.
   Pilih `mix (HTP)` untuk menggabungkan console + programmer PC.

### B. Programming / pre-programming di PC

1. Pilih fixture/group → atur di **Programmer** (atau ketik di command line).
2. **Store…** ke executor (step baru, merge, atau overwrite).
3. Mainkan lewat **Executor bar**; edit timing di tab **Cues**.
4. Bila ingin menyalakan lampu langsung dari PC, aktifkan Art-Net / sACN / USB Pro di **DMX I/O…**.
   Jangan mengirim ke lampu yang sama bersamaan dengan console kecuali jaringan Anda melakukan merge.

## Catatan kompatibilitas `.SHO`

Format `.SHO` MINI 1000 tidak dipublikasikan; struktur dibaca dari file show asli
(lihat [`docs/FORMAT_SHO.md`](docs/FORMAT_SHO.md)).

- **Sudah andal**: library fixture & nama channel, patch/alamat DMX, tipe tiap fixture, group,
  nama playback & fixed playback, IP console.
- **Beta**: isi step playback (nilai per channel) dan waktu fade/speed. Isi step di-decode dari
  "block heap" internal console, jadi beberapa playback bisa kosong atau berisi step sisa (stale).
  Bandingkan cue penting dengan console lewat input Art-Net, lalu perbaiki di tab **Cues**
  (mis. *Merge steps → 1 scene* bila step ternyata bagian dari satu scene).
- Warna color wheel & perilaku shutter di visualizer adalah pendekatan generik; sesuaikan atribut
  channel di **Patch → Edit fixture type…** bila perlu.
- Export balik ke format `.SHO` belum didukung (sengaja, agar file console tidak rusak).

## Struktur proyek

```
minidesk/
  sho_import.py   importer file show CODE MINI 1000T (.SHO)
  model.py        model show (fixture type, patch, group, playback, step) + simpan/buka JSON
  engine.py       engine DMX: programmer, playback/chase, fade, HTP/LTP, GM, blackout
  dmx_io.py       Art-Net / sACN / ENTTEC USB Pro output + Art-Net / USB Pro input
  commands.py     command line gaya dot2
  vis_state.py    DMX -> intensitas, warna, arah beam (dipakai visualizer)
  layout.py       auto layout posisi fixture dari nama group
  ui/             jendela utama, visualizer, programmer, executor, cue editor, patch, DMX monitor
samples/GMS_MATT.SHO   contoh show dari console
tests/                 unit test (pytest)
```

## Test

```bash
pip install pytest
python -m pytest -q
```
