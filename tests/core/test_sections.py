"""core.sections: headings, estimation from gaps / repeats / loudness, tiling."""
import unittest

import numpy as np

from lyric_live_builder.core import lyrics, sections, timing


def tiles(secs, duration):
    return secs[0].start == 0 and all(a.end == b.start for a, b in zip(secs, secs[1:])) and secs[-1].end == duration


class TestHeadings(unittest.TestCase):
    def test_from_headings(self):
        p = lyrics.parse("前の行\n[A]\nあ\nい\n[サビ]\nう\n[間奏]\n[B]\nえ")
        t = timing.compute(p.lines, taps={0: 1.0, 1: 5.0, 2: 9.0, 3: 20.0, 4: 40.0}, audio_duration=60.0)
        s = sections.from_headings(p, t)
        self.assertEqual([x.kind for x in s], ["verse", "verse", "chorus", "interlude", "prechorus"])
        self.assertEqual([x.label for x in s], ["", "A", "サビ", "間奏", "B"])
        self.assertEqual(s[1].start, 5.0)
        self.assertEqual(s[2].start, 20.0)
        # the empty interlude starts when the chorus line is estimated to finish
        self.assertAlmostEqual(s[3].start, 20.0 + timing.line_duration("う"))
        self.assertEqual(s[4].start, 40.0)
        self.assertTrue(tiles(s, 60.0))

    def test_empty_heading_without_time_gives_way(self):
        p = lyrics.parse("[A]\nあ\n[B]\n[サビ]\nい")
        t = timing.compute(p.lines, taps={0: 0.0, 1: 1.0}, audio_duration=10.0)
        s = sections.from_headings(p, t)
        self.assertEqual([x.label for x in s], ["A", "サビ"])
        self.assertTrue(tiles(s, 10.0))


class TestEstimate(unittest.TestCase):
    LYR = """一番目のうた
二番目のうた

ここで盛り上がる
ここで盛り上がる
まだまだ続く
まだまだ続く

三番目のうた
四番目のうた

ここで盛り上がる
ここで盛り上がる
最後の一行"""

    def test_repeats_blank_lines_and_tiling(self):
        p = lyrics.parse(self.LYR)
        taps = {i: 6.0 + i * 4.0 for i in range(len(p.lines))}
        t = timing.compute(p.lines, taps=taps, audio_duration=60.0)
        s = sections.estimate(p, t, bpm=120)
        # the 6 s intro is merged forward; 11.5 s after the last line is an outro
        self.assertEqual([x.kind for x in s], ["verse", "chorus", "verse", "chorus", "outro"])
        self.assertEqual([x.start for x in s][:4], [0.0, 14.0, 30.0, 38.0])
        self.assertTrue(tiles(s, 60.0))
        self.assertTrue(all(x.end - x.start >= sections.MIN_SECTION for x in s))

    def test_loudness_lift_without_repeats(self):
        p = lyrics.parse("\n".join(f"違う歌詞の{i}行目です" for i in range(12)))
        t = timing.compute(p.lines, taps={i: i * 4.0 for i in range(12)}, audio_duration=60.0)
        energy = np.full(60 * 50, 0.2)
        energy[24 * 50:] = 0.8                         # lift at line 6 (24 s)
        s = sections.estimate(p, t, energy=energy)
        self.assertEqual([(x.kind, x.start) for x in s][:2], [("verse", 0.0), ("chorus", 24.0)])

    def test_long_gap_is_interlude(self):
        p = lyrics.parse("\n".join(f"うたの{i}" for i in range(6)))
        taps = {0: 1.0, 1: 4.0, 2: 7.0, 3: 30.0, 4: 33.0, 5: 36.0}
        t = timing.compute(p.lines, taps=taps, audio_duration=50.0)
        s = sections.estimate(p, t)
        self.assertIn("interlude", [x.kind for x in s])
        self.assertTrue(tiles(s, 50.0))

    def test_no_lines(self):
        p = lyrics.parse("")
        s = sections.estimate(p, timing.compute([], audio_duration=30.0))
        self.assertEqual([(x.kind, x.start, x.end) for x in s], [("verse", 0.0, 30.0)])

    def test_section_of(self):
        s = [sections.Section("verse", "", 0, 10), sections.Section("chorus", "", 10, 20)]
        self.assertEqual([sections.section_of(s, t) for t in (0, 9.9, 10, 25)], [0, 0, 1, 1])


if __name__ == "__main__":
    unittest.main()
