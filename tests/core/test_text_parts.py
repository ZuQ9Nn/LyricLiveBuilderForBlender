"""Phase 2 core: part contracts, layouts, planner and bake (no Blender)."""
import math
import time
import unittest

import numpy as np

from lyric_live_builder.core import bake, lyrics, model, planner, registry, xform
from lyric_live_builder.core.rng import Rng


class FakeMetrics:
    def advance_em(self, ch):
        return 0.3 if ch.isspace() else 0.55 if lyrics.is_latin(ch) else 1.0

    def vadvance_em(self, ch):
        return 1.0


def metrics(role):
    return FakeMetrics()


LYRICS = ["夜明けの色を覚えてる", "ほどけた声が遠くで鳴った", "ねえ、まだ間に合うかな", "透明なままじゃ終われない",
          "光の粒を集めて", "きみの名前を呼ぶよ", "Hello world again", "窓の外はまだ青くて"]


def inputs(n_lines=24, gap=4.0, is_3d=False, sec_len=32.0, **over):
    out = []
    for i in range(n_lines):
        text = LYRICS[i % len(LYRICS)]
        s = 2.0 + i * gap
        ct = [s + k * 0.12 for k in range(len(text))]
        out.append(model.LineInput(index=i, text=text, start=s, end=s + gap, section_index=int(s // sec_len),
                                   char_times=ct, emph_words=["透明"] if "透明" in text else [], is_3d=is_3d, **over))
    return out


def sections_for(duration, sec_len=32.0):
    n = int(math.ceil(duration / sec_len))
    return [(k * sec_len, min(duration, (k + 1) * sec_len)) for k in range(n)]


def make(n_lines=24, seed=7, sec_len=32.0, **kw):
    lines = inputs(n_lines, sec_len=sec_len, **kw)
    duration = lines[-1].end + 2.0
    p = planner.plan(lines, sections_for(duration, sec_len), duration, seed, bpm=120)
    return p, bake.bake(p, metrics)


class TestContracts(unittest.TestCase):
    def ctx(self, n=6):
        return registry.MotionCtx(n=n, rest=np.zeros((n, 3)), em=0.2, start=1.0, end=5.0,
                                  char_times=np.linspace(1, 2, n), bpm=120, seed=3)

    def assert_identity(self, d, msg):
        np.testing.assert_allclose(d.loc, 0, atol=1e-9, err_msg=msg)
        np.testing.assert_allclose(np.abs(d.rot[..., 0]), 1, atol=1e-9, err_msg=msg)
        np.testing.assert_allclose(d.scale, 1, atol=1e-9, err_msg=msg)
        np.testing.assert_allclose(d.alpha, 1, atol=1e-9, err_msg=msg)

    def test_counts(self):
        self.assertEqual(len(registry.keys("enter")), 10)
        self.assertEqual(len(registry.keys("hold")), 6)
        self.assertEqual(len(registry.keys("exit")), 7)
        self.assertEqual(len([p for p in registry.parts("layout") if not p.only_3d]), 7)
        self.assertEqual(len([p for p in registry.parts("layout") if p.only_3d]), 6)

    def test_enter_identity_at_1_and_hidden_or_moved_at_0(self):
        c = self.ctx()
        for part in registry.parts("enter"):
            self.assert_identity(part.evaluate(c, np.ones((6, 3))), part.key)
            d0 = part.evaluate(c, np.zeros((6, 3)))
            changed = (d0.alpha < 0.5).any() or (np.abs(d0.scale - 1) > 0.1).any() or (np.abs(d0.loc) > 1e-3).any()
            self.assertTrue(changed, part.key)

    def test_exit_identity_at_0(self):
        c = self.ctx()
        for part in registry.parts("exit"):
            self.assert_identity(part.evaluate(c, np.zeros((6, 3))), part.key)
            d1 = part.evaluate(c, np.ones((6, 3)))
            gone = (d1.alpha < 0.05).all() or (np.abs(d1.scale) < 0.05).all()
            self.assertTrue(gone, part.key)

    def test_hold_identity_at_0_and_finite(self):
        c = self.ctx()
        for part in registry.parts("hold"):
            self.assert_identity(part.evaluate(c, np.zeros((6, 3))), part.key)
            d = part.evaluate(c, np.linspace(0, 30, 90)[None].repeat(6, 0))
            self.assertTrue(np.isfinite(d.loc).all() and np.isfinite(d.rot).all(), part.key)

    def test_no_motion_comes_toward_the_viewer(self):
        c = self.ctx()
        p = np.linspace(0, 1, 21)[None].repeat(6, 0)
        for kind in ("enter", "exit"):
            for part in registry.parts(kind):
                self.assertGreaterEqual(part.evaluate(c, p).loc[..., 1].min(), -1e-9, part.key)


class TestLayouts(unittest.TestCase):
    def ctx(self, text="夜明けの色を覚えてる", distance=3.5, is_3d=True, anchor=(0.0, 0.0)):
        m = FakeMetrics()
        em = 2 * distance * math.tan(math.radians(model.ANGLE_BODY) / 2)
        return registry.LayoutCtx(text=text, adv=[m.advance_em(c) for c in text], vadv=[1.0] * len(text),
                                  em=em, distance=distance, eye=1.5, is_3d=is_3d, depth=0.15,
                                  chunks=lyrics.chunk_text(text), char_times=[float(i) for i in range(len(text))],
                                  anchor=anchor)

    def test_every_layout_places_every_visible_char(self):
        for part in registry.parts("layout"):
            c = self.ctx()
            params = part.plan(Rng(1), c)
            pl = part.place(c, params)
            self.assertEqual(sorted(g.char_index for g in pl.glyphs), list(range(len(c.text))), part.key)
            self.assertGreater(pl.em, 0.01, part.key)

    def test_front_size_is_the_visual_angle(self):
        c = self.ctx(text="あい", distance=3.5)
        pl = registry.get("layout", "front").place(c, {})
        self.assertAlmostEqual(pl.em, 2 * 3.5 * math.tan(math.radians(model.ANGLE_BODY) / 2))
        np.testing.assert_allclose(pl.loc, [0, 3.5, 1.5], atol=1e-9)
        # the face (-y) points back at the eye
        np.testing.assert_allclose(xform.rotate(pl.rot, [0, -1, 0]), [0, -1, 0], atol=1e-9)

    def test_long_line_is_shrunk_to_70_degrees(self):
        c = self.ctx(text="あ" * 60, distance=1.2)
        pl = registry.get("layout", "front").place(c, {})
        half = 60 * pl.em / 2
        self.assertLessEqual(math.degrees(2 * math.atan(half / 1.2)), 70.0 + 1e-6)

    def test_side_anchor_faces_the_eye(self):
        az = math.radians(62)
        c = self.ctx(anchor=(az, 0.0))
        pl = registry.get("layout", "front").place(c, {})
        to_eye = np.array([0, 0, 1.5]) - pl.loc
        face = xform.rotate(pl.rot, [0, -1, 0])
        np.testing.assert_allclose(face, to_eye / np.linalg.norm(to_eye), atol=1e-9)

    def test_floor_faces_up(self):
        c = self.ctx()
        pl = registry.get("layout", "floor").place(c, {"distance": 2.0})
        np.testing.assert_allclose(xform.rotate(pl.rot, [0, -1, 0]), [0, 0, 1], atol=1e-9)
        self.assertLess(pl.loc[2], 0.2)

    def test_pillar_is_vertical(self):
        c = self.ctx(text="夜明けの色")
        pl = registry.get("layout", "pillar").place(c, {"side": 1, "azimuth": 0.5})
        zs = [g.loc[2] for g in pl.glyphs]
        self.assertEqual(zs, sorted(zs, reverse=True))


    def test_cube_shows_one_face_at_a_time(self):
        c = self.ctx(text="夜明けの色を覚えてる光の粒")
        part = registry.get("layout", "cube")
        params = part.plan(Rng(1), c)
        pl = part.place(c, params)
        shown = part.shown(c, params, pl)
        faces = [params["face_of"][g.char_index] for g in pl.glyphs]
        self.assertGreater(len(set(faces)), 1)
        mid = (shown[faces.index(1)][0] + shown[faces.index(1)][1]) / 2 + 0.4   # face 1 settled in front
        for f, (on, off) in zip(faces, shown):
            self.assertEqual(on <= mid < off, f == 1, f)

    def test_approach_passes_beside_over_the_whole_line(self):
        c = self.ctx(text="夜明けの色")
        c.span = (10.0, 14.0)
        part = registry.get("layout", "approach")
        params = part.plan(Rng(1), c)
        pl = part.place(c, params)
        loc, _ = part.group_motion(c, params, pl, np.array([10.0, 12.0, 14.0]))
        self.assertGreater(loc[0, 1], 20)            # far ahead at the start
        self.assertTrue(0 < loc[1, 1] < loc[0, 1])   # still on its way half-way through
        self.assertLess(loc[2, 1], 0)                # behind the viewer at the end
        self.assertGreater(abs(loc[0, 0]) - sum(c.adv) * pl.em / 2, 1.0)   # never through the viewer


class TestPlanBake(unittest.TestCase):
    def test_deterministic(self):
        a, ba = make(seed=11)
        b, bb = make(seed=11)
        self.assertEqual([(x.layout, x.enter, x.hold, x.exit, x.distance, x.persist) for x in a.lines],
                         [(x.layout, x.enter, x.hold, x.exit, x.distance, x.persist) for x in b.lines])
        self.assertEqual(len(ba.tracks), len(bb.tracks))
        for x, y in zip(ba.tracks, bb.tracks):
            self.assertEqual((x.node, x.prop), (y.node, y.prop))
            np.testing.assert_array_equal(x.values, y.values)
        c, _ = make(seed=12)
        self.assertNotEqual([x.layout for x in a.lines], [x.layout for x in c.lines])

    def test_overrides_are_kept(self):
        p, _ = make(n_lines=6, is_3d=True, layout="slanted_wall", enter="fade", hold="float", exit="topple", distance="far")
        for ln in p.lines:
            self.assertEqual((ln.layout, ln.enter, ln.hold, ln.exit, ln.distance), ("slanted_wall", "fade", "float", "topple", "far"))
        p, _ = make(n_lines=6, persist="section")
        self.assertTrue(all(ln.persist for ln in p.lines))
        self.assertEqual(len({ln.anchor for ln in p.lines if ln.section_index == 0}),
                         len([ln for ln in p.lines if ln.section_index == 0]))

    def test_kept_line_appears_in_front_then_glides_to_its_slot(self):
        p, b = make(n_lines=6, persist="section")
        eye = np.array([0, 0, model.EYE_HEIGHT])
        for ln in p.lines[:-1]:
            self.assertIsNotNone(ln.glide, ln.index)
            for t, want in ((ln.glide[0] - 0.02, 0.0), (ln.glide[1] + 0.05, ln.anchor[0])):
                pos = [v for k, v in bake.world_positions(b, t).items() if k.startswith(f"line{ln.index:03d}_")]
                c = np.mean(pos, axis=0) - eye
                self.assertAlmostEqual(math.atan2(c[0], c[1]), want, delta=0.05, msg=(ln.index, t))
        self.assertIsNone(p.lines[-1].glide)              # nothing comes after it in its section

    def test_2d_lines_never_get_3d_layouts(self):
        for seed in range(5):
            p, _ = make(seed=seed)
            self.assertFalse(any(registry.get("layout", ln.layout).only_3d for ln in p.lines))

    def test_no_overlap_and_eye_distance(self):
        for seed, is_3d, persist in [(s, d, k) for s in range(4) for d in (False, True) for k in ("", "section")]:
            p, b = make(seed=seed, is_3d=is_3d, n_lines=16, gap=3.0, sec_len=24.0, persist=persist)
            em = {n.id: n.scale[0] for n in b.nodes if n.kind == "glyph"}
            for t in np.arange(0, b.duration, 0.2):
                pos = bake.world_positions(b, t)
                ids = list(pos)
                for k, a in enumerate(ids):
                    d = np.linalg.norm(pos[a] - np.array([0, 0, 1.5]))
                    self.assertGreaterEqual(d, model.MIN_EYE_DISTANCE - 1e-6, (seed, a, t))
                    for c in ids[k + 1:]:
                        if a.split("_")[0] == c.split("_")[0]:
                            continue                    # same line
                        gap = np.linalg.norm(pos[a] - pos[c])
                        self.assertGreater(gap, 0.45 * (em[a] + em[c]), (seed, is_3d, a, c, round(t, 2)))

    def test_decimation_tolerance(self):
        times = np.linspace(0, 4, 121)
        values = np.stack([np.sin(times * 3), np.cos(times * 2), times ** 2 * 0.01], axis=1)
        idx = bake.rdp(times, values, 0.001)
        self.assertLess(len(idx), len(times))
        for c in range(3):
            approx = np.interp(times, times[idx], values[idx, c])
            self.assertLessEqual(np.abs(approx - values[:, c]).max(), 0.001 + 1e-12)

    def test_tracks_are_sane(self):
        p, b = make(n_lines=8)
        glyphs = [n for n in b.nodes if n.kind == "glyph"]
        self.assertEqual(len(glyphs), sum(len(ln.text.replace(" ", "")) for ln in p.lines))
        for tr in b.tracks:
            self.assertTrue(np.all(np.diff(tr.times) >= 0), tr.node)
            self.assertTrue(np.isfinite(tr.values).all(), tr.node)
        # emphasised characters get the accent colour
        line = next(ln for ln in p.lines if "透明" in ln.text)
        want = tuple(line.colors["accent"])
        accent = [n for n in glyphs if n.parent == f"line{line.index:03d}" and np.allclose(n.color[:3], want)]
        self.assertEqual(len(accent), 2)

    def test_speed_four_minutes(self):
        t = time.perf_counter()
        make(n_lines=60, gap=4.0)
        self.assertLess(time.perf_counter() - t, 10.0)


if __name__ == "__main__":
    unittest.main()
