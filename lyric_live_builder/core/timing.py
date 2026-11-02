# Line timing is ported from JIZURA (src/08_planner.js computeTiming), MIT License,
# Copyright (c) 2026 hakoniwa. Added: per-line sources (manual > LRC > tap > estimate)
# and per-character times.
"""Line and character times, tap latency."""
import statistics
from dataclasses import dataclass

from . import lyrics as L
from .rng import clamp, js_round

DEFAULT_OFFSET = 0.4
DEFAULT_TAIL = 0.9
LATENCY_BPM = 120.0
LATENCY_COUNT_IN = 4
LATENCY_TAPS = 16
OUTLIER_MS = 150.0


@dataclass
class Timing:
    starts: list
    ends: list
    sources: list        # "manual" | "lrc" | "tap" | "auto" per line
    duration: float


def line_duration(text, bpm=0.0, lo=1.3, scale=1.0):
    """Estimated sung length of a line from its character count (snapped to whole beats)."""
    d = clamp(0.8 + len(text) * 0.17, lo, 5.2) * scale
    if bpm > 0:
        beat = 60.0 / bpm
        d = max(2, js_round(d / beat)) * beat
    return d


def compute(lines, bpm=0.0, offset=DEFAULT_OFFSET, manual=None, taps=None,
            audio_duration=None, tail=DEFAULT_TAIL, line_scale=1.0):
    """lines: list of lyrics.Line. manual / taps: {line index: seconds}; taps are already
    latency-corrected. Lines without a time are chained from the previous start."""
    manual, taps = manual or {}, taps or {}
    beat = 60.0 / bpm if bpm > 0 else 0.0
    starts, sources = [], []
    for i, ln in enumerate(lines):
        if i in manual:
            s, src = manual[i], "manual"
        elif ln.lrc is not None:
            s, src = ln.lrc, "lrc"
        elif i in taps:
            s, src = taps[i], "tap"
        elif i > 0:
            d = line_duration(lines[i - 1].text, bpm, scale=line_scale)
            s = starts[-1] + d + ((beat * 2 if beat else 0.8) if ln.gap_before else 0.0)
            src = "auto"
        else:
            s, src = offset, "auto"
        starts.append(s)
        sources.append(src)
    ends = [max(s + 0.35, starts[i + 1]) for i, s in enumerate(starts[:-1])]
    if lines:
        ends.append(starts[-1] + line_duration(lines[-1].text, bpm, lo=1.5, scale=line_scale))
    last = ends[-1] if ends else 3.0
    if audio_duration:
        duration = max(audio_duration, last + 0.2 if ends else 1.0)
    else:
        duration = last + tail
    return Timing(starts, ends, sources, duration)


def char_weight(c):
    if c == "ー":
        return 0.8
    if c.isspace():
        return 0.0
    if L.is_small_kana(c):
        return 0.5
    if L.is_hira(c) or L.is_kata(c):
        return 1.0
    if L.is_kanji(c):
        return 1.6
    if L.is_latin(c):
        return 0.6
    if L.is_punct(c):
        return 0.2
    return 1.0


def char_times(text, start, end):
    """Start time of each character, spread by weight over the sung part of the line
    (up to the next line, but no longer than the estimated length)."""
    span = min(end - start, line_duration(text))
    w = [char_weight(c) for c in text]
    total = sum(w) or 1.0
    out, acc = [], 0.0
    for x in w:
        out.append(start + span * acc / total)
        acc += x
    return out


def tap_latency(taps_song, bpm=LATENCY_BPM, count_in=LATENCY_COUNT_IN, n_clicks=None):
    """Song times of taps -> (median ms, MAD ms, valid, outliers) or None with < 8 valid taps."""
    beat = 60.0 / bpm
    n_clicks = n_clicks or count_in + LATENCY_TAPS
    raw = []
    for t in taps_song:
        k = js_round(t / beat)
        if count_in <= k < n_clicks:
            raw.append((t - k * beat) * 1000)
    ok = [o for o in raw if abs(o) <= OUTLIER_MS]
    if len(ok) < 8:
        return None
    med = statistics.median(ok)
    return med, statistics.median(abs(o - med) for o in ok), len(ok), len(raw) - len(ok)
