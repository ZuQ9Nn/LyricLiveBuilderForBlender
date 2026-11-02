"""Sections: from lyric headings, or estimated from gaps, loudness and repeated lines.

Sections always tile the song from 0 to the end without gaps (the Unity clips are cut on them).
"""
import re
from dataclasses import dataclass

import numpy as np

from .timing import line_duration

MIN_SECTION = 8.0          # shorter sections are merged into the previous one
SURGE_RATIO = 1.35         # loudness after / before a boundary that counts as a lift
SURGE_WINDOW = 4.0         # seconds on each side
INTERLUDE_GAP = 8.0        # silence between lines that becomes an interlude


@dataclass
class Section:
    kind: str
    label: str
    start: float
    end: float


def _tile(raw, duration):
    """raw: [(kind, label, start)] -> Sections covering 0..duration. A section that would be
    empty (the next one starts at the same time) gives way to the later one."""
    out = []
    for kind, label, start in raw:
        if out:
            start = max(start, out[-1].start)
            if start == out[-1].start:
                out.pop()
        out.append(Section(kind, label, start, 0.0))
    if not out:
        out.append(Section("verse", "", 0.0, 0.0))
    out[0].start = 0.0
    for a, b in zip(out, out[1:]):
        a.end = b.start
    out[-1].end = max(duration, out[-1].start)
    return out


def from_headings(parsed, timing):
    """Headings of the lyrics; a heading without lines (e.g. [間奏]) starts where the
    previous line is estimated to finish. Lines before the first heading form an implicit verse."""
    lines, starts, ends = parsed.lines, timing.starts, timing.ends
    sung_end = [min(ends[i], starts[i] + line_duration(ln.text)) for i, ln in enumerate(lines)]
    raw = []
    if any(ln.heading is None for ln in lines):
        raw.append(("verse", "", 0.0))
    for k, hd in enumerate(parsed.headings):
        idx = [i for i, ln in enumerate(lines) if ln.heading == k]
        if idx:
            start = min(starts[i] for i in idx)
        else:
            prev = [i for i, ln in enumerate(lines) if ln.heading is not None and ln.heading < k]
            start = max(sung_end[i] for i in prev) if prev else 0.0
        raw.append((hd.kind, hd.label, start))
    return _tile(raw, timing.duration)


def _norm(text):
    return re.sub(r"[\s、。,.!?！？・…ー〜～]", "", text)


def _repeated(lines):
    """Indices of lines inside a run of 2+ consecutive lines that occurs at least twice."""
    t = [_norm(ln.text) for ln in lines]
    n, rep = len(t), set()
    for i in range(n):
        for j in range(i + 1, n):
            k = 0
            while j + k < n and i + k < j and t[i + k] == t[j + k]:
                k += 1
            if k >= 2:
                rep.update(range(i, i + k))
                rep.update(range(j, j + k))
    return rep


def _mean(energy, rate, t0, t1):
    a, b = max(0, int(t0 * rate)), max(0, int(t1 * rate))
    seg = energy[a:b]
    return float(seg.mean()) if seg.size else 0.0


def estimate(parsed, timing, bpm=0.0, energy=None, energy_rate=50.0):
    lines, starts = parsed.lines, timing.starts
    if not lines:
        return _tile([], timing.duration)
    beat = 60.0 / bpm if bpm > 0 else 0.5
    n = len(lines)
    sung_end = [starts[i] + line_duration(lines[i].text) for i in range(n)]
    gap = [0.0] + [starts[i] - sung_end[i - 1] for i in range(1, n)]
    surge = set()
    if energy is not None and len(energy):
        energy = np.asarray(energy, dtype=np.float64)
        for i in range(1, n):
            before = _mean(energy, energy_rate, starts[i] - SURGE_WINDOW, starts[i])
            after = _mean(energy, energy_rate, starts[i], starts[i] + SURGE_WINDOW)
            if before > 1e-6 and after / before >= SURGE_RATIO:
                surge.add(i)
    # a pause counts when it is 2 beats longer than this song's usual pause between lines
    thr = 2 * beat + (float(np.median(gap[1:])) if n > 1 else 0.0)
    thr = max(thr, 2 * beat)
    cuts = [0] + [i for i in range(1, n) if lines[i].gap_before or gap[i] >= thr or i in surge]
    groups = [list(range(a, b)) for a, b in zip(cuts, cuts[1:] + [n])]
    rep = _repeated(lines)
    span = lambda g: (starts[g[0]], sung_end[g[-1]])
    kinds, level = [], 0.0
    for g in groups:
        if rep:
            chorus = sum(i in rep for i in g) * 2 >= len(g)
        elif energy is None:
            chorus = False
        else:
            # a lift starts a chorus; it lasts while the loudness stays near that level
            e = _mean(energy, energy_rate, *span(g))
            if g[0] in surge:
                level = e
            chorus = g[0] in surge or (bool(kinds) and kinds[-1] == "chorus" and e * SURGE_RATIO >= level)
        kinds.append("chorus" if chorus else "verse")
    for k in range(2, len(kinds)):
        if kinds[k] == "chorus" and kinds[k - 1] == "verse" and kinds[k - 2] == "verse":
            kinds[k - 1] = "prechorus"
    raw = []
    if starts[0] > 0:
        raw.append(("intro", "", 0.0))
    for g, kind in zip(groups, kinds):
        if gap[g[0]] >= INTERLUDE_GAP and g[0] > 0:
            raw.append(("interlude", "", sung_end[g[0] - 1]))
        elif raw and raw[-1][0] == kind:
            continue                       # same kind continues
        raw.append((kind, "", starts[g[0]]))
    if timing.duration - sung_end[-1] > 0:
        raw.append(("outro", "", sung_end[-1]))
    return merge_short(_tile(raw, timing.duration))


def merge_short(sections, min_len=MIN_SECTION):
    """Merge sections shorter than min_len: the first into the next, the others into the previous."""
    out = [Section(x.kind, x.label, x.start, x.end) for x in sections]
    while len(out) > 1 and out[0].end - out[0].start < min_len:
        out[1].start = 0.0
        out.pop(0)
    merged = out[:1]
    for x in out[1:]:
        if x.end - x.start < min_len or x.kind == merged[-1].kind:
            merged[-1].end = x.end
        else:
            merged.append(x)
    return merged


def section_of(sections, t):
    """Index of the section that contains time t."""
    for i in range(len(sections) - 1, -1, -1):
        if t >= sections[i].start:
            return i
    return 0
