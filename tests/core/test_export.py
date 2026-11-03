"""Phase 4 (Python side, no Blender): conversion, LLBM meshes, particle descriptions, manifest clips."""
import json
import unittest

import numpy as np

from lyric_live_builder.core import bake, meshes, model, planner, xform
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
        pos, nrm, idx = meshbin.decode(data)
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
            pos, _, _ = meshbin.decode(blob, e["offset"])
            self.assertGreater(len(pos), 10)


class TestParticles(unittest.TestCase):
    def test_every_preset_describes(self):
        st = model.Settings()
        pal = {r: "#FFFFFF" for r in ("fg", "sub", "accent", "accent2", "ghostA", "ghostB", "white", "bg")}
        from lyric_live_builder.core import world
        for key, p in pts.PRESETS.items():
            spec = world.emitter(key, 1.0, 9.0, 5, pal, st, bursts=[{"t": 2.0, "origin": [0.0, 3.0, 2.0]}]
                                 if p["emitter"] == "burst" else None)
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
                tile = d["renderer"]["tile"]
                self.assertTrue(tile == -1 or 0 <= tile < 15, key)
                self.assertIn(d["shape"]["type"], ("Sphere", "Hemisphere", "Circle", "Box"))


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


if __name__ == "__main__":
    unittest.main()
