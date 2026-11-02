"""core.audio: BPM of synthetic metronome tracks within +-1 BPM (P1-05)."""
import unittest

import numpy as np

from lyric_live_builder.core import audio


def metronome(bpm, seconds=30.0, sr=44100, first=0.25, noise=0.0, stereo=False):
    n = int(sr * seconds)
    x = np.zeros(n, dtype=np.float32)
    tone = (np.sin(2 * np.pi * 1500 * np.arange(int(sr * 0.02)) / sr) * np.linspace(1, 0, int(sr * 0.02))).astype(np.float32)
    for k, t in enumerate(np.arange(first, seconds - 0.05, 60.0 / bpm)):
        s = int(t * sr)
        x[s:s + tone.size] += tone * (1.0 if k % 4 == 0 else 0.6)
    if noise:
        x += np.random.default_rng(1).normal(0, noise, n).astype(np.float32)
    return (np.stack([x, x], axis=1) if stereo else x), sr


class TestAudio(unittest.TestCase):
    def test_bpm(self):
        for bpm in (72, 96, 120, 128, 150, 174):
            pcm, sr = metronome(bpm)
            info = audio.analyze(pcm, sr)
            self.assertLessEqual(abs(info.bpm - bpm), 1.0, (bpm, info.bpm))

    def test_noise_stereo_48k(self):
        pcm, sr = metronome(120, sr=48000, noise=0.02, stereo=True)
        info = audio.analyze(pcm, sr)
        self.assertLessEqual(abs(info.bpm - 120), 1.0)
        self.assertAlmostEqual(info.duration, 30.0)

    def test_beat_phase_and_energy(self):
        pcm, sr = metronome(120, first=0.25)
        info = audio.analyze(pcm, sr)
        # the grid lands on the clicks (within one analysis frame)
        self.assertLess(abs(((info.beats[0] - 0.25) + 0.25) % 0.5 - 0.25), 1.5 / audio.RATE)
        self.assertEqual(info.energy.shape, (int(30 * audio.RATE),))
        self.assertLessEqual(float(info.energy.max()), 1.0)

    def test_silence_and_short(self):
        info = audio.analyze(np.zeros(44100 * 5, dtype=np.float32), 44100)
        self.assertEqual(info.duration, 5.0)
        info = audio.analyze(np.zeros(100, dtype=np.float32), 44100)
        self.assertEqual(info.bpm, 0.0)

    def test_beat_grid(self):
        self.assertEqual(audio.beat_grid(120, 0.5, 2.0).tolist(), [0.5, 1.0, 1.5, 2.0])
        self.assertEqual(audio.beat_grid(0, 0.5, 2.0).size, 0)


if __name__ == "__main__":
    unittest.main()
