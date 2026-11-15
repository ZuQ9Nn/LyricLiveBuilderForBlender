"""Phase 4 (Python side, no Blender): conversion, LLBM meshes, particle descriptions, manifest clips."""
import json
import math
import unittest

import numpy as np

from lyric_live_builder.core import bake, meshes, model, planner, world, xform
from lyric_live_builder.core.parts import particles as pts
from lyric_live_builder.export_unity import convert, manifest, meshbin, particles_unity
from tests.core.test_text_parts import inputs, metrics, sections_for

SWAP = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=np.float64)       # Blender -> Unity axes


def unity_rotate(q, v):
    """Rotate v by a Unity (x, y, z, w) quaternion (left-handed, but the formula is the same)."""
    return xform.rotate(np.array([q[3], q[0], q[1], q[2]]), v)


class TestConvert(unittest.TestCase):
    def test_rotation_follows_the_axis_swap(self):
        rng = np.random.default_rng(3)
        for _ in range(20):
            q = xform.normalize(rng.normal(size=4))
            v = rng.normal(size=3)
            want = SWAP @ xform.rotate(q, v)                 # rotate in Blender, then swap axes
            got = unity_rotate(convert.quat(q), SWAP @ v)   # swap, then rotate with the converted quaternion
            np.testing.assert_allclose(got, want, atol=1e-9)

    def test_srgb(self):
        np.testing.assert_allclose(convert.srgb([0.0, 1.0]), [0.0, 1.0], atol=1e-9)
        self.assertAlmostEqual(float(convert.srgb([0.214041])[0]), 0.5, places=3)


class TestMeshBin(unittest.TestCase):
    def test_round_trip_and_winding(self):
        v, f = meshes.particle_shape("cube")
        data = meshbin.encode(v, f, flat=True)
        pos, nrm, idx, _ = meshbin.decode(data)
        self.assertEqual(len(idx) % 3, 0)
        tris = idx.reshape(-1, 3)
        # every Unity triangle's normal (left-handed winding) agrees with the stored normal
        for a, b, c in tris:
            n = np.cross(pos[b] - pos[a], pos[c] - pos[a])         # Unity's own normal of a front face
            self.assertGreater(np.dot(n, nrm[a]), 0)
        np.testing.assert_allclose(np.sort(pos[:, 1]), np.sort(convert.pos(v[np.array([x for face in f for k in range(1, len(face) - 1) for x in (face[0], face[k], face[k + 1])])])[:, 1]))

    def test_pack(self):
        p = meshbin.Pack()
        for key in ("orb", "dome"):
            p.add(key, meshbin.encode(*meshes.build(key)))
        blob = p.bytes()
        for e in p.entries:
            pos = meshbin.decode(blob, e["offset"])[0]
            self.assertGreater(len(pos), 10)


class TestParticles(unittest.TestCase):
    def test_every_preset_describes(self):
        st = model.Settings()
        pal = {r: "#FFFFFF" for r in ("fg", "sub", "accent", "accent2", "ghostA", "ghostB", "white", "bg")}
        from lyric_live_builder.core import world
        for key, p in pts.PRESETS.items():
            spec = world.emitter(key, 1.0, 9.0, 5, pal, st, bursts=[{"t": 2.0, "origin": [0.0, 3.0, 2.0]}]
                                 if p["emitter"] == "burst" else None)
            if p["emitter"] == "lines":
                from lyric_live_builder.core.parts import lines
                v, f, col, uv4 = particles_unity.line_mesh(lines.geometry(p, spec["seed"], spec["colors"]))
                data = meshbin.encode(v, f, colors=col, uv4=uv4)
                pos, _, idx, col2 = meshbin.decode(data)
                self.assertEqual(len(pos), len(v))
                self.assertEqual(idx.size, 6 * len(f))
                self.assertEqual(int(idx.max()), len(v) - 1)
                np.testing.assert_allclose(col2, np.round(np.clip(col, 0, 1) * 255) / 255, atol=1e-6)
                quad = np.asarray(uv4[0]).reshape(-1, 4, 4)             # the other end of a's vertices is b
                np.testing.assert_allclose(quad[:, 0, :3], pos.reshape(-1, 4, 3)[:, 2], atol=1e-5)
                self.assertEqual(particles_unity.line_params(p)[0]["name"], "_Drift")
                continue
            if p["emitter"] == "burst":
                d, origin, span = particles_unity.burst(spec, spec["bursts"][0])
                self.assertEqual(origin, [0.0, 2.0, 3.0])
                self.assertGreater(d["burst"], 0)
                systems = [d]
            else:
                systems = particles_unity.continuous(spec)
            for d in systems:
                json.dumps(d)
                self.assertEqual(len(d["colors"]) % 4, 0)
                tile, last = d["renderer"]["tile"], d["renderer"]["tileLast"]
                self.assertTrue(tile == -1 or 0 <= tile <= last < 15, key)
                if p["shape"] in pts.SHAPES_3D:
                    self.assertEqual(len(d["renderer"]["meshes"]), len(pts.shapes_of(p)), key)
                self.assertIn(d["shape"]["type"], ("Sphere", "Hemisphere", "Circle", "Box", "Cone"))
                if p.get("radial"):                          # pulled toward its own ring's centre
                    self.assertLess(d["velocity"]["radial"][0], 0, key)
                    self.assertAlmostEqual(d["velocity"]["offsetY"], d["shape"]["position"][1], 6)
                if p.get("steps"):                           # one moving axis per segment, both curves alike
                    n = d["steps"]["n"]
                    lo, hi = np.reshape(d["steps"]["lo"], (3, n)), np.reshape(d["steps"]["hi"], (3, n))
                    self.assertTrue(((hi != 0).sum(axis=0) == 1).all(), key)
                    np.testing.assert_array_equal(lo, -hi)
                if p.get("tail"):
                    self.assertTrue(0 < d["trail"]["ratio"] <= 1 and d["trail"]["width"] > 0, key)
            if p.get("steps"):
                self.assertEqual(len(systems), 3, key)
                self.assertEqual(len({json.dumps(d["steps"]) for d in systems}), 3, key)
            if p.get("levels"):
                self.assertEqual(len(systems), len(p["levels"]), key)
            if p.get("opacity") is not None:                     # faint: the colours' alpha
                self.assertTrue(all(abs(a - p["opacity"]) < 1e-9 for a in systems[0]["colors"][3::4]), key)
            if p["emitter"] == "sphere" and p.get("direction") == "up":
                self.assertEqual(systems[0]["speed"], [0.0, 0.0])
                self.assertEqual(systems[0]["velocity"]["y"], [float(x) for x in p["speed"]])
            if p["emitter"] == "cone_pair":                      # left and right cones, beams stretched forward
                self.assertEqual(len(systems), 2, key)
                for d, side in zip(systems, (-1.0, 1.0)):
                    self.assertEqual(d["shape"]["type"], "Cone")
                    self.assertAlmostEqual(d["shape"]["angle"], p["cones"]["spread"])
                    self.assertAlmostEqual(d["shape"]["position"][0], side * p["cones"]["x"])
                    rx, ry, _ = (math.radians(a) for a in d["shape"]["rotation"])
                    axis = [math.cos(rx) * math.sin(ry), -math.sin(rx), math.cos(rx) * math.cos(ry)]   # Unity +Z turned
                    np.testing.assert_allclose(axis, convert.pos(pts.cone_axis(p, side)), atol=1e-6)
                    self.assertEqual(d["renderer"]["mode"], "Stretch")
                    self.assertAlmostEqual(-d["renderer"]["length"] * p["size"][0], p["beam"]["length"])
            if p.get("size3d"):
                self.assertEqual(systems[0]["size3d"], [p["size3d"][0][0], p["size3d"][0][1], p["size3d"][2][0],
                                                        p["size3d"][2][1], p["size3d"][1][0], p["size3d"][1][1]])
                self.assertTrue(systems[0]["tumble"])
            if p["emitter"] == "point_orbit":                    # a point per height, orbiting
                self.assertEqual(len(systems), 2, key)
                for d in systems:
                    self.assertGreater(d["velocity"]["orbitalY"][0], 0, key)
                    self.assertAlmostEqual(np.hypot(d["shape"]["position"][0], d["shape"]["position"][2]),
                                           p["radius"][0], 5)


class TestManifest(unittest.TestCase):
    def build(self, persist=""):
        lines = inputs(12, sec_len=16.0, persist=persist)
        duration = lines[-1].end + 2.0
        secs = [model.SectionInput(a, b, "verse") for a, b in sections_for(duration, 16.0)]
        plan = planner.plan(lines, secs, duration, 4, bpm=120, settings=model.Settings(mood="pop"))
        baked = bake.bake(plan, metrics)
        sections = [{"index": i, "label": f"S{i}", "kind": "verse", "start": a, "end": b}
                    for i, (a, b) in enumerate(plan.sections)]
        doc = manifest.build(baked, plan, sections, [], {"title": "t"}, {"materialMode": "VRCHAT"},
                             [{"name": "_TopA", "values": [0.1, 0.2, 0.3]}])
        return plan, baked, doc

    def test_structure(self):
        plan, baked, doc = self.build()
        self.assertEqual(len(doc["clips"]), len(plan.sections) * 4)
        ids = {n["id"] for n in doc["nodes"]}
        for n in doc["nodes"]:
            self.assertTrue(n["parent"] == -1 or n["parent"] in ids)
            self.assertIn(n["category"], manifest.CATEGORIES)
        names = {}
        for n in doc["nodes"]:
            key = (n["parent"], n["name"])
            self.assertNotIn(key, names, "sibling names must be unique (animation paths)")
            names[key] = 1
        json.dumps(doc)
        for c in doc["clips"]:
            for cv in c["curves"]:
                self.assertEqual(len(cv["values"]), len(cv["times"]) * len(cv["fields"]))
                self.assertTrue(all(0 <= t <= 16.0 + 1e-6 for t in cv["times"]))

    def test_text_is_gone_when_the_song_ends(self):
        """Lines kept to the end of the last section leave before the song ends, and the last clip switches them
        off (it has no next clip to do it)."""
        lines = inputs(12, sec_len=24.0, persist="section")           # the last section holds the last 6 lines
        duration = lines[-1].end + 2.0
        secs = [model.SectionInput(0.0, 24.0, "verse"), model.SectionInput(24.0, duration, "chorus")]
        plan = planner.plan(lines, secs, duration, 4, bpm=120, settings=model.Settings(mood="pop"))
        baked = bake.bake(plan, metrics)
        sections = [{"index": i, "label": f"S{i}", "kind": "verse", "start": a, "end": b}
                    for i, (a, b) in enumerate(plan.sections)]
        doc = manifest.build(baked, plan, sections, [], {"title": "t"}, {"materialMode": "VRCHAT"}, [])
        last = len(plan.sections) - 1
        kept = [lp for lp in plan.lines if lp.persist and lp.section_index == last]
        self.assertTrue(kept)
        self.assertTrue(all(lp.end <= plan.duration - planner.END_GAP + 1e-6 for lp in plan.lines))
        self.assertTrue(plan.emitters and all(world.gone(e) <= plan.duration - planner.END_GAP + 1e-6
                                              for e in plan.emitters))       # particles too (Unity holds the end)
        length = plan.sections[last][1] - plan.sections[last][0]
        for cat in ("text", "particles", "gimmicks"):
            clip = next(c for c in doc["clips"] if c["section"] == last and c["category"] == cat)
            switches = [cv for cv in clip["curves"] if cv["attr"] == "m_IsActive"]
            self.assertTrue(switches or cat == "gimmicks", cat)
            for cv in switches:
                self.assertAlmostEqual(cv["times"][-1], length, 3)
                self.assertEqual(cv["values"][-1], 0.0, (cat, cv["node"]))
            for cv in clip["curves"]:
                if cv["attr"].startswith("EmissionModule.rateOverTime"):
                    self.assertEqual(cv["values"][-1], 0.0, cv["node"])

    def test_clips_start_where_the_track_is(self):
        """The first key of every clip curve equals the baked track at the section start (self-contained clips)."""
        plan, baked, doc = self.build(persist="section")
        by_id = {n["id"]: n for n in doc["nodes"]}
        name_to_node = {}
        b = manifest.Builder(baked)
        b.build_nodes([])
        node_of = {v: k for k, v in b.ids.items()}
        tracks = {(t.node, t.prop): t for t in baked.tracks}
        checked = 0
        for c in doc["clips"]:
            s0 = plan.sections[c["section"]][0]
            for cv in c["curves"]:
                if cv["attr"] != "m_LocalPosition":
                    continue
                tr = tracks.get((node_of[cv["node"]], "location"))
                if tr is None:
                    continue
                want = convert.pos(manifest._value_at(tr.times, tr.values, tr.interp, s0))
                np.testing.assert_allclose(cv["values"][:3], want, atol=2e-5)
                checked += 1
        self.assertGreater(checked, 20)

    def test_visible_nodes_are_in_their_section_clip(self):
        plan, baked, doc = self.build()
        b = manifest.Builder(baked)
        b.build_nodes([])
        for si, (s0, s1) in enumerate(plan.sections):
            t = (s0 + s1) / 2
            shown = {nid for nid in bake.world_positions(baked, t)}
            clip_nodes = {cv["node"] for c in doc["clips"] if c["section"] == si for cv in c["curves"]}
            for nid in shown:
                self.assertIn(b.ids[nid], clip_nodes, (si, nid))

    def test_dome_bindings(self):
        _, _, doc = self.build()
        attrs = {cv["attr"] for c in doc["clips"] for cv in c["curves"] if c["category"] == "background"}
        for a in ("material._TopA", "material._Progress", "material._Next", "material._CueDir", "material._FlashColor"):
            self.assertIn(a, attrs)
        self.assertNotIn("material.None", attrs)


    def test_mask_bindings(self):
        from lyric_live_builder.export_unity import manifest
        t, f, v = manifest.binding("glyph_tmp", "mask", np.array([[0.0], [1.0]]))[:3], None, None
        self.assertEqual(t[:2], ("MeshRenderer", "material._Mask"))
        typ, attr, fields, vals = manifest.binding("glyph", "mask_box", np.array([[-1.0, -2.0, 3.0, 4.0]]))
        self.assertEqual((attr, fields), ("material._MaskBox", ["x", "y", "z", "w"]))
        np.testing.assert_allclose(vals, [[-1.0, -2.0, 3.0, 4.0]])           # glyph coordinates: not converted
        self.assertEqual(manifest.binding("glyph", "mask_shape", np.zeros((1, 4)))[1], "material._MaskShape")


class TestMobile(unittest.TestCase):
    def plan(self, hold="still", **over):
        lines = inputs(10, sec_len=16.0, hold=hold, **over)
        duration = lines[-1].end + 2.0
        secs = [model.SectionInput(a, b, "verse") for a, b in sections_for(duration, 16.0)]
        return planner.plan(lines, secs, duration, 4, bpm=120, settings=model.Settings(mood="pop"))

    def test_still_lines_switch_to_one_mesh(self):
        plan = self.plan()
        b = bake.bake(plan, metrics, mobile=True)
        lines = [n for n in b.nodes if n.kind == "line_mesh"]
        self.assertGreater(len(lines), 5)
        normal = bake.bake(plan, metrics)
        self.assertFalse([n for n in normal.nodes if n.kind == "line_mesh"])
        self.assertEqual(len(normal.guides), len(b.guides))        # the guides still see the letters
        act = {t.node: t for t in b.tracks if t.prop == "active"}
        for ln in lines:
            t_on, t_off = act[ln.id].times[1], act[ln.id].times[2]
            t = (t_on + t_off) / 2
            shown = bake.world_positions(b, t)
            self.assertFalse([k for k in shown if k.startswith(ln.parent + "_g")], "letters hidden while the line mesh shows")
            self.assertTrue([k for k in bake.world_positions(b, t_on - 0.05) if k.startswith(ln.parent + "_g")])
        self.assertFalse([n for n in bake.bake(self.plan(hold="float"), metrics, mobile=True).nodes if n.kind == "line_mesh"])
        self.assertFalse([n for n in bake.bake(plan, metrics, mobile=True, tmp=True).nodes if n.kind == "line_mesh"])

    def test_mobile_manifest(self):
        plan = self.plan()
        b = bake.bake(plan, metrics, mobile=True)
        sections = [{"index": i, "label": f"S{i}", "kind": "verse", "start": a, "end": c} for i, (a, c) in enumerate(plan.sections)]
        full = manifest.build(b, plan, sections, [], {}, {"mobile": False}, [])
        mob = manifest.build(b, plan, sections, [], {}, {"mobile": True, "particleRatio": 0.5}, [])
        text_full = [m for m in full["materials"] if m["shader"] == "text"]
        text_mob = [m for m in mob["materials"] if m["shader"] == "text"]
        self.assertEqual(len(text_mob), 1)
        self.assertGreaterEqual(len(text_full), 1)
        self.assertTrue(any(m["shader"] == "text_vc" for m in mob["materials"]))
        glyphs = {n["id"] for n in mob["nodes"] if n["kind"] == "glyph"}
        coloured = {cv["node"] for c in mob["clips"] for cv in c["curves"] if cv["attr"] == "material._Color"}
        self.assertTrue(glyphs <= coloured, "every letter carries its colour on the shared material")
        ps = lambda doc: sum(json.loads(n["particles"])["max"] for n in doc["nodes"] if n["particles"])
        self.assertLess(ps(mob), ps(full) * 0.6)

    def test_tmp_and_guides(self):
        plan = self.plan(persist="section")
        b = bake.bake(plan, metrics, tmp=True)
        tmp = {k: "body" for k, src in b.meshes.items() if src.kind == "glyph2d"}
        sections = [{"index": i, "label": f"S{i}", "kind": "verse", "start": a, "end": c} for i, (a, c) in enumerate(plan.sections)]
        doc = manifest.build(b, plan, sections, [], {}, {"tmp": True}, [], fonts=[{"key": "body", "file": "fonts/x.ttf", "chars": "夜"}], tmp_fonts=tmp)
        letters = [n for n in doc["nodes"] if n["tmp"]]
        self.assertTrue(letters and all(n["kind"] == "glyph_tmp" and n["tmpFont"] == "body" and not n["mesh"] for n in letters))
        types = {cv["type"] for c in doc["clips"] for cv in c["curves"] if cv["node"] in {n["id"] for n in letters} and cv["attr"] == "m_fontColor"}
        self.assertEqual(types, {"TextMeshPro"})
        ids = {n["id"]: n for n in doc["nodes"]}
        for g in doc["guides"]:
            self.assertEqual(ids[g["node"]]["kind"], "group")
            self.assertEqual((len(g["target"]), g["motes"] > 0), (3, True))
            self.assertLess(g["tOn"], g["tHit"])


if __name__ == "__main__":
    unittest.main()
