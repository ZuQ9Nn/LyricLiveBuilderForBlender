"""The part of a plan shown in the trial window (design §12)."""
import unittest

from lyric_live_builder.core import bake, planner

from .test_text_parts import inputs, metrics, sections_for


class Subset(unittest.TestCase):
    def setUp(self):
        lines = inputs(12)
        lines[4].gimmick, lines[4].particle = "star", "sparkle_burst"
        duration = lines[-1].end + 2.0
        self.plan = planner.plan(lines, sections_for(duration), duration, 7, bpm=120)

    def test_one_line_with_its_own_things(self):
        lp = self.plan.lines[4]
        part = planner.subset(self.plan, lp.start - 1.4, lp.end + 0.4, line=4)
        self.assertEqual([x.index for x in part.lines], [4])
        self.assertEqual([g["line"] for g in part.gimmicks], [4])
        self.assertTrue(part.emitters and all(e["start"] < lp.end + 0.4 and e["end"] > lp.start - 1.4 for e in part.emitters))
        self.assertTrue(any(e["key"] == "sparkle_burst" for e in part.emitters))
        self.assertEqual(part.world, self.plan.world)
        self.assertEqual(len(self.plan.lines), 12)                  # the plan itself is left as it was

    def test_section_start_has_no_lines(self):
        part = planner.subset(self.plan, 30.0, 38.0)
        self.assertEqual((part.lines, part.gimmicks), ([], []))

    def test_bakes_only_that_line(self):
        lp = self.plan.lines[4]
        baked = bake.bake(planner.subset(self.plan, lp.start - 1.4, lp.end + 0.4, line=4), metrics)
        groups = {n.id for n in baked.nodes if n.kind == "group" and n.category == "text"}
        self.assertEqual(groups, {"line004"})


if __name__ == "__main__":
    unittest.main()
