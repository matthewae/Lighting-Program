"""DMX input/output: Art-Net, sACN (E1.31) and ENTTEC DMX USB Pro.

Output: send the engine universes to real fixtures.
Input:  receive what the CODE MINI 1000T console is sending (Art-Net or a
        USB DMX interface that receives DMX), so the visualizer shows the
        console's live output while you program on the console itself.
"""
from __future__ import annotations

import socket
import struct
import threading
import time
import uuid
from typing import Callable, Optional

ARTNET_PORT = 6454
SACN_PORT = 5568


# ----------------------------------------------------------------- Art-Net
def artdmx_packet(universe: int, data: bytes, sequence: int = 0) -> bytes:
    data = bytes(data[:512])
    if len(data) % 2:
        data += b"\0"
    return (b"Art-Net\0" + struct.pack("<H", 0x5000) + struct.pack(">H", 14)
            + bytes([sequence & 0xFF, 0]) + struct.pack("<H", universe & 0x7FFF)
            + struct.pack(">H", len(data)) + data)


def parse_artdmx(pkt: bytes) -> Optional[tuple[int, bytes]]:
    if len(pkt) < 18 or pkt[:8] != b"Art-Net\0":
        return None
    if struct.unpack_from("<H", pkt, 8)[0] != 0x5000:
        return None
    universe = struct.unpack_from("<H", pkt, 14)[0]
    length = struct.unpack_from(">H", pkt, 16)[0]
    return universe, pkt[18:18 + length]


class ArtNetOutput:
    def __init__(self, target: str = "255.255.255.255", universe_offset: int = 0):
        self.target = target
        self.offset = universe_offset
        self.seq = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def send(self, universes: dict[int, bytearray]) -> None:
        self.seq = self.seq % 255 + 1
        for u, data in universes.items():
            try:
                self.sock.sendto(artdmx_packet(u + self.offset, data, self.seq), (self.target, ARTNET_PORT))
            except OSError:
                pass

    def close(self) -> None:
        self.sock.close()


# -------------------------------------------------------------------- sACN
class SacnOutput:
    def __init__(self, universe_offset: int = 1, source_name: str = "MiniDesk"):
        self.offset = universe_offset
        self.cid = uuid.uuid4().bytes
        self.name = source_name.encode()[:63].ljust(64, b"\0")
        self.seq = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)

    def packet(self, universe: int, data: bytes) -> bytes:
        data = bytes(data[:512]).ljust(512, b"\0")
        dmp = (struct.pack(">H", 0x7000 | (10 + 513)) + b"\x02\xa1" + struct.pack(">HHH", 0, 1, 513)
               + b"\0" + data)
        frame = (struct.pack(">H", 0x7000 | (77 + len(dmp))) + struct.pack(">I", 0x00000002) + self.name
                 + bytes([100]) + struct.pack(">H", 0) + bytes([self.seq, 0])
                 + struct.pack(">H", universe) + dmp)
        root = (struct.pack(">HH", 0x0010, 0) + b"ASC-E1.17\0\0\0"
                + struct.pack(">H", 0x7000 | (22 + len(frame))) + struct.pack(">I", 0x00000004)
                + self.cid + frame)
        return root

    def send(self, universes: dict[int, bytearray]) -> None:
        self.seq = (self.seq + 1) & 0xFF
        for u, data in universes.items():
            uni = u + self.offset
            addr = f"239.255.{(uni >> 8) & 0xFF}.{uni & 0xFF}"
            try:
                self.sock.sendto(self.packet(uni, data), (addr, SACN_PORT))
            except OSError:
                pass

    def close(self) -> None:
        self.sock.close()


# ------------------------------------------------------- ENTTEC DMX USB Pro
def list_serial_ports() -> list[str]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [p.device for p in list_ports.comports()]


class EnttecProOutput:
    def __init__(self, port: str):
        import serial  # pyserial
        self.ser = serial.Serial(port, baudrate=57600, timeout=0)

    def send(self, universes: dict[int, bytearray]) -> None:
        data = bytes(universes.get(min(universes), bytearray(512)) if universes else bytearray(512))
        payload = b"\0" + data[:512]
        msg = b"\x7e\x06" + struct.pack("<H", len(payload)) + payload + b"\xe7"
        try:
            self.ser.write(msg)
        except Exception:
            pass

    def close(self) -> None:
        self.ser.close()


# ------------------------------------------------------------------- input
class DmxInput:
    """Base class: keeps the latest received universe and a timestamp."""

    def __init__(self):
        self.data = bytearray(512)
        self.last_rx = 0.0
        self.packets = 0
        self.source = ""
        self.lock = threading.Lock()
        self.on_frame: Optional[Callable[[], None]] = None
        self._stop = threading.Event()
        self.thread: Optional[threading.Thread] = None

    @property
    def alive(self) -> bool:
        return time.time() - self.last_rx < 2.0

    def _update(self, data: bytes, source: str) -> None:
        with self.lock:
            n = min(512, len(data))
            self.data[:n] = data[:n]
            self.last_rx = time.time()
            self.packets += 1
            self.source = source
        if self.on_frame:
            self.on_frame()

    def snapshot(self) -> bytearray:
        with self.lock:
            return bytearray(self.data)

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def stop(self) -> None:
        self._stop.set()


class ArtNetInput(DmxInput):
    def __init__(self, universe: int = 0, bind: str = "0.0.0.0", ignore_ips: Optional[set[str]] = None):
        super().__init__()
        self.universe = universe
        self.ignore = ignore_ips or set()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        self.sock.bind((bind, ARTNET_PORT))
        self.sock.settimeout(0.5)

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                pkt, addr = self.sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            if addr[0] in self.ignore:
                continue
            res = parse_artdmx(pkt)
            if res and res[0] == self.universe:
                self._update(res[1], addr[0])

    def stop(self) -> None:
        super().stop()
        try:
            self.sock.close()
        except OSError:
            pass


class EnttecProInput(DmxInput):
    """ENTTEC DMX USB Pro in 'receive DMX' mode (label 5)."""

    def __init__(self, port: str):
        super().__init__()
        import serial
        self.ser = serial.Serial(port, baudrate=57600, timeout=0.5)
        # receive DMX on change = 0 -> always send packets
        self.ser.write(b"\x7e\x08\x01\x00\x00\xe7")

    def run(self) -> None:
        buf = bytearray()
        while not self._stop.is_set():
            try:
                buf += self.ser.read(600)
            except Exception:
                break
            while True:
                s = buf.find(b"\x7e")
                if s < 0 or len(buf) - s < 5:
                    break
                label = buf[s + 1]
                ln = buf[s + 2] | (buf[s + 3] << 8)
                if len(buf) - s < 5 + ln:
                    break
                body = bytes(buf[s + 4:s + 4 + ln])
                del buf[:s + 5 + ln]
                if label == 5 and len(body) > 2 and body[0] == 0:
                    self._update(body[2:], "USB")

    def stop(self) -> None:
        super().stop()
        try:
            self.ser.close()
        except Exception:
            pass


def local_ips() -> set[str]:
    ips = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return ips
