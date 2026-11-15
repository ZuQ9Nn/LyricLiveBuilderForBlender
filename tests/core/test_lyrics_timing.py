"""core.lyrics / core.timing against JIZURA's src/08_planner.js (node, Intl.Segmenter off)."""
import unittest

from lyric_live_builder.core import lyrics, timing

CHUNKS = [
    [
        "夜明けの色を覚えてる",
        [
            "夜明けの色を",
            "覚えてる"
        ]
    ],
    [
        "ほどけた声が遠くで鳴った",
        [
            "ほどけた",
            "声が遠くで",
            "鳴った"
        ]
    ],
    [
        "ねえ、まだ間に合うかな",
        [
            "ねえ、まだ",
            "間に合うかな"
        ]
    ],
    [
        "透明なままじゃ終われない",
        [
            "透明なままじゃ",
            "終われない"
        ]
    ],
    [
        "カタカナとひらがなの混在テスト",
        [
            "カタカナとひらがなの",
            "混在",
            "テスト"
        ]
    ],
    [
        "Hello world again",
        [
            "Hello",
            "world",
            "again"
        ]
    ],
    [
        "きみのことをずっとずっとおもいだしてしまうよるのそら",
        [
            "きみのことを",
            "ずっとずっとお",
            "もいだしてしま",
            "うよるのそら"
        ]
    ],
    [
        "東京特許許可局長今日急遽休暇許可拒否",
        [
            "東京特許許可",
            "局長今日急遽",
            "休暇許可拒否"
        ]
    ]
]

SAMPLE = """# comment
[ti:Song]
夜明けの色を/覚えてる

ほどけた声が遠くで鳴った|note here
ねえ、まだ間に合うかな
*透明*なままじゃ終われない!
Hello/world again
[00:12.50][01:02.00]繰り返し"""
PARSED = [
    {
        "text": "繰り返し",
        "note": None,
        "impact": False,
        "emph": [],
        "manual": None,
        "gapBefore": False,
        "lrc": 12.5
    },
    {
        "text": "繰り返し",
        "note": None,
        "impact": False,
        "emph": [],
        "manual": None,
        "gapBefore": False,
        "lrc": 62
    },
    {
        "text": "夜明けの色を覚えてる",
        "note": None,
        "impact": False,
        "emph": [],
        "manual": [
            "夜明けの色を",
            "覚えてる"
        ],
        "gapBefore": False,
        "lrc": None
    },
    {
        "text": "ほどけた声が遠くで鳴った",
        "note": "note here",
        "impact": False,
        "emph": [],
        "manual": None,
        "gapBefore": True,
        "lrc": None
    },
    {
        "text": "ねえ、まだ間に合うかな",
        "note": None,
        "impact": False,
        "emph": [],
        "manual": None,
        "gapBefore": False,
        "lrc": None
    },
    {
        "text": "透明なままじゃ終われない",
        "note": None,
        "impact": True,
        "emph": [
            "透明"
        ],
        "manual": None,
        "gapBefore": False,
        "lrc": None
    },
    {
        "text": "Hello world again",
        "note": None,
        "impact": False,
        "emph": [],
        "manual": [
            "Hello",
            "world again"
        ],
        "gapBefore": False,
        "lrc": None
    }
]

TIMING_LINES = ["夜明けの色を覚えてる", "ほどけた声が遠くで鳴った", "", "ねえ、まだ間に合うかな", "透明なままじゃ終われない"]
# (bpm, offset, manual, audio duration) -> JIZURA computeTiming
TIMING = [(0, 0.4, {}, None, {'starts': [0.4, 2.9, 6.54, 9.21], 'ends': [2.9, 6.54, 9.21, 12.05], 'duration': 12.950000000000001}), (120, 0.5, {}, None, {'starts': [0.5, 3, 7, 9.5], 'ends': [3, 7, 9.5, 12.5], 'duration': 13.4}), (120, 0.5, {2: 10}, None, {'starts': [0.5, 3, 10, 12.5], 'ends': [3, 10, 12.5, 15.5], 'duration': 16.4}), (0, 0.4, {}, 60, {'starts': [0.4, 2.9, 6.54, 9.21], 'ends': [2.9, 6.54, 9.21, 12.05], 'duration': 60})]


class TestChunks(unittest.TestCase):
    def test_chunk_text(self):
        for text, want in CHUNKS:
            self.assertEqual(lyrics.chunk_text(text), want, text)

    def test_split_lines(self):
        self.assertEqual(lyrics.split_lines("きみのことをずっとずっとおもいだしてしまうよるのそら", 8),
                         "きみのことを\nずっとずっとお\nもいだしてしま\nうよるのそら")


class TestDecodeText(unittest.TestCase):
    def test_encodings(self):
        text = "夜明けの色を覚えてる\n[サビ]\nHello world"
        for data in (text.encode("utf-8"), text.encode("utf-8-sig"), text.encode("utf-16"), text.encode("cp932")):
            self.assertEqual(lyrics.decode_text(data), text)


class TestParse(unittest.TestCase):
    def test_jizura_notation(self):
        p = lyrics.parse(SAMPLE)
        self.assertEqual(p.meta, {"ti": "Song"})
        self.assertEqual(len(p.lines), len(PARSED))
        for got, want in zip(p.lines, PARSED):
            self.assertEqual((got.text, got.note, got.impact, got.emph, got.manual, got.gap_before, got.lrc),
                             (want["text"], want["note"], want["impact"], want["emph"], want["manual"], want["gapBefore"], want["lrc"]))

    def test_escaped_marks_are_letters(self):
        p = lyrics.parse("\\#1 行くよ\\!\nA\\/B *強\\*調*\n[サビ]\n\\[サビ\\]\n終わり\\\\!\n曲名\\|副題|注\\/釈\nC:\\x/y\n")
        got = [(ln.text, ln.impact, ln.emph, ln.manual, ln.note) for ln in p.lines]
        self.assertEqual(got, [
            ("#1 行くよ!", False, [], None, None),                 # not a comment, not an accent
            ("A/B 強*調", False, ["強*調"], None, None),          # not a chunk break, a star in the emphasis
            ("[サビ]", False, [], None, None),                    # not a heading
            ("終わり\\", True, [], None, None),                    # \\ is a backslash; the ! after it is the accent
            ("曲名|副題", False, [], None, "注/釈"),
            ("C:\\x y", False, [], ["C:\\x", "y"], None),         # a backslash before another letter stays
        ])
        self.assertEqual(len(p.headings), 1)

    def test_headings(self):
        p = lyrics.parse("[Ａメロ]\n一行目\n[サビ]\n二行目\n[01:02.00]時刻\n[Verse 2]\n[間奏]\n[ラップ]\n三行目")
        self.assertEqual([(h.kind, h.label) for h in p.headings],
                         [("verse", "Ａメロ"), ("chorus", "サビ"), ("verse", "Verse 2"), ("interlude", "間奏"), ("custom", "ラップ")])
        # lines with an LRC time sort first (JIZURA behaviour)
        self.assertEqual([(ln.text, ln.heading) for ln in p.lines], [("時刻", 1), ("一行目", 0), ("二行目", 1), ("三行目", 4)])
        self.assertEqual(p.lines[0].lrc, 62.0)

    def test_heading_names(self):
        for name, kind in [("A", "verse"), ("B", "prechorus"), ("Pre-Chorus", "prechorus"), ("Chorus", "chorus"),
                           ("イントロ", "intro"), ("Intro", "intro"), ("Bメロ", "prechorus"), ("Cメロ", "bridge"),
                           ("Bridge", "bridge"), ("大サビ", "bridge"), ("アウトロ", "outro"), ("Outro", "outro"),
                           ("Interlude", "interlude"), ("サビ2", "chorus")]:
            self.assertEqual(lyrics.heading_kind(name), kind, name)

    def test_lrc_is_not_a_heading(self):
        p = lyrics.parse("[00:01.00]a\n[12:30]b")
        self.assertEqual(p.headings, [])
        self.assertEqual([ln.lrc for ln in p.lines], [1.0, 750.0])


class TestMatchLines(unittest.TestCase):
    def test_insert_delete_edit(self):
        old = ["a", "b", "c", "b", "c"]
        self.assertEqual(lyrics.match_lines(old, old), {i: i for i in range(5)})
        self.assertEqual(lyrics.match_lines(old, ["new", "a", "b", "c", "b", "c"]), {1: 0, 2: 1, 3: 2, 4: 3, 5: 4})
        self.assertEqual(lyrics.match_lines(old, ["a", "c", "b", "c"]), {0: 0, 1: 2, 2: 3, 3: 4})
        # a typo fix keeps its line; the repeated chorus lines keep their own copies
        self.assertEqual(lyrics.match_lines(old, ["a", "B", "c", "b", "c"]), {i: i for i in range(5)})
        self.assertEqual(lyrics.match_lines([], ["a"]), {})


class TestTiming(unittest.TestCase):
    def test_jizura_compute_timing(self):
        p = lyrics.parse("\n".join(TIMING_LINES))
        for bpm, offset, manual, dur, want in TIMING:
            t = timing.compute(p.lines, bpm=bpm, offset=offset, manual=manual, audio_duration=dur)
            for a, b in zip(t.starts, want["starts"]):
                self.assertAlmostEqual(a, b, places=9)
            for a, b in zip(t.ends, want["ends"]):
                self.assertAlmostEqual(a, b, places=9)
            self.assertAlmostEqual(t.duration, want["duration"], places=9)

    def test_priority(self):
        p = lyrics.parse("a\n[00:05.00]b\nc\nd")
        # parse sorts by LRC: b(5.0) first, then a, c, d
        t = timing.compute(p.lines, manual={0: 1.0}, taps={0: 9.0, 2: 3.0})
        self.assertEqual(t.sources, ["manual", "auto", "tap", "auto"])
        self.assertEqual(t.starts[0], 1.0)
        self.assertEqual(t.starts[2], 3.0)
        p = lyrics.parse("[00:05.00]a\nb")
        t = timing.compute(p.lines, taps={0: 9.0, 1: 7.0})
        self.assertEqual(t.sources, ["lrc", "tap"])
        self.assertEqual(t.starts, [5.0, 7.0])

    def test_char_times(self):
        ct = timing.char_times("あい漢", 10.0, 20.0)
        span = timing.line_duration("あい漢")
        self.assertEqual(len(ct), 3)
        self.assertAlmostEqual(ct[0], 10.0)
        self.assertAlmostEqual(ct[1], 10.0 + span * 1.0 / 3.6)
        self.assertAlmostEqual(ct[2], 10.0 + span * 2.0 / 3.6)
        # never runs past the next line
        self.assertLess(timing.char_times("あいうえおかきくけこさしすせそ", 0.0, 1.0)[-1], 1.0)


    def test_tap_latency(self):
        beat = 0.5
        taps = [k * beat + 0.030 + (0.004 if k % 2 else -0.004) for k in range(4, 20)]
        taps += [1.0, 7.75, 11.0]          # count-in tap, off-beat outlier, tap after the last click
        med, mad, ok, out = timing.tap_latency(taps)
        self.assertAlmostEqual(med, 30.0, places=6)
        self.assertAlmostEqual(mad, 4.0, places=6)
        self.assertEqual((ok, out), (16, 1))
        self.assertIsNone(timing.tap_latency([k * beat for k in range(4, 10)]))     # fewer than 8


if __name__ == "__main__":
    unittest.main()
