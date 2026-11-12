"""Copy / paste of a line's effects (spec §6.2), the core side: a pasted line plans and bakes like its source."""
import unittest
from dataclasses import replace

import numpy as np

from lyric_live_builder.core import bake, planner

from .test_text_parts import LYRICS, inputs, metrics, sections_for

MOTION = ("location", "rotation", "scale", "mask", "mask_shape", "mask_box")


def plan_of(lines, seed=7):
    duration = lines[-1].end + 2.0
    return planner.plan(lines, sections_for(duration), duration, seed, bpm=120)


def paste(lines, plan, src, dst):
    """What ui.planning.copy_line / paste_line write, on the planner's inputs."""
    lp = plan.lines[src]
    lines[dst] = replace(lines[dst], layout=lp.layout, enter=lp.enter, hold=lp.hold, exit=lp.exit, distance=lp.distance,
                         persist="section" if lp.persist else "next", cuts=len(lp.cuts) if lp.cuts else 1,
                         look_seed=lp.seed,
                         cut_specs=[{"layout": c.layout, "enter": c.enter, "hold": c.hold, "exit": c.exit,
                                     "distance": c.distance, "seed": c.seed} for c in lp.cuts or ()])
    return lines


def tracks(baked, prefix, start):
    """Motion tracks of a line's nodes, keyed by the node id without the line number, times from its start."""
    out = {}
    for tr in baked.tracks:
        if tr.node.startswith(prefix) and tr.prop in MOTION:
            out[(tr.node[len(prefix):], tr.prop)] = (np.round(tr.times - start, 4), np.round(tr.values, 5))
    return out


class CopyPaste(unittest.TestCase):
    def setUp(self):
        self.src, self.dst = 2, 2 + len(LYRICS)                         # the same lyrics, later in the song
        self.lines = inputs(len(LYRICS) + 6, persist="next")
        self.assertEqual(self.lines[self.src].text, self.lines[self.dst].text)

    def check_same(self, lines, plan):
        a, b = plan.lines[self.src], plan.lines[self.dst]
        for f in ("layout", "layout_params", "enter", "hold", "exit", "distance", "seed", "anchor"):
            self.assertEqual(getattr(a, f), getattr(b, f), f)
        baked = bake.bake(plan, metrics)
        ta = tracks(baked, f"line{self.src:03d}", a.start)
        tb = tracks(baked, f"line{self.dst:03d}", b.start)
        self.assertTrue(ta)
        self.assertEqual(set(ta), set(tb))
        for key in ta:
            np.testing.assert_array_equal(ta[key][0], tb[key][0], err_msg=str(key))
            np.testing.assert_allclose(ta[key][1], tb[key][1], atol=1e-5, err_msg=str(key))

    def test_same_lyrics_same_look(self):
        lines = paste(self.lines, plan_of(self.lines), self.src, self.dst)
        self.check_same(lines, plan_of(lines))

    def test_cut_lines_too(self):
        self.lines[self.src] = replace(self.lines[self.src], cuts=3)
        lines = paste(self.lines, plan_of(self.lines), self.src, self.dst)
        plan = plan_of(lines)
        a, b = plan.lines[self.src].cuts, plan.lines[self.dst].cuts
        self.assertEqual(len(a), 3)
        for x, y in zip(a, b):
            for f in ("text", "layout", "layout_params", "enter", "hold", "exit", "distance", "seed"):
                self.assertEqual(getattr(x, f), getattr(y, f), f)

    def test_the_paste_does_not_follow_the_source(self):
        lines = paste(self.lines, plan_of(self.lines), self.src, self.dst)
        before = plan_of(lines).lines[self.dst]
        lines[self.src] = replace(lines[self.src], seed_offset=3)       # the source re-rolled
        after = plan_of(lines)
        self.assertNotEqual(after.lines[self.src].seed, before.seed)
        for f in ("layout", "layout_params", "enter", "hold", "exit", "distance", "seed"):
            self.assertEqual(getattr(after.lines[self.dst], f), getattr(before, f), f)
        for seed in (8, 9):                                             # Make It for Me (another seed) keeps it too
            self.assertEqual(plan_of(lines, seed).lines[self.dst].layout, before.layout)

    def test_other_lyrics_take_the_parts(self):
        other = self.dst + 1                                            # different lyrics, other length
        self.assertNotEqual(len(self.lines[other].text), len(self.lines[self.src].text))
        lines = paste(self.lines, plan_of(self.lines), self.src, other)
        plan = plan_of(lines)
        a, b = plan.lines[self.src], plan.lines[other]
        self.assertEqual((a.layout, a.enter, a.hold, a.exit, a.distance, a.seed),
                         (b.layout, b.enter, b.hold, b.exit, b.distance, b.seed))
        bake.bake(plan, metrics)                                        # laid out for its own letters


if __name__ == "__main__":
    unittest.main()
