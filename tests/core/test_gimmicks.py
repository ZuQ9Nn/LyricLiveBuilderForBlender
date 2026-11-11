"""Phase 6 core: keywords, built-in shapes, gimmick planning and baking (no Blender)."""
import collections
import unittest

import numpy as np

from lyric_live_builder.core import bake, gimmick_shapes as shapes, meshes, model, planner, synonyms
from lyric_live_builder.core.parts import gimmicks
from tests.core.test_text_parts import inputs, metrics, sections_for


def lines_with(*texts, **kw):
    lines = inputs(len(texts))
    for ln, text in zip(lines, texts):
        ln.text = text
        ln.chunks = None
        ln.char_times = None
        for k, v in kw.items():
            setattr(ln, k, v)
    return lines


def make(lines, duration=None, settings=None, seed=3):
    duration = duration or lines[-1].end + 3.0
    p = planner.plan(lines, sections_for(duration), duration, seed, settings=settings)
    return p, bake.bake(p, metrics)


class TestSynonyms(unittest.TestCase):
    def test_spellings_match_one_tag(self):
        for text in ("星が降る", "ほしが降る", "ホシが降る", "スターが降る", "ｽﾀｰ", "the STARS", "☆"):
            self.assertEqual([t for t, _ in synonyms.find(text)], ["star"], text)

    def test_words_that_only_contain_a_keyword_do_not_match(self):
        for text in ("ほしいものは", "starlight", "君の言葉", "月曜の朝", "はなしをしよう", "どこまでもゆきたい"):
            self.assertEqual(synonyms.find(text), [], text)

    def test_longest_word_wins_and_order_follows_the_lyric(self):
        self.assertEqual(synonyms.find("三日月と雲")[0], ("moon", "三日月"))
        self.assertEqual([t for t, _ in synonyms.find("雲の上の星")], ["cloud", "star"])

    def test_user_words_and_tags(self):
        extra = synonyms.parse_user("cat=ミケ,タマ; fox=きつね")
        self.assertEqual(synonyms.find("ミケときつね", extra), [("cat", "ミケ"), ("fox", "きつね")])
        self.assertEqual((synonyms.canonical("猫"), synonyms.canonical("CAT"), synonyms.canonical("ふくろう")),
                         ("cat", "cat", "ふくろう"))


class TestShapes(unittest.TestCase):
    def test_every_shape_is_sound(self):
        self.assertTrue(20 <= len(shapes.SHAPES) <= 30)
        for key in shapes.SHAPES:
            v, f = meshes.build(f"gimmick:{key}")
            self.assertLessEqual(sum(len(x) - 2 for x in f), 1000, key)
            self.assertTrue(np.isfinite(v).all(), key)
            self.assertAlmostEqual(v[:, 2].min(), 0.0, msg=key)
            self.assertAlmostEqual(v[:, 2].max(), 1.0, msg=key)
            self.assertLess(np.abs((v[:, :2].min(axis=0) + v[:, :2].max(axis=0)) / 2).max(), 1e-9, key)

    def test_primitives_are_closed_and_face_outward(self):
        a = np.linspace(0, np.pi, 6)
        arc = np.stack([np.cos(a), np.sin(a)], axis=1)
        for v, f in (shapes.box(1, 1, 1), shapes.lathe([(0, 0), (1, 0), (1, 1), (0, 1)], 8), shapes.torus(1, 0.2),
                     shapes.plate(shapes._star_outline(5, 0.5, 0.2), 0.1), shapes.strip(arc, arc * 0.5, 0.2)):
            edges = collections.Counter((p, q) for x in f for p, q in zip(x, x[1:] + x[:1]))
            self.assertTrue(all(edges.get((q, p)) == n for (p, q), n in edges.items()))
            volume = sum(np.dot(v[x[0]], np.cross(v[x[k]], v[x[k + 1]])) for x in f for k in range(1, len(x) - 1))
            self.assertGreater(volume, 0)


class TestPlan(unittest.TestCase):
    def test_keyword_brings_its_object_at_full_strength(self):
        lines = lines_with("星が降る夜に", "何もない", "月を見ていた")
        p, _ = make(lines, settings=model.Settings(fx={"gimmick": 1.0}))
        self.assertEqual([(g["line"], g["tag"], g["source"]) for g in p.gimmicks], [(0, "star", "builtin"), (2, "moon", "builtin")])

    def test_source_order_user_builtin_emblem(self):
        lines = lines_with("星が降る", "猫がいた", "犬がいた")
        assets = {"star": {"file": "a.blend", "name": "S"}, "dog": {"file": "a.blend", "name": "D"}}
        p, b = make(lines, settings=model.Settings(fx={"gimmick": 1.0}, user_assets=assets))
        self.assertEqual([g["source"] for g in p.gimmicks], ["user", "emblem", "user"])
        self.assertEqual(p.gimmicks[1]["word"], "猫")
        self.assertEqual(b.meshes["user:S"].args, assets["star"])

    def test_line_settings(self):
        lines = lines_with("何もない", "星が降る", "言葉だけ")
        lines[0].gimmick, lines[0].gimmick_show = "gem", "flip"
        lines[1].gimmick = "none"
        lines[2].gimmick, lines[2].gimmick_word = "emblem", "言葉"
        p, b = make(lines, settings=model.Settings(fx={"gimmick": 0.0}))
        self.assertEqual([(g["line"], g["tag"], g["show"]) for g in p.gimmicks][0], (0, "gem", "flip"))
        self.assertEqual(p.gimmicks[1]["source"], "emblem")
        letters = [n for n in b.nodes if n.parent == "gim001" and n.kind == "glyph"]
        self.assertEqual([n.name for n in letters], ["言", "葉"])
        self.assertTrue(all(b.meshes[n.mesh].kind == "glyph3d" for n in letters))
        self.assertTrue(any(n.id == "gim001_base" for n in b.nodes))

    def test_strength_section_limit_and_switches(self):
        lines = lines_with(*["星が降る"] * 10)
        none, _ = make(lines, settings=model.Settings(fx={"gimmick": 0.0}))
        some, _ = make(lines, settings=model.Settings(fx={"gimmick": 1.0}))
        self.assertEqual(none.gimmicks, [])
        per_section = collections.Counter(some.lines[g["line"]].section_index for g in some.gimmicks)
        self.assertLessEqual(max(per_section.values()), 4)
        off, _ = make(lines, settings=model.Settings(fx={"gimmick": 1.0}, disabled={"gimmick": {"star"}}))
        self.assertEqual(off.gimmicks, [])

    def test_objects_stand_beside_the_line(self):
        import math
        lines = lines_with("星が降る", "星が降る夜に君の名前を呼んでいた", "星", "星が降る夜に君の名前を呼んでいた空")
        for ln in lines:                                 # a flat line: as wide as its letters (big layouts spread wider)
            ln.layout, ln.hold, ln.persist = "front", "still", "next"
        p, b = make(lines, settings=model.Settings(fx={"gimmick": 1.0}))
        self.assertTrue(p.gimmicks)
        for g in p.gimmicks:
            ln = p.lines[g["line"]]
            off = abs((math.degrees(g["az"] - ln.anchor[0]) + 180) % 360 - 180)
            # the line's letters, measured where they really are (a long line is shrunk to 70°)
            pos = [v for k, v in bake.world_positions(b, ln.start + 1.5).items() if k.startswith(f"line{ln.index:03d}_")]
            half = max((abs(math.degrees(math.atan2(v[0], v[1]) - ln.anchor[0])) for v in pos), default=0.0)
            obj = math.degrees(math.atan2(g["size"] / 2, gimmicks.RADIUS))
            self.assertGreaterEqual(off, half + obj, (ln.text, off, half, obj))
            self.assertGreaterEqual(off, gimmicks.SIDE[0])

    def test_reroll_stage_leaves_the_text_alone(self):
        lines = lines_with(*["星が降る"] * 6)
        a, _ = make(lines, settings=model.Settings(fx={"gimmick": 1.0}))
        c, _ = make(lines, settings=model.Settings(fx={"gimmick": 1.0}, stage_offsets={5: 1}))
        self.assertEqual([x.layout for x in a.lines], [x.layout for x in c.lines])
        self.assertNotEqual([g["az"] for g in a.gimmicks], [g["az"] for g in c.gimmicks])


class TestBake(unittest.TestCase):
    def shown(self, show, tag="tree"):
        lines = lines_with("何もない", "何もない", "何もない")
        lines[1].gimmick, lines[1].gimmick_show = tag, show
        p, b = make(lines, settings=model.Settings(fx={"gimmick": 0.0}))
        tracks = {(t.node, t.prop): t for t in b.tracks}
        return p.gimmicks[0], b, tracks

    def test_every_way_of_appearing_ends_at_its_place(self):
        for show in gimmicks.SHOW_ORDER:
            g, b, tracks = self.shown(show)
            group = next(n for n in b.nodes if n.id == "gim000")
            mid = g["start"] + gimmicks.SHOWS[show]["dur"] + 0.1
            self.assertLess(mid, g["end"] - 0.8, show)
            self.assertAlmostEqual(np.hypot(group.loc[0], group.loc[1]), gimmicks.RADIUS, msg=show)
            for prop, rest in (("location", group.loc), ("scale", (1, 1, 1))):
                tr = tracks.get(("gim000", prop))
                if tr is None:
                    continue
                at = [np.interp(mid, tr.times, tr.values[:, c]) for c in range(3)]
                self.assertLess(np.abs(np.array(at) - rest).max(), 0.02, (show, prop))
            self.assertTrue(any(k[0].startswith("gim000_") and k[1] == "active" for k in tracks))
            self.assertTrue(group.default_active)
            self.assertFalse(any(n.default_active for n in b.nodes if n.parent == "gim000"))

    def test_motion_differs_at_the_start(self):
        g, _, tr = self.shown("sky")
        self.assertGreater(tr[("gim000", "location")].values[0, 2], 4.0)
        _, _, tr = self.shown("flip")
        q = tr[("gim000", "rotation")].values
        self.assertGreater(abs(np.dot(q[0], q[-1])) * -1 + 1, 0.5)                  # half a turn apart
        _, b, tr = self.shown("open")
        self.assertEqual(sum(n.name.startswith("Wall") for n in b.nodes), 4)
        self.assertIn(("gim000_w0", "rotation"), tr)
        _, _, tr = self.shown("dissolve")
        a = tr[("gim000_obj", "color")].values[:, 3]
        self.assertLess(a[0], 0.1)
        self.assertGreater(a.max(), 0.99)
        self.assertLess(a[-1], 0.1)

    def test_spectrum_bars(self):
        lines = lines_with("何もない", "何もない")
        frames = 50 * 20
        levels = np.tile(np.sin(np.arange(frames) * 0.2)[:, None] * 0.5 + 0.5, (1, 24)).astype(np.float32)
        secs = [model.SectionInput(0.0, 10.0, "verse"), model.SectionInput(10.0, 20.0, "chorus")]
        settings = model.Settings(fx={"spectrum": "chorus"}, spectrum=levels, energy_rate=50.0)
        p = planner.plan(lines, secs, 20.0, 3, settings=settings)
        b = bake.bake(p, metrics)
        bars = [n for n in b.nodes if n.id.startswith("bar")]
        self.assertEqual(len(bars), gimmicks.BARS)
        tracks = {(t.node, t.prop): t for t in b.tracks}
        h = tracks[("bar03", "scale")]
        self.assertTrue((h.times >= 10.0).all())
        self.assertGreater(np.ptp(h.values[:, 2]), 0.3)
        self.assertEqual(float(tracks[("bar03", "active")].values[0, 0]), 0.0)
        late = [model.SectionInput(0.0, 25.0, "verse"), model.SectionInput(25.0, 30.0, "chorus")]    # past the audio
        self.assertFalse([n for n in bake.bake(planner.plan(lines, late, 30.0, 3, settings=settings), metrics).nodes
                          if n.id.startswith("bar")])
        settings.fx["spectrum"] = "off"
        self.assertFalse([n for n in bake.bake(planner.plan(lines, secs, 20.0, 3, settings=settings), metrics).nodes
                          if n.id.startswith("bar")])


if __name__ == "__main__":
    unittest.main()
