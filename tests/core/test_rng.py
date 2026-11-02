"""core.rng against values produced by JIZURA's own src/01_util.js (node)."""
import unittest

import numpy as np

from lyric_live_builder.core import rng

H = [(0, 0, 0, 0, 0, 1838900668), (1, 2, 3, 4, 5, 2253742018), (20260922, 7, 0, 0, 0, 2548713879), (-5, 123456789, 0, 0, 0, 298832851), (3.7, -2.2, 0, 0, 0, 4279342918), (4294967295, 1, 2, 0, 0, 3057225505)]
SID = [('', 2166136261), ('a', 3826002220), ('layout', 3401678079), ('夜明け', 3856067194)]
STREAM_20260922 = [0.845932636875659, 0.559843998402357, 0.884747682139277, 0.386655486188829, 0.629926605848595, 0.669897390762344, 0.65715691074729, 0.315851290943101]
INT_42 = [4, 3, 6, 5, 2, 4]
WPICK_7 = ['a', 'a', 'c', 'b', 'b', 'b']
EASE_X = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]
EASE = {
    "lin": [
        0,
        0.1,
        0.25,
        0.5,
        0.75,
        0.9,
        1
    ],
    "inQuad": [
        0,
        0.01,
        0.0625,
        0.25,
        0.5625,
        0.81,
        1
    ],
    "outQuad": [
        0,
        0.19,
        0.4375,
        0.75,
        0.9375,
        0.99,
        1
    ],
    "inCubic": [
        0,
        0.001,
        0.015625,
        0.125,
        0.421875,
        0.729,
        1
    ],
    "outCubic": [
        0,
        0.271,
        0.578125,
        0.875,
        0.984375,
        0.999,
        1
    ],
    "inOutCubic": [
        0,
        0.004,
        0.0625,
        0.5,
        0.9375,
        0.996,
        1
    ],
    "outExpo": [
        0,
        0.5,
        0.823223304703,
        0.96875,
        0.994475728272,
        0.998046875,
        1
    ],
    "inExpo": [
        0,
        0.001953125,
        0.005524271728,
        0.03125,
        0.176776695297,
        0.5,
        1
    ],
    "inOutExpo": [
        0,
        0.001953125,
        0.015625,
        0.5,
        0.984375,
        0.998046875,
        1
    ],
    "outBack": [
        0,
        0.4249,
        0.8453125,
        1.1125,
        1.0734375,
        1.0161,
        1
    ],
    "outElastic": [
        0,
        1.25,
        0.911611652352,
        1.015625,
        1.005524271728,
        0.998046875,
        1
    ],
    "inOutSine": [
        0,
        0.024471741852,
        0.146446609407,
        0.5,
        0.853553390593,
        0.975528258148,
        1
    ]
}
NOISE_SEED5 = [(0, -0.3175455662421882), (0.3, -0.049375785946845996), (1.5, 0.3720096827019006), (2.75, -0.4038319654064253), (-1.2, -0.02608658447861678), (10.01, -0.4165687432886651)]


class TestRng(unittest.TestCase):
    def test_hash(self):
        for *args, want in H:
            self.assertEqual(rng.h(*args), want, args)

    def test_sid(self):
        for s, want in SID:
            self.assertEqual(rng.sid(s), want, s)

    def test_stream(self):
        g = rng.Rng(20260922)
        for want in STREAM_20260922:
            self.assertAlmostEqual(g(), want, places=14)
        g = rng.Rng(42)
        self.assertEqual([g.int(1, 6) for _ in INT_42], INT_42)
        g = rng.Rng(7)
        self.assertEqual([g.wpick([("a", 1), ("b", 3), ("c", 0.5)]) for _ in WPICK_7], WPICK_7)

    def test_easing(self):
        self.assertEqual(set(EASE), set(rng.E))
        for k, want in EASE.items():
            for x, w in zip(EASE_X, want):
                self.assertAlmostEqual(rng.E[k](x), w, places=10, msg=(k, x))

    def test_noise(self):
        for x, want in NOISE_SEED5:
            self.assertAlmostEqual(rng.noise1(x, 5), want, places=12)

    def test_vectorized_matches_scalar(self):
        a = np.array([0, 1, -5, 3.7, 4294967295, 123456789])
        b = np.array([0, 2, 123456789, -2.2, 1, 7])
        got = rng.h_np(a, b, 3)
        want = [rng.h(float(x) if x % 1 else int(x), float(y) if y % 1 else int(y), 3) for x, y in zip(a, b)]
        self.assertEqual(got.tolist(), want)
        xs = np.array([x for x, _ in NOISE_SEED5])
        np.testing.assert_allclose(rng.noise1_np(xs, 5), [w for _, w in NOISE_SEED5], atol=1e-12)


if __name__ == "__main__":
    unittest.main()
