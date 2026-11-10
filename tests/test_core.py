import os
import socket
import time

import pytest

from minidesk.attributes import infer_attribute
from minidesk.commands import CommandLine
from minidesk.dmx_io import ArtNetInput, artdmx_packet, parse_artdmx
from minidesk.engine import Engine
from minidesk.model import Fixture, Playback, Show, Step, builtin_types
from minidesk.sho_import import import_sho

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "GMS_MATT.SHO")


def small_show() -> Show:
    s = Show()
    for t in builtin_types():
        s.add_type(t)
    par = s.types["Generic/RGBW PAR 8ch"]
    mh = s.types["Generic/Moving Head Spot 16ch"]
    s.fixtures.append(Fixture(1, "Par 1", par.key, 0, 1))
    s.fixtures.append(Fixture(2, "Par 2", par.key, 0, 9))
    s.fixtures.append(Fixture(3, "Spot", mh.key, 0, 17))
    return s


# ------------------------------------------------------------------ importer
@pytest.fixture(scope="module")
def imported():
    if not os.path.exists(SAMPLE):
        pytest.skip("sample show missing")
    return import_sho(SAMPLE)


def test_import_counts(imported):
    show, rep = imported
    assert rep.types == 10
    assert len(show.fixtures) == 65
    assert len(show.groups) == 14
    assert show.console_info["ip"] == "192.168.0.231"


def test_import_patch_and_types(imported):
    show, _ = imported
    f1 = show.fixture(1)
    assert f1.type_key == "GMS/PAR NEW" and f1.address == 1
    f2 = show.fixture(2)
    assert f2.type_key == "Centurion/CLED-543" and f2.address == 9
    f20 = show.fixture(20)
    assert f20.type_key == "MJingLIGHT/AS_BSW350" and f20.address == 241
    bsw = show.types["MJingLIGHT/AS_BSW350"]
    assert [c.attr for c in bsw.channels[:4]] == ["pan", "pan_fine", "tilt", "tilt_fine"]
    assert not show.fixture(46).patched          # unpatched RGBW Led
    assert show.patch_conflicts() == []


def test_import_groups(imported):
    show, _ = imported
    g = {x.name: x.fixtures for x in show.groups}
    assert g["ALL PAR"] == list(range(1, 19))
    assert g["STRB TOWER"] == [27, 30]
    assert g["HAZER"] == [41]


def test_import_playbacks(imported):
    show, _ = imported
    pbs = {p.name: p for p in show.playbacks if p.bank == "Fixed"}
    assert "Ambience" in pbs and "Sermon" in pbs
    fres = pbs["Fresnel PAW"]
    assert len(fres.steps) == 1
    # all 10 fresnels, both dimmer channels
    assert sorted(fres.steps[0].values) == list(range(31, 41))
    assert all(set(v) == {0, 1} for v in fres.steps[0].values.values())


def test_show_roundtrip(imported, tmp_path):
    show, _ = imported
    p = tmp_path / "x.mdshow"
    show.save(str(p))
    s2 = Show.load(str(p))
    assert len(s2.fixtures) == len(show.fixtures)
    assert s2.playbacks[0].steps[0].values == show.playbacks[0].steps[0].values


# -------------------------------------------------------------------- engine
def test_attribute_inference():
    assert infer_attribute("Dimmer BL") == "dimmer"
    assert infer_attribute("X/Y Speed") == "speed"
    assert infer_attribute("Col.Mix 1") == "colormacro"
    assert infer_attribute("Gobo 2 Rot") == "gobo_rot"
    assert infer_attribute("Inner Red") == "red"
    assert infer_attribute("unused") == "none"


def test_programmer_output():
    s = small_show()
    e = Engine(s)
    e.select([1, 2])
    e.set_intensity(100)
    e.set_attr("red", 200)
    u = e.tick(0.02)[0]
    assert u[0] == 255 and u[1] == 200 and u[8] == 255 and u[9] == 200
    # moving head defaults: pan/tilt centre and open shutter
    assert u[16] == 128 and u[18] == 128 and u[22] == 255


def test_playback_htp_and_fade():
    s = small_show()
    pb = Playback(name="A", number=1, mode="cuelist", fade=1.0,
                  steps=[Step(values={1: {0: 200, 1: 255}})])
    s.playbacks.append(pb)
    e = Engine(s)
    st = e.states[0]
    e.set_level(st, 0.5)
    e.tick(0.5)                  # half way through a 1 s fade
    u = e.tick(0.0)[0]
    assert 40 <= u[0] <= 60      # 200 * 0.5 progress * 0.5 level
    e.tick(1.0)
    u = e.tick(0.0)[0]
    assert u[0] == 100 and u[1] == 255   # dimmer scaled by fader, colour LTP not scaled
    e.grand_master = 0.5
    assert e.tick(0.0)[0][0] == 50


def test_chase_advances():
    s = small_show()
    pb = Playback(name="C", number=1, mode="chase", speed=0.1,
                  steps=[Step(values={1: {0: 255}}), Step(values={2: {0: 255}})])
    s.playbacks.append(pb)
    e = Engine(s)
    st = e.states[0]
    e.go(st)
    e.tick(0.01)
    assert st.index == 0
    for _ in range(12):
        e.tick(0.01)
    assert st.index == 1


def test_store_from_programmer():
    s = small_show()
    e = Engine(s)
    e.select([3])
    e.set_attr("pan", 10)
    pb = Playback(name="P", number=7)
    s.playbacks.append(pb)
    e.store(pb)
    assert pb.steps[0].values == {3: {0: 10}}


def test_command_line():
    s = small_show()
    e = Engine(s)
    c = CommandLine(e)
    assert "3 fixture" in c.run("fixture 1 thru 3 at 50")
    assert e.programmer[1][0] == 128
    c.run("clear")
    assert not e.programmer and not e.selection
    c.run("f 1 + 2 at full")
    assert "stored" in c.run("store 9")
    assert any(p.number == 9 for p in s.playbacks)
    assert "go executor 9" in c.run("go 9")
    assert e.state_for(s.playbacks[-1]).running


# ----------------------------------------------------------------------- I/O
def test_artnet_packet_roundtrip():
    data = bytes(range(256)) * 2
    uni, out = parse_artdmx(artdmx_packet(3, data, 5))
    assert uni == 3 and out == data


def test_artnet_input_loopback():
    try:
        inp = ArtNetInput(universe=0, bind="127.0.0.1")
    except OSError:
        pytest.skip("port 6454 not available")
    inp.start()
    try:
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        frame = bytes([10, 20, 30]) + bytes(509)
        for _ in range(20):
            tx.sendto(artdmx_packet(0, frame), ("127.0.0.1", 6454))
            time.sleep(0.02)
            if inp.packets:
                break
        assert inp.alive
        assert inp.snapshot()[:3] == bytearray([10, 20, 30])
    finally:
        inp.stop()
