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
    assert sorted(g["ALL PAR"]) == list(range(1, 19))
    assert g["ALL PAR"][:4] == [18, 17, 16, 15]          # console member order is kept
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


# ------------------------------------------------------------------ effects
def test_position_effect_moves_pan():
    from minidesk.model import Effect
    s = small_show()
    e = Engine(s)
    e.add_effect(Effect(type="circle", fixtures=[3], speed=1.0, size=50))
    seen = set()
    for _ in range(40):
        seen.add(e.tick(0.025)[0][16])        # pan of the spot
    assert max(seen) - min(seen) > 60


def test_intensity_chase_effect_and_store():
    from minidesk.model import Effect
    s = small_show()
    e = Engine(s)
    e.select([1, 2])
    e.add_effect(Effect(type="dim_chase", fixtures=[1, 2], speed=1.0, spread=360))
    u = e.tick(0.1)[0]
    assert {u[0], u[8]} == {0, 255}             # one on, one off
    pb = Playback(name="FX", number=3)
    s.playbacks.append(pb)
    e.store(pb)
    assert pb.steps[0].effects and pb.steps[0].effects[0].type == "dim_chase"
    e.clear_programmer()
    st = e.state_for(pb)
    e.go(st)
    u = e.tick(0.1)[0]
    assert {u[0], u[8]} == {0, 255}


def test_delay_and_fade_out():
    s = small_show()
    pb = Playback(name="T", number=1, mode="cuelist", steps=[
        Step(values={1: {0: 255}}, fade=1.0, delay=1.0),
        Step(values={1: {0: 0}}, fade=0.0, fade_out=2.0)])
    s.playbacks.append(pb)
    e = Engine(s)
    st = e.states[0]
    e.go(st)
    e.tick(0.5)
    assert e.tick(0.0)[0][0] == 0               # still in the delay
    e.tick(1.0)
    assert 100 < e.tick(0.0)[0][0] < 160        # half way through fade in
    e.tick(1.0)
    e.go(st)                                     # step 2: fade out over 2 s
    e.tick(1.0)
    assert 100 < e.tick(0.0)[0][0] < 160


# --------------------------------------------------------------- .SHO write
def test_sho_save_unchanged_is_identical(tmp_path):
    import shutil
    from minidesk.sho_file import ShoDocument
    p = tmp_path / "A.SHO"
    shutil.copy(SAMPLE, p)
    show, _ = import_sho(str(p))
    doc = ShoDocument.open(str(p))
    rep = doc.save(show)
    assert not rep.errors and rep.verified
    assert p.read_bytes() == open(SAMPLE, "rb").read()


def test_sho_save_changes(tmp_path):
    import shutil
    from minidesk.model import Group
    from minidesk.sho_file import ShoDocument
    p = tmp_path / "B.SHO"
    shutil.copy(SAMPLE, p)
    show, _ = import_sho(str(p))
    doc = ShoDocument.open(str(p))
    show.fixture(46).address = 460
    show.fixture(1).name = "PAR KIRI"
    show.fixtures.append(Fixture(66, "NEW", "Centurion/CLED-543", 1, 1))
    show.groups.append(Group("BARU", [66, 46]))
    show.playbacks[0].name = "Ambience 2"
    rep = doc.save(show, backup_dir=str(tmp_path / "bk"))
    assert not rep.errors and rep.verified and rep.backup
    s2, _ = import_sho(str(p))
    assert s2.fixture(46).address == 460 and s2.fixture(1).name == "PAR KIRI"
    assert s2.fixture(66).universe == 1 and s2.fixture(66).type_key == "Centurion/CLED-543"
    assert [g.fixtures for g in s2.groups if g.name == "BARU"] == [[66, 46]]
    assert s2.playbacks[0].name == "Ambience 2"
    assert sum(len(p.steps) for p in s2.playbacks) == sum(len(p.steps) for p in show.playbacks)


def test_sho_save_rejects_overlap(tmp_path):
    import shutil
    from minidesk.sho_file import ShoDocument
    p = tmp_path / "C.SHO"
    shutil.copy(SAMPLE, p)
    show, _ = import_sho(str(p))
    doc = ShoDocument.open(str(p))
    show.fixture(2).address = 3
    rep = doc.save(show)
    assert rep.errors
    assert p.read_bytes() == open(SAMPLE, "rb").read()


# ------------------------------------------------- playback options & presets
def _chase(direction, loop=True, n=3):
    s = small_show()
    pb = Playback(name="D", number=1, mode="chase", speed=0.1, direction=direction, loop=loop,
                  steps=[Step(values={1: {0: 10 * (i + 1)}}) for i in range(n)])
    s.playbacks.append(pb)
    e = Engine(s)
    return e, e.states[0]


def _run(e, st, steps):
    seen = []
    for _ in range(steps):
        e.tick(0.11)
        seen.append(st.index)
    return seen


def test_chase_directions():
    e, st = _chase("backward")
    e.go(st)
    assert st.index == 2
    assert _run(e, st, 3) == [1, 0, 2]
    e, st = _chase("bounce")
    e.go(st)
    assert _run(e, st, 5) == [1, 2, 1, 0, 1]
    e, st = _chase("forward", loop=False)
    e.go(st)
    assert _run(e, st, 4) == [1, 2, 2, 2]          # holds on the last step


def test_cuelist_follow_and_release():
    s = small_show()
    pb = Playback(name="F", number=1, mode="cuelist", release=1.0, steps=[
        Step(values={1: {0: 255}}, hold=0.2, follow=True), Step(values={1: {0: 100}})])
    s.playbacks.append(pb)
    e = Engine(s)
    st = e.states[0]
    e.go(st)
    e.tick(0.1)
    assert st.index == 0
    e.tick(0.2)
    assert st.index == 1                            # followed automatically
    e.tick(0.1)
    e.stop(st, fade=True)                           # release fade 1 s
    e.tick(0.5)
    assert st.running and 40 <= e.tick(0.0)[0][0] <= 60
    e.tick(0.6)
    assert not st.running


def test_tap_tempo(monkeypatch):
    import minidesk.engine as em
    e, st = _chase("forward")
    t = [100.0]
    monkeypatch.setattr(em.time, "perf_counter", lambda: t[0])
    for _ in range(4):
        e.tap(st)
        t[0] += 0.5
    assert abs(st.pb.speed - 0.5) < 1e-6


def test_presets_store_and_recall():
    s = small_show()
    e = Engine(s)
    e.select([1])
    e.set_attr("red", 255)
    e.set_intensity(100)
    pr = e.make_preset("Red", "Color")
    assert pr.values == {1: {1: 255}}               # only colour channels kept
    e.clear_programmer()
    e.select([2])                                    # same type -> recalled by type
    assert e.apply_preset(pr) == 1
    assert e.programmer[2] == {1: 255}


def test_import_presets(imported):
    show, _ = imported
    names = [p.name for p in show.presets]
    assert names[:3] == ["WHITE", "GREEN", "YELLOW"]
    assert show.presets[0].category == "Color"


def test_channel_functions_and_beam_state():
    from minidesk.vis_state import compute
    s = small_show()
    e = Engine(s)
    e.select([3])
    e.set_intensity(100)
    e.set_attr("gobo", 30)      # gobo 2
    e.set_attr("prism", 60)     # prism on
    u = bytes(e.tick(0.0)[0])
    st = compute(s.fixture(3), s.types[s.fixture(3).type_key], u, 0.0)
    assert st.gobo == 2 and st.prism == 3


# ---------------------------------------------------------------- MIDI / net
def test_midi_mapping_and_learn():
    from minidesk.midi import MidiManager, parse
    got = []
    m = MidiManager(lambda a, t, v, on: got.append((a, t, round(v, 2), on)))
    m.mapping = MidiManager.default_bank_map(16, 15)
    m.feed(parse(0x90, 2, 100))          # note 2 -> GO executor 18
    m.feed(parse(0xB0, 0, 127))          # cc 0 -> fader executor 16
    assert got == [("exec_go", 18, 0.79, True), ("exec_fader", 16, 1.0, True)]
    learned = []
    m.learn = learned.append
    m.feed(parse(0x91, 60, 90))
    assert learned and learned[0]["ch"] == 1 and learned[0]["num"] == 60


def test_artpoll_reply_parse():
    from minidesk.dmx_io import artpoll_packet, parse_artpollreply, same_subnet
    assert artpoll_packet()[8:10] == b"\x00\x20"
    pkt = bytearray(239)
    pkt[:8] = b"Art-Net\0"
    pkt[8:10] = b"\x00\x21"
    pkt[10:14] = bytes([192, 168, 0, 231])
    pkt[26:30] = b"MINI"
    rep = parse_artpollreply(bytes(pkt))
    assert rep["ip"] == "192.168.0.231" and rep["short"] == "MINI"
    assert same_subnet("192.168.0.10", "192.168.0.231") and not same_subnet("10.0.0.2", "192.168.0.231")


# -------------------------------------------------------------- 3D models
def test_builtin_models_and_obj_roundtrip(tmp_path):
    from minidesk.meshes import BUILTIN, build_model, load_obj, write_obj
    for k in BUILTIN:
        m = build_model(k)
        assert m.face_count > 0
        p = tmp_path / f"{k}.obj"
        write_obj(m, str(p))
        r = load_obj(str(p))
        assert r.face_count == m.face_count
        assert set(r.parts) <= {"base", "yoke", "head"} | set(m.parts)
        assert abs(r.pivot[2] - m.pivot[2]) < 1e-3
        assert r.parts and any(p_.EM.any() for p_ in r.parts.values()) or k in ("fog", "hazer")


def test_stl_and_gltf_import(tmp_path):
    import json
    import struct
    from minidesk.meshes import fit_scale, load_model
    stl = tmp_path / "a.stl"
    stl.write_text("solid a\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 100 0 0\n"
                   "vertex 0 100 0\nendloop\nendfacet\nendsolid a\n")
    m = load_model(str(stl))
    assert m.face_count == 1 and 0.002 < fit_scale(m, "par") < 0.004      # mm model gets fitted
    # minimal glb: one triangle in a node called "Head", emissive material
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    gj = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
          "nodes": [{"name": "Head", "mesh": 0}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
          "materials": [{"name": "Lens", "emissiveFactor": [1, 1, 1]}],
          "buffers": [{"byteLength": len(pos)}],
          "bufferViews": [{"buffer": 0, "byteLength": len(pos)}],
          "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}]}
    js = json.dumps(gj).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(pos), b"BIN\x00") + pos
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)
    g = load_model(str(glb))
    assert list(g.parts) == ["head"] and g.parts["head"].EM.all()
    # Y-up -> Z-up: the vertex (0, 1, 0) becomes (0, 0, 1)
    assert any(abs(v[2] - 1) < 1e-6 for v in g.parts["head"].verts)


def test_model_choice_for_console_fixtures(imported):
    show, _ = imported
    model = {t.name: t.model for t in show.types.values()}
    from minidesk.meshes import bundled_defaults
    mover = bundled_defaults().get("moving")
    assert model["CM-280V2@16"] == (mover or "beam") and model["AS_BSW350"] == (mover or "hybrid")
    assert model["CLED-543"] == "par" and model["STROBE 2.5"] == "strobe"
    assert model["DSK-1500VS"] == "fog_vertical" and model["HAZER"] == "hazer"


def test_user_models_fbx_and_truss():
    from minidesk import truss_model
    from minidesk.meshes import BUNDLED, load_model
    import os
    fbx = os.path.join(BUNDLED, "Moveing_head_1_A.fbx")
    if not os.path.exists(fbx):
        pytest.skip("bundled user models missing")
    m = load_model(fbx, "beam")
    assert {"base", "yoke", "head"} <= set(m.parts)
    head = m.parts["head"]
    lens = head.C[head.EM].mean(axis=0)
    assert lens[2] > m.pivot[2]                      # lens points up (+Z) at tilt centre
    t = truss_model.analyse(os.path.join(BUNDLED, "box_truss_12in.obj"))
    assert abs(t["width"] - 0.3048) < 0.002
    assert [round(s["length"], 2) for s in t["segments"]] == [3.05, 2.44, 1.83, 1.52, 0.91]
    tiles = truss_model.tile(6.1, t["segments"])
    assert len(tiles) == 2


def test_every_effect_runs_on_every_fixture_kind():
    from minidesk.model import EFFECT_TYPES, Effect
    s = small_show()
    e = Engine(s)
    for key in EFFECT_TYPES:
        e.clear_programmer()
        e.select([1, 2, 3])
        e.set_intensity(100)
        e.add_effect(Effect(type=key, fixtures=[1, 2, 3], speed=1.0))
        frames = {bytes(e.tick(0.07)[0][:40]) for _ in range(60)}
        constant = {"iris_wave", "iris_pulse",        # no iris channel in the test fixtures
                    "gobo_shake", "prism_spin"}       # one DMX value, the fixture itself shakes / spins
        assert len(frames) > 1 or key in constant, f"{key} does not change the output"


def test_position_shapes_follow_path():
    from minidesk.effects import shape_xy
    assert shape_xy("diamond", 0.0)[1] == 1 and abs(shape_xy("diamond", 0.25)[0] - 1) < 1e-9
    assert shape_xy("pan_saw", 0.0) == (-1.0, 0.0) and shape_xy("tilt_saw", 0.5)[1] == 0.0
    xs = [shape_xy("s_shape", i / 20)[0] for i in range(20)]
    assert max(xs) > 0.5 and min(xs) < -0.5             # S swings to both sides


def test_pan_tilt_invert_swap():
    s = small_show()
    e = Engine(s)
    spot = s.fixture(3)
    e.select([3])
    e.set_attr("pan", 10)
    e.set_attr("tilt", 200)
    u = e.tick(0.0)[0]
    assert (u[16], u[18]) == (10, 200)
    spot.invert_pan, spot.swap_pan_tilt = True, True
    u = e.tick(0.0)[0]
    assert (u[16], u[18]) == (255 - 200, 10)


def test_effect_order_and_blocks():
    from minidesk.effects import fixture_phase
    from minidesk.model import Effect
    e = Effect(type="dim_chase", fixtures=list(range(1, 9)), spread=360, order="center_out")
    ph = [fixture_phase(e, f) for f in e.fixtures]
    assert ph[3] == ph[4] and ph[0] == ph[7] and ph[3] < ph[0]       # symmetric from the centre
    e.order, e.blocks = "forward", 2
    ph = [fixture_phase(e, f) for f in e.fixtures]
    assert ph[0] == ph[1] and ph[2] == ph[3] and ph[1] < ph[2]       # pairs move together
    e.order = "odd_even"
    e.blocks = 1
    assert [fixture_phase(e, f) for f in (1, 2, 3)] == [0.0, 0.5, 0.0]
