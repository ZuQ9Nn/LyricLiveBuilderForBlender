# Ported from JIZURA (src/10_audio.js analyzeAudio / beatGrid), MIT License,
# Copyright (c) 2026 hakoniwa. Vectorized with numpy.
"""PCM -> loudness envelope, onset strength, BPM and beat grid."""
from dataclasses import dataclass

import numpy as np

RATE = 50                  # analysis frames per second
_HP = 0.92                 # one-pole high-pass y[n] = a * (y[n-1] + x[n] - x[n-1])
_CHUNK = 4096              # frames per FFT batch (bounds memory on long songs)


@dataclass
class AudioInfo:
    duration: float
    sample_rate: int
    bpm: float
    beats: np.ndarray          # seconds
    energy: np.ndarray         # normalized loudness, RATE Hz, 0..1
    energy_rate: int = RATE
    spectrum: np.ndarray = None  # (frames, BANDS) 0..1 at RATE Hz (design §5.4)


def _frame_energies(mono, hop):
    """RMS and high-passed RMS of each hop-sized frame.

    The high-pass energy is taken in the frequency domain (Parseval) with the filter's
    magnitude response instead of running the recursive filter sample by sample."""
    n = len(mono) // hop
    frames = mono[:n * hop].reshape(n, hop)
    energy = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    w = np.exp(-2j * np.pi * np.fft.rfftfreq(hop))           # z^-1 on the unit circle
    gain = np.abs(_HP * (1 - w) / (1 - _HP * w)) ** 2
    weight = np.full(gain.shape, 2.0)
    weight[0] = 1.0
    if hop % 2 == 0:
        weight[-1] = 1.0
    gain *= weight
    flux = np.empty(n)
    for a in range(0, n, _CHUNK):
        spec = np.fft.rfft(frames[a:a + _CHUNK], axis=1)
        flux[a:a + _CHUNK] = (np.abs(spec) ** 2) @ gain
    flux = np.sqrt(flux / hop / hop)
    return energy, flux


def _onset(flux):
    """Positive change of log high-passed energy against the mean of the 4 previous frames."""
    lf = np.log(1e-4 + flux)
    c = np.concatenate(([0.0], np.cumsum(lf)))
    f = np.arange(len(lf))
    lo = np.maximum(0, f - 4)
    k = np.maximum(1, f - lo)
    mean = (c[f] - c[lo]) / k
    out = np.maximum(0.0, lf - mean)
    out[0] = 0.0
    return out


def _tempo(onset):
    """Autocorrelation over 70..180 BPM weighted toward 125 BPM; returns the period in frames."""
    min_lag, max_lag = round(RATE * 60 / 180), round(RATE * 60 / 70)
    scores = {}
    # one extra lag on each side so a peak at the edge of the range can still be interpolated
    for lag in range(min_lag - 1, max_lag + 2):
        s = float(np.dot(onset[lag:], onset[:-lag]))
        bpm = 60 * RATE / lag
        scores[lag] = s * np.exp(-0.5 * (np.log2(bpm / 125) / 0.7) ** 2)
    best = max(range(min_lag, max_lag + 1), key=lambda k: (scores[k], -k))
    if scores[best] <= 0:
        return RATE * 0.5
    lag = float(best)
    if best - 1 in scores and best + 1 in scores:
        a, b, c = scores[best - 1], scores[best], scores[best + 1]
        d = a - 2 * b + c
        if d != 0:
            lag = best + 0.5 * (a - c) / d
    return lag


def _phase(onset, lag):
    n = len(onset)
    best_ph, best_s = 0.0, -1.0
    for ph in np.arange(0.0, lag, 0.5):
        idx = np.floor(np.arange(ph, n, lag) + 0.5).astype(np.int64)
        s = float(onset[idx[idx < n]].sum())
        if s > best_s:
            best_s, best_ph = s, ph
    return best_ph


BANDS = 24
_FFT = 2048


def spectrum(mono, sample_rate, hop):
    """Log-spaced band levels (40 Hz .. 16 kHz) per analysis frame, 0..1 over the song's top 60 dB."""
    n = max(0, (len(mono) - _FFT) // hop + 1)
    if n == 0:
        return np.zeros((0, BANDS), dtype=np.float32)
    freqs = np.fft.rfftfreq(_FFT, 1.0 / sample_rate)
    edges = np.geomspace(40.0, min(16000.0, sample_rate / 2), BANDS + 1)
    band = np.clip(np.searchsorted(edges, freqs) - 1, -1, BANDS)
    valid = (band >= 0) & (band < BANDS)
    counts = np.maximum(np.bincount(band[valid], minlength=BANDS), 1)
    window = np.hanning(_FFT).astype(np.float32)
    out = np.empty((n, BANDS))
    for a in range(0, n, _CHUNK):
        idx = np.arange(a, min(n, a + _CHUNK))[:, None] * hop + np.arange(_FFT)
        power = np.abs(np.fft.rfft(mono[idx] * window, axis=1)) ** 2
        out[a:a + len(idx)] = (power[:, valid] @ np.eye(BANDS)[band[valid]]) / counts
    db = 10 * np.log10(out + 1e-12)
    hi = np.percentile(db, 99.5)                          # one scale for all bands: the top 60 dB
    return np.clip((db - (hi - 60.0)) / 60.0, 0, 1).astype(np.float32)


def analyze(pcm, sample_rate):
    """pcm: float array [samples] or [samples, channels]."""
    pcm = np.asarray(pcm, dtype=np.float32)
    mono = pcm.mean(axis=1) if pcm.ndim == 2 else pcm
    duration = len(mono) / sample_rate
    hop = round(sample_rate / RATE)
    if len(mono) < hop * 8:
        return AudioInfo(duration, sample_rate, 0.0, np.zeros(0), np.zeros(0))
    energy, flux = _frame_energies(mono, hop)
    onset = _onset(flux)
    lag = _tempo(onset)
    period = lag / RATE
    first = _phase(onset, lag) / RATE
    p95 = float(np.sort(energy)[int(len(energy) * 0.95)]) or 1.0
    return AudioInfo(
        duration=duration,
        sample_rate=sample_rate,
        bpm=round(60 / period * 10) / 10,
        beats=np.round(np.arange(first, duration, period), 4),
        energy=np.minimum(1.0, energy / p95).astype(np.float32),
        spectrum=spectrum(mono, sample_rate, hop),
    )


def beat_grid(bpm, offset, duration):
    """Beat times from a user BPM and first-beat offset."""
    if not bpm > 0:
        return np.zeros(0)
    t = np.arange(offset, duration + 0.01, 60.0 / bpm)
    return np.round(t[t >= 0], 4)
