# Line composition follows JIZURA's plan() (src/08_planner.js: novelty weighting, emphasis,
# per-line seeds), MIT License, Copyright (c) 2026 hakoniwa. Rewritten for 3D space.
"""Plan: which layout / motions / distance each line uses and where it stands (design §5.5)."""
import math

from . import lyrics, model, registry
from .rng import Rng, h

STAGE_TEXT = 2                       # seed stage of the text composition ("ここだけ変える" re-rolls stages)
DEG = math.pi / 180
# side slots for lines kept until the section ends: (azimuth, elevation); the front stays free
KEEP_SLOTS = [(-62, 0), (62, 0), (-62, 22), (62, 22), (-105, 8), (105, 8)]   # clear of "look up" (front, 22-34°)
KEEP_CHANCE = 0.22


def novelty(history, key, value):
    w = 1.0
    for d, item in enumerate(reversed(history[-6:])):
        if item.get(key) == value:
            w *= 0.2 if d < 2 else 0.6
    return w


def _pick(rng, kind, history, allowed, emphasis=False, is_3d=False):
    cands = []
    for part in registry.parts(kind):
        if not allowed(part):
            continue
        w = part.weight * novelty(history, kind, part.key)
        if is_3d and getattr(part, "only_3d", False):
            w *= 1.6
        if emphasis and part.key in ("front", "zoom", "pop_sing", "approach", "explode", "slanted_wall"):
            w *= 1.5
        cands.append((part.key, w))
    return rng.wpick(cands) if cands else None


def emph_mask(text, words):
    mask = [False] * len(text)
    for w in words:
        start = text.find(w)
        while start >= 0 and w:
            for i in range(start, start + len(w)):
                mask[i] = True
            start = text.find(w, start + len(w))
    return mask


def plan(lines, sections, duration, seed, bpm=0.0, strength=0.7):
    """lines: [model.LineInput] in time order; sections: [(start, end)]."""
    history, out = [], []
    kept = {}                                  # section index -> slots used
    for k, ln in enumerate(lines):
        rng = Rng(h(seed, STAGE_TEXT, ln.index + 1))
        text = ln.text
        n = len(text.replace(" ", ""))
        nxt = lines[k + 1].start if k + 1 < len(lines) else duration
        emphasis = ln.impact or bool(ln.emph_words)
        sec_end = sections[ln.section_index][1] if 0 <= ln.section_index < len(sections) else duration

        # keep the line on stage until the section ends?
        slots = kept.setdefault(ln.section_index, [])
        if ln.persist == "section":
            keep = len(slots) < len(KEEP_SLOTS)
        elif ln.persist == "next":
            keep = False
        else:
            keep = len(slots) < len(KEEP_SLOTS) and sec_end - ln.start > 4.0 and rng.chance(KEEP_CHANCE)
        stage_busy = bool(slots)               # earlier lines of this section are still standing

        def layout_ok(part):
            if part.only_3d and not ln.is_3d:
                return False
            if not part.fits(n):
                return False
            if (keep or stage_busy) and (part.big or not part.anchored):
                return False
            return not keep or part.keepable

        chosen = registry.get("layout", ln.layout)
        if chosen and (ln.is_3d or not chosen.only_3d):
            layout = ln.layout                 # a 3D-only layout asked for on a flat line is ignored
        else:
            layout = _pick(rng, "layout", history, layout_ok, emphasis, ln.is_3d)
        lp = registry.get("layout", layout)
        if (keep or stage_busy) and (lp.big or not lp.anchored) or not lp.keepable:
            keep = False                       # a hand-picked layout that cannot share the stage
        anchor = (0.0, 0.0)
        if keep:
            az, el = KEEP_SLOTS[len(slots)]
            anchor = (az * DEG, el * DEG)
            slots.append(ln.index)

        def motion_ok(kind, allow):
            return lambda part: allow is None or part.key in allow

        enter = ln.enter if registry.get("enter", ln.enter) else _pick(rng, "enter", history, motion_ok("enter", lp.enter_ok), emphasis)
        hold = ln.hold if registry.get("hold", ln.hold) else _pick(rng, "hold", history, lambda p: True)
        exit_ = ln.exit if registry.get("exit", ln.exit) else _pick(rng, "exit", history, motion_ok("exit", lp.exit_ok), emphasis)

        if ln.distance in model.DISTANCE:
            distance = ln.distance
        elif lp.fixed_distance:
            distance = lp.fixed_distance
        elif keep:
            distance = "mid"
        else:
            distance = rng.wpick([("near", 0.5 if emphasis else 0.25), ("mid", 0.6), ("far", 0.05 if emphasis else 0.15)])

        # visible until the next line (or the section end when kept), JIZURA's visEnd rule
        end = sec_end if keep else min(nxt, ln.start + max(3.6, n * 0.5 + 1.2))
        end = max(end, ln.start + 0.5)
        enter_part, exit_part = registry.get("enter", enter), registry.get("exit", exit_)
        exit_dur = min(exit_part.duration, (end - ln.start) * 0.3)
        enter_dur = min(enter_part.duration, (end - ln.start) * 0.4)
        char_times = list(ln.char_times or [ln.start + 0.05 * i for i in range(len(text))])
        params = lp.plan(rng, _Ctx(text, ln.chunks))
        role = "serif" if lp.vertical else ("display" if emphasis else "body")
        out.append(model.LinePlan(
            index=ln.index, text=text, start=ln.start, end=end, section_index=ln.section_index,
            char_times=char_times, emph_mask=emph_mask(text, ln.emph_words), is_3d=ln.is_3d,
            depth=ln.depth, bevel=ln.bevel, font_role=role, layout=layout, layout_params=params,
            enter=enter, hold=hold, exit=exit_, enter_dur=enter_dur, exit_dur=exit_dur,
            distance=distance, persist=keep, anchor=anchor, emphasis=emphasis,
            seed=h(seed, STAGE_TEXT, ln.index + 1, 7)))
        history.append({"layout": layout, "enter": enter, "hold": hold, "exit": exit_})
    return model.Plan(seed=seed, duration=duration, bpm=bpm, lines=out, sections=list(sections))


class _Ctx:
    """What a layout's plan() may look at before placement."""

    def __init__(self, text, chunks):
        self.text = text
        self.chunks = chunks or lyrics.chunk_text(text)
