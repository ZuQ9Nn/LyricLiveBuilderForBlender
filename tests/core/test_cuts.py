"""A line shown in several cuts (design §5.5.1)."""
import unittest
from contextlib import contextmanager

import numpy as np

from lyric_live_builder.core import bake, lyrics, model, planner

from .test_text_parts import LYRICS, inputs, make, metrics, sections_for


def plan_of(lines, seed=7):
    duration = lines[-1].end + 2.0
    return planner.plan(lines, sections_for(duration), duration, seed, bpm=120)


def with_cuts(cuts, line=4, n=12, **over):
    lines = inputs(n)
    lines[line].cuts = cuts
    for key, value in over.items():
        setattr(lines[line], key, value)
    return lines


@contextmanager
def text_scale(scale):
    keep = model.TEXT_SCALE
    model.TEXT_SCALE = scale
    try:
        yield
    finally:
        model.TEXT_SCALE = keep


def whole(plan):
    return [(x.layout, x.enter, x.hold, x.exit, x.distance, x.start, x.end) for x in plan.lines]


class SplitLine(unittest.TestCase):
    def test_keeps_the_text_in_order(self):
        for text in ("夜明けの色を覚えてる", "透明なままじゃ終われない", "Hello world again", "ねえ、まだ間に合うかな", "ああ ああ ああ"):
            for n in range(1, 7):
                parts = lyrics.split_line(text, lyrics.chunk_text(text), n)
                self.assertLessEqual(len(parts), n)
                self.assertEqual("".join(p for _, p in parts).replace(" ", ""), text.replace(" ", ""))
                for off, piece in parts:
                    self.assertEqual(text[off:off + len(piece)], piece)
                self.assertEqual([o for o, _ in parts], sorted({o for o, _ in parts}))

    def test_makes_the_count_asked_for(self):
        for n in range(1, 7):
            self.assertEqual(len(lyrics.split_line("夜明けの色を覚えてる", lyrics.chunk_text("夜明けの色を覚えてる"), n)), n)

    def test_never_more_than_the_letters(self):
        self.assertEqual([p for _, p in lyrics.split_line("光を", ["光を"], 6)], ["光", "を"])

    def test_words_stay_whole(self):
        parts = lyrics.split_line("Hello world again", lyrics.chunk_text("Hello world again"), 2)
        self.assertEqual([p for _, p in parts], ["Hello world", "again"])

    def test_manual_chunks_are_cut_points(self):
        self.assertEqual([p for _, p in lyrics.split_line("光の粒を集めて", ["光の粒を", "集めて"], 2)], ["光の粒を", "集めて"])


class Plan(unittest.TestCase):
    def test_auto_and_one_change_nothing(self):
        """A line that keeps the text size whole is not cut on Planner's Choice."""
        from lyric_live_builder.core import registry
        cap = registry.capacity(registry.get("layout", "front"))
        short = inputs(12, cuts=0)
        for ln in short:
            ln.text, ln.char_times = ln.text[:cap], ln.char_times[:cap]
        base = plan_of(short)
        self.assertTrue(all(x.cuts is None for x in base.lines))
        for ln in short:
            ln.cuts = 1
        self.assertEqual(whole(plan_of(short)), whole(base))

    def test_long_lines_are_cut_to_keep_the_text_size(self):
        """Planner's Choice cuts a line too wide for the front into parts that fit, each in a layout that keeps
        them at SIZE_KEEP of the text size or more, whatever the size setting (design §7.3)."""
        from lyric_live_builder.core import registry
        keep = model.TEXT_SCALE
        try:
            for scale in (1.0, 0.5, 1.5, 2.0):
                model.TEXT_SCALE = keep * scale
                if model.text_angle("mid") > model.MAX_LINE_ANGLE:
                    continue                                # one letter wider than a line: beyond the setting's range
                cap = registry.capacity(registry.get("layout", "front"))
                self.assertGreaterEqual(cap, 1, scale)
                p = plan_of(inputs(len(LYRICS), cuts=0))
                for x in p.lines:
                    if registry.text_width(x.text) <= cap:
                        continue
                    self.assertTrue(x.cuts, (scale, x.text))
                    self.assertEqual("".join(c.text for c in x.cuts).replace(" ", ""), x.text.replace(" ", ""))
                    for c in x.cuts:
                        w = registry.text_width(c.text)
                        self.assertLessEqual(w, cap, (scale, c.text))
                        self.assertLessEqual(w, registry.capacity(registry.get("layout", c.layout)), (scale, c.layout))
                bake.bake(p, metrics)
        finally:
            model.TEXT_SCALE = keep

    def test_hand_settings_are_not_cut_for_size(self):
        lines = inputs(12, cuts=0)
        long = "あ" * 30                                                    # wider than the front at any size
        for k in (4, 5, 6):
            lines[k].text, lines[k].char_times = long, [lines[k].start + 0.1 * i for i in range(len(long))]
        lines[4].cuts, lines[5].persist = 1, "section"
        p = plan_of(lines)
        self.assertIsNone(p.lines[4].cuts)                                  # "1": whole, even when too wide
        self.assertIsNone(p.lines[5].cuts)                                  # kept to the section end by hand
        self.assertTrue(p.lines[6].cuts)                                    # Planner's Choice: cut

    def test_slashes_cut_a_planners_choice_line(self):
        def slashed(n_parts, cuts=0, **over):
            lines = with_cuts(cuts, **over)
            text = lines[4].text
            step = max(1, len(text) // n_parts)
            lines[4].chunks = [text[i * step:(i + 1) * step if i < n_parts - 1 else len(text)] for i in range(n_parts)]
            with text_scale(0.05):                      # letters so small that only the '/' cut the line
                return lines, plan_of(lines)
        lines, p = slashed(3)
        cuts = p.lines[4].cuts
        self.assertEqual([c.text for c in cuts], lines[4].chunks)          # one cut per '/' chunk, as written
        times = lines[4].char_times or [lines[4].start + 0.05 * i for i in range(len(lines[4].text))]
        offsets = [lines[4].text.index(c) for c in lines[4].chunks]
        self.assertEqual([round(c.start, 6) for c in cuts[1:]], [round(times[o], 6) for o in offsets[1:]])
        self.assertIsNone(slashed(3, cuts=1)[1].lines[4].cuts)              # "1": whole, slashes or not
        self.assertEqual(len(slashed(8)[1].lines[4].cuts), planner.MAX_CUTS)
        self.assertFalse(slashed(3, persist="section")[1].lines[4].persist)  # a split line never stays
        self.assertEqual(whole(plan_of(inputs(12))), whole(plan_of(inputs(12))))
        self.assertTrue(all(x.cuts is None for i, x in enumerate(p.lines) if i != 4))

    def test_cuts_follow_each_other_as_sung(self):
        lines = with_cuts(3)
        p = plan_of(lines)
        line = p.lines[4]
        self.assertEqual(len(line.cuts), 3)
        self.assertEqual("".join(c.text for c in line.cuts), line.text)
        self.assertEqual(line.cuts[0].start, line.start)
        self.assertEqual(line.cuts[-1].end, line.end)
        for a, b in zip(line.cuts, line.cuts[1:]):
            self.assertEqual(a.end, b.start)
        off = len(line.cuts[0].text)
        self.assertAlmostEqual(line.cuts[1].start, lines[4].char_times[off])
        self.assertTrue(all(len(c.char_times) == len(c.text) == len(c.emph_mask) for c in line.cuts))

    def test_other_lines_do_not_change(self):
        base, cut = whole(plan_of(inputs(12))), whole(plan_of(with_cuts(4)))
        for i in range(12):
            if i != 4:
                self.assertEqual(cut[i], base[i])

    def test_line_wide_things_stay_line_wide(self):
        lines = with_cuts(4, particle="sparkle_burst", guide="on")
        lines[4].impact = True
        base, cut = plan_of(with_cuts(0, particle="sparkle_burst", guide="on")), plan_of(lines)
        self.assertEqual(sum(e["key"] == "sparkle_burst" and e["start"] == lines[4].start for e in cut.emitters), 1)
        self.assertEqual(len(cut.gimmicks), len(base.gimmicks))

    def test_emphasis_and_impact_land_on_their_cut(self):
        lines = with_cuts(2, line=3, impact=True)                  # 透明なままじゃ終われない, *透明*
        line = plan_of(lines).lines[3]
        self.assertTrue(line.cuts[0].impact and not line.cuts[1].impact)
        self.assertEqual(line.cuts[0].emph_mask[:2], [True, True])
        self.assertFalse(any(line.cuts[1].emph_mask))

    def test_short_line_gets_fewer_cuts(self):
        lines = inputs(4)
        lines[1].cuts, lines[2].start = 6, lines[1].start + 0.5
        lines[3].start = lines[2].start + 4
        cuts = plan_of(lines).lines[1].cuts
        self.assertEqual(len(cuts), 2)
        self.assertGreaterEqual(cuts[1].start - cuts[0].start, planner.MIN_CUT)

    def test_one_letter_cuts_find_a_layout(self):
        lines = inputs(4)
        lines[1].text, lines[1].char_times, lines[1].cuts = "光を", None, 6
        cuts = plan_of(lines).lines[1].cuts
        self.assertEqual([c.text for c in cuts], ["光", "を"])
        bake.bake(plan_of(lines), metrics)

    def test_a_split_line_does_not_stay(self):
        line = plan_of(with_cuts(3, persist="section")).lines[4]
        self.assertFalse(line.persist or line.glide or any(c.persist for c in line.cuts))

    def test_cuts_pick_their_own_parts_and_keep_the_line_settings(self):
        line = plan_of(with_cuts(3)).lines[4]
        self.assertGreater(len({c.layout for c in line.cuts} | {c.enter for c in line.cuts}), 1)
        fixed = plan_of(with_cuts(3, layout="front", enter="fade")).lines[4]
        self.assertEqual({(c.layout, c.enter) for c in fixed.cuts}, {("front", "fade")})

    def test_cuts_stay_in_front(self):
        from lyric_live_builder.core import registry
        for seed in range(30):
            for c in plan_of(with_cuts(5), seed).lines[4].cuts:
                part = registry.get("layout", c.layout)
                self.assertTrue(part.anchored and not part.big, c.layout)

    def test_locked_specs_win_over_the_seed(self):
        first = plan_of(with_cuts(3)).lines[4].cuts
        specs = [dict(layout=c.layout, enter=c.enter, hold=c.hold, exit=c.exit, distance=c.distance) for c in first]
        other = plan_of(with_cuts(3, cut_specs=specs), seed=99).lines[4].cuts
        self.assertEqual([(c.layout, c.enter, c.hold, c.exit, c.distance) for c in other],
                         [(c.layout, c.enter, c.hold, c.exit, c.distance) for c in first])


class Bake(unittest.TestCase):
    def setUp(self):
        self.lines = with_cuts(3)
        self.plan = plan_of(self.lines)
        self.baked = bake.bake(self.plan, metrics)
        self.tracks = {(t.node, t.prop): t for t in self.baked.tracks}

    def spans(self, gid):
        out = []
        for n in self.baked.nodes:
            if n.kind == "glyph" and n.parent == gid and (n.id, "active") in self.tracks:
                t = self.tracks[(n.id, "active")]
                on = t.times[np.flatnonzero(t.values[:, 0] > 0.5)]
                out.append((float(on[0]), float(t.times[-1])))
        return out

    def test_a_group_per_cut_with_every_letter(self):
        groups = [n.id for n in self.baked.nodes if n.kind == "group" and n.id.startswith("line004")]
        self.assertEqual(groups, ["line004", "line004_c1", "line004_c2"])
        glyphs = [n for n in self.baked.nodes if n.kind == "glyph" and n.id.startswith("line004")
                  and not bake.is_band_copy(n.id)]
        self.assertEqual(len(glyphs), len(self.lines[4].text.replace(" ", "")))

    def test_one_cut_at_a_time(self):
        cuts = self.plan.lines[4].cuts
        for c, gid in zip(cuts, ("line004", "line004_c1", "line004_c2")):
            spans = self.spans(gid)
            self.assertGreater(len(spans), 0)
            self.assertGreaterEqual(min(s for s, _ in spans), c.start - 1e-3)
            self.assertLessEqual(max(e for _, e in spans), c.end + 1e-3)

    def test_gaze_sees_the_later_cuts(self):
        t = self.plan.lines[4].cuts[2].start + 0.3
        self.assertTrue(any(k.startswith("line004_") for k in bake.world_positions(self.baked, t)))


if __name__ == "__main__":
    unittest.main()
