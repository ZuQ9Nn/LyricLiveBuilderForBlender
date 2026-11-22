# Line composition follows JIZURA's plan() (src/08_planner.js: novelty weighting, emphasis,
# per-line seeds, cut counts), MIT License, Copyright (c) 2026 hakoniwa. Rewritten for 3D space.
"""Plan: which layout / motions / distance each line uses and where it stands (design §5.5)."""
import math
from dataclasses import replace

from . import lyrics, model, moods, registry, styles, world
from .parts import gimmicks
from .rng import Rng, h

STAGE_TEXT = world.STAGE_TEXT        # seed stage of the text composition ("change only this" re-rolls stages)
DEG = math.pi / 180
# side slots for lines kept until the section ends: (azimuth, elevation); the front stays free. The newest kept line
# waits above the front (model.KEEP_ABOVE) and moves to the next free side slot when another one comes up
# out past the front lines (evened letters reach about ±90°) and the line above; the rows of ±110° and ±155° stay
# about 7° apart once the lines shrink to KEPT_LINE_ANGLE
KEEP_SLOTS = [(-110, 0), (110, 0), (-110, 22), (110, 22), (-155, 8), (155, 8)]
KEEP_CHANCE = 0.22
# a kept line first appears in front, then glides up above the front as the next line comes in
GLIDE_LEAD = 0.9                     # seconds before the next line starts
GLIDE_DUR = 1.0
END_GAP = 0.25                       # seconds: every line has left before the song ends (Unity holds the last frame)
# kept lines leave together at the section end; these exits stay in place (no falling into the slot below)
KEEP_EXITS = ("fade", "dust", "fly_away", "shrink", "blur", "blur_stagger", "wipe", "crumble", "lamp_off")
MIN_CUT = 0.22                       # seconds between the cuts of a line (JIZURA)
MAX_CUTS = 6                         # as the line's "Cuts" menu
# title card ([ti:] in the lyrics), JIZURA's plan(): from 0.1 s until just before the first line, if that is late enough
TITLE_START, TITLE_GAP, TITLE_MIN_LEAD = 0.1, 0.04, 1.1
TITLE_ENTERS = ("blur", "type", "wipe", "assemble")
TITLE_EXITS = ("blur", "fade", "wipe")      # JIZURA's drift exit has no counterpart here: fade
# the artist ([ar:]) under the title, JIZURA's title layout: small (a share of the title's letters as baked; JIZURA
# about 0.2-0.25, a little bigger to read in VR), in the body font, below by 0.95 title sizes, fading in 0.3 s later
ARTIST_SIZE, ARTIST_BELOW, ARTIST_DELAY = 0.4, 0.95, 0.3


def novelty(history, key, value):
    w = 1.0
    for d, item in enumerate(reversed(history[-6:])):
        if item.get(key) == value:
            w *= 0.2 if d < 2 else 0.6
    return w


def _pick(rng, kind, history, allowed, emphasis=False, is_3d=False, settings=None):
    cands = []
    off = settings.disabled.get(kind, ()) if settings else ()
    mood = settings.mood if settings else ""
    for part in registry.parts(kind):
        if not allowed(part) or not registry.group_ok(part, mood):
            continue
        w = part.weight * novelty(history, kind, part.key) * moods.favours(mood, part.tags)
        if is_3d and getattr(part, "only_3d", False):
            w *= 1.6
        if emphasis and part.key in ("front", "zoom", "pop_sing", "approach", "explode", "slanted_wall"):
            w *= 1.5
        cands.append((part.key, w, part.key in off))
    on = [(k, w) for k, w, disabled in cands if not disabled]
    pool = on or [(k, w) for k, w, _ in cands]           # everything turned off: ignore the switches
    return rng.wpick(pool) if pool else None


def emph_mask(text, words):
    mask = [False] * len(text)
    for w in words:
        start = text.find(w)
        while start >= 0 and w:
            for i in range(start, start + len(w)):
                mask[i] = True
            start = text.find(w, start + len(w))
    return mask


def _section_input(s):
    if isinstance(s, model.SectionInput):
        return s
    return model.SectionInput(s[0], s[1], *s[2:])


def _compose(ln, rng, history, keep, stage_busy, settings, look, above=False):
    """Layout, motions and distance of one line, drawn from rng in a fixed order; the layout's details come from
    the line's look seed (its own stream: fixing the parts by hand or by paste leaves them as they were).
    above: a kept line waits above the front: no layout reaching up to it, no entrance coming down through it."""
    n = len(ln.text.replace(" ", ""))
    width = registry.text_width(ln.text)
    # a line as wide as the front holds keeps its size; a wider one (left whole by hand) shrinks anyway
    sized_line = width <= registry.capacity(registry.get("layout", "front"))
    emphasis = ln.impact or bool(ln.emph_words)

    def layout_ok(part, sized=True):
        if part.only_3d and not ln.is_3d:
            return False
        if not part.fits(n):
            return False
        if sized and sized_line and width > registry.capacity(part):     # would shrink it below SIZE_KEEP
            return False
        if (keep or stage_busy) and (part.big or not part.anchored):
            return False
        if above and registry.top(part) > model.ABOVE_CLEAR:
            return False
        return not keep or part.keepable

    chosen = registry.get("layout", ln.layout)
    if chosen and (ln.is_3d or not chosen.only_3d):
        layout = ln.layout                     # a 3D-only layout asked for on a flat line is ignored
    else:
        # the line's own text and details placed once: a layout that still shrinks it too much is dropped
        dropped = set()
        while True:
            layout = _pick(rng, "layout", history, lambda p: p.key not in dropped and layout_ok(p), emphasis,
                           ln.is_3d, settings)
            if layout is None or not sized_line:
                break
            part = registry.get("layout", layout)
            params = part.plan(Rng(h(look, 11)), _Ctx(ln.text, ln.chunks))
            if registry.size_ratio(part, ln.text, ln.chunks, params) >= model.SIZE_KEEP - 1e-9:
                break
            dropped.add(layout)
        # none keeps the size (a line cut by hand, one long word): any that fits, with smaller letters
        layout = layout or _pick(rng, "layout", history, lambda p: layout_ok(p, False), emphasis, ln.is_3d, settings)
    lp = registry.get("layout", layout)
    if (keep or stage_busy) and (lp.big or not lp.anchored) or not lp.keepable:
        keep = False                           # a hand-picked layout that cannot share the stage

    def motion_ok(allow, keep_only=()):
        return lambda part: (allow is None or part.key in allow) and (not keep_only or part.key in keep_only)

    low = (lambda part: not registry.from_above(part)) if above else (lambda part: True)
    enter = ln.enter if registry.get("enter", ln.enter) else \
        _pick(rng, "enter", history, lambda p: motion_ok(lp.enter_ok)(p) and low(p), emphasis, settings=settings)
    hold = ln.hold if registry.get("hold", ln.hold) else _pick(rng, "hold", history, lambda p: True, settings=settings)
    exit_ = ln.exit if registry.get("exit", ln.exit) else \
        _pick(rng, "exit", history, motion_ok(lp.exit_ok, KEEP_EXITS if keep else ()), emphasis, settings=settings)
    # every line stands in the middle layer (spec §7.1); layouts on the floor / around the audience bring their own
    distance = lp.fixed_distance or "mid"
    params = lp.plan(Rng(h(look, 11)), _Ctx(ln.text, ln.chunks))
    return {"layout": layout, "lp": lp, "keep": keep, "enter": enter, "hold": hold, "exit": exit_,
            "distance": distance, "params": params}


def _line_plan(ln, c, style, end, mask, seed, colors, anchor=(0.0, 0.0), glide=None, cut=0):
    emphasis = ln.impact or bool(ln.emph_words)
    enter_part, exit_part = registry.get("enter", c["enter"]), registry.get("exit", c["exit"])
    role = "serif" if c["lp"].vertical else ("display" if emphasis else styles.STYLES[style]["body"])
    return model.LinePlan(
        index=ln.index, text=ln.text, start=ln.start, end=end, section_index=ln.section_index,
        char_times=list(ln.char_times or [ln.start + 0.05 * i for i in range(len(ln.text))]), emph_mask=mask,
        is_3d=ln.is_3d, depth=ln.depth, bevel=ln.bevel, font_role=role, layout=c["layout"], layout_params=c["params"],
        enter=c["enter"], hold=c["hold"], exit=c["exit"], enter_dur=min(enter_part.duration, (end - ln.start) * 0.4),
        exit_dur=min(exit_part.duration, (end - ln.start) * 0.3), distance=c["distance"], persist=c["keep"],
        anchor=anchor, emphasis=emphasis, seed=seed, glide=glide, colors=colors, guide=ln.guide,
        particle=ln.particle, impact=ln.impact, cut=cut)


def _cut_count(ln):
    """Cuts of a line: as set; on Planner's Choice (0) one per '/' chunk of the lyrics (JIZURA), and more when a
    part is still too wide to keep the text size in its layout (the hand-picked one, else the front; design §7.3).
    A line kept to the section end by hand is not cut for size (it could not stay)."""
    if ln.cuts:
        return ln.cuts
    n = min(MAX_CUTS, len(ln.chunks)) if ln.chunks and len(ln.chunks) > 1 else 1
    if ln.persist == "section":
        return n
    part = registry.get("layout", ln.layout)
    cap = registry.capacity(part) if part and (ln.is_3d or not part.only_3d) else 0
    cap = cap or registry.capacity(registry.get("layout", "front"))
    chunks = ln.chunks or lyrics.chunk_text(ln.text)
    while n < len(ln.text) and any(registry.text_width(p) > cap for _, p in lyrics.split_line(ln.text, chunks, n)):
        n += 1
    return n


def _cut_lines(ln, end):
    """The parts of a line set to several cuts: [(offset in the line, LineInput)], [] = shown whole (design §5.5.1)."""
    pieces = lyrics.split_line(ln.text, ln.chunks or lyrics.chunk_text(ln.text),
                               min(ln.cuts, int((end - ln.start) / MIN_CUT)))
    if len(pieces) < 2:
        return []
    times = ln.char_times or [ln.start + 0.05 * i for i in range(len(ln.text))]
    bounds = [ln.start] + [times[min(off, len(times) - 1)] for off, _ in pieces[1:]] + [end]
    for k in range(1, len(pieces)):
        bounds[k] = max(bounds[k], bounds[k - 1] + MIN_CUT)
    for k in range(len(pieces) - 1, 0, -1):
        bounds[k] = min(bounds[k], bounds[k + 1] - MIN_CUT)
    # "seed": _cut_seed; "distance": saved by an older version (the layer is no longer chosen)
    specs = [{f: v for f, v in s.items() if f not in ("seed", "distance")} for s in ln.cut_specs or []]
    return [(off, replace(ln, text=piece, start=bounds[k], end=bounds[k + 1], char_times=times[off:off + len(piece)],
                          chunks=None, emph_words=[w for w in ln.emph_words if w in piece], impact=ln.impact and k == 0,
                          **(specs[k] if k < len(specs) else {})))
            for k, (off, piece) in enumerate(pieces)]


def _cut_look(ln, k, cut_seed):
    """Look seed of cut k: the copied / locked one when there is, else from the cut's own seed."""
    specs = ln.cut_specs or []
    seed = specs[k].get("seed") if k < len(specs) else None
    return int(seed) if seed else h(cut_seed, 7)


def _compose_cuts(ln, end, history, settings, text_seed, style, world_, above=False):
    """LinePlans of the cuts. Their draws stay inside the line, so other lines are left as they are."""
    recent, out = list(history), []
    mask = emph_mask(ln.text, ln.emph_words)
    for k, (off, cut) in enumerate(_cut_lines(ln, end)):
        # in front only: no gaze guide leads to a later cut
        cut_seed = h(text_seed, STAGE_TEXT, ln.index + 1, 100 + k, ln.seed_offset)
        look = _cut_look(ln, k, cut_seed)
        c = _compose(cut, Rng(cut_seed), recent, False, True, settings, look, above)
        recent.append({key: c[key] for key in ("layout", "enter", "hold", "exit")})
        out.append(_line_plan(cut, c, style, cut.end, mask[off:off + len(cut.text)], look,
                              world.line_colors(world_, style, settings.accent, cut.start), cut=k))
    return out


def plan(lines, sections, duration, seed, bpm=0.0, settings=None):
    """lines: [model.LineInput] in time order; sections: [model.SectionInput] or [(start, end[, kind])]."""
    settings = settings or model.Settings()
    secs = [_section_input(s) for s in sections]
    style = settings.style or styles.DEFAULT
    section_plans, world_ = world.plan_world(secs, lines, seed, settings, style)
    text_seed = world.stage_seed(settings, seed, STAGE_TEXT)
    keep_chance = KEEP_CHANCE * (0.5 + settings.fx_value("density"))
    history, out = [], []
    kept = {}                                  # section index -> slots used
    for k, ln in enumerate(lines):
        ln = replace(ln, cuts=_cut_count(ln))
        rng = Rng(h(text_seed, STAGE_TEXT, ln.index + 1))
        text = ln.text
        n = len(text.replace(" ", ""))
        nxt = lines[k + 1].start if k + 1 < len(lines) else duration
        sec_end = secs[ln.section_index].end if 0 <= ln.section_index < len(secs) else duration

        # keep the line on stage until the section ends?
        slots = kept.setdefault(ln.section_index, [])
        room = len(slots) < len(KEEP_SLOTS) + 1               # the side slots and the place above
        if ln.persist == "section":
            keep = room
        elif ln.persist == "next":
            keep = False
        else:
            keep = room and sec_end - ln.start > 4.0 and rng.chance(keep_chance)
        keep = keep and ln.cuts < 2            # the parts follow each other: nothing can stand aside
        stage_busy = bool(slots)               # earlier lines of this section are still standing (one above)
        look = ln.look_seed or h(text_seed, STAGE_TEXT, ln.index + 1, 7, ln.seed_offset)
        # the first draw as before any re-roll (its size check places the line with the look seed)
        c = _compose(ln, rng, history, keep, stage_busy, settings,
                     ln.look_seed or h(text_seed, STAGE_TEXT, ln.index + 1, 7, 0), stage_busy)
        keep = c["keep"]
        # a re-rolled line draws again with its own stream; the others still see the first draw
        # (novelty history, slots), so re-rolling one line changes only that line
        history.append({key: c[key] for key in ("layout", "enter", "hold", "exit")})
        if ln.seed_offset:
            c = _compose(ln, Rng(h(text_seed, STAGE_TEXT, ln.index + 1, ln.seed_offset)), history[:-1], keep,
                         stage_busy, settings, look, stage_busy)
            c["keep"] = keep = keep and c["keep"]
        anchor = (0.0, 0.0)
        gs = max(ln.start, nxt - GLIDE_LEAD)
        if keep and nxt < sec_end:             # the last kept line of a section simply stays in front
            anchor = (0.0, model.KEEP_ABOVE * DEG)
            if slots:                          # the line above makes room: on to the next free side slot
                prev = out[slots[-1]]
                az, el = KEEP_SLOTS[len(slots) - 1]
                a0 = max(gs - GLIDE_DUR / 2, prev.glide[1])     # it leaves as this one comes up
                prev.anchor, prev.aside = (az * DEG, el * DEG), (a0, a0 + GLIDE_DUR)
            slots.append(len(out))

        # visible until the next line (or the section end when kept), JIZURA's visEnd rule
        end = sec_end if keep else min(nxt, ln.start + max(3.6, n * 0.5 + 1.2))
        end = max(end, ln.start + 0.5)
        end = max(min(end, duration - END_GAP), ln.start + 0.1)     # gone before the song ends (spec §6.2)
        glide = (gs, gs + GLIDE_DUR) if keep and anchor != (0.0, 0.0) else None
        line = _line_plan(ln, c, style, end, emph_mask(text, ln.emph_words), look,
                          world.line_colors(world_, style, settings.accent, ln.start), anchor, glide)
        if ln.cuts > 1:
            line.cuts = _compose_cuts(ln, end, history[:-1], settings, text_seed, style, world_, stage_busy) or None
        out.append(line)
    emitters = [world.fit_to_song(e, duration - END_GAP)                 # gone before the song ends (spec §6.2)
                for e in world.plan_particles(section_plans, out, seed, settings)]
    events = world.plan_events(section_plans, out, world_, settings)
    fx = {key: settings.fx_value(key) for key in model.FX_DEFAULTS}
    gim = gimmicks.plan(out, lines, duration, world.stage_seed(settings, seed, world.STAGE_GIMMICK), fx, world.STAGE_GIMMICK,
                        settings.disabled, settings.user_assets, settings.user_words, lyrics.chunk_text)
    return model.Plan(seed=seed, duration=duration, bpm=bpm, lines=out, sections=[(s.start, s.end) for s in secs],
                      mood=settings.mood, style=style, fx=fx, section_plans=section_plans, world=world_,
                      emitters=emitters, events=events, gimmicks=gim,
                      spectrum=gimmicks.plan_spectrum(section_plans, fx, settings.spectrum, settings.energy_rate),
                      **_title(settings, lines, duration, text_seed, style, world_))


def _title(settings, lines, duration, text_seed, style, world_):
    """The title card: the song title in the heading font, in front, until just before the first line, and the
    artist small under it. {"title": LinePlan or None, "artist": LinePlan or None}"""
    text = (settings.title or "").strip()
    first = lines[0].start if lines else duration
    if not text or first < TITLE_MIN_LEAD:
        return {}
    rng = Rng(h(text_seed, 999))
    end = first - TITLE_GAP
    enter, exit_ = rng.pick(list(TITLE_ENTERS)), rng.pick(list(TITLE_EXITS))
    colors = world.line_colors(world_, style, settings.accent, TITLE_START)

    def card(index, words, start, role, enter, exit_, anchor, size, seed):
        span = end - start
        return model.LinePlan(
            index=index, text=words, start=start, end=end, section_index=0,
            char_times=[start + 0.05 * i for i in range(len(words))], emph_mask=[False] * len(words),
            is_3d=False, depth=0.0, bevel=0.0, font_role=role, layout="front", layout_params={},
            enter=enter, hold="still", exit=exit_, enter_dur=min(registry.get("enter", enter).duration, span * 0.4),
            exit_dur=min(registry.get("exit", exit_).duration, span * 0.3), distance="mid", persist=False,
            anchor=anchor, emphasis=True, seed=seed, colors=colors, size=size)
    out = {"title": card(-1, text, TITLE_START, "display", enter, exit_, (0.0, 0.0), 1.0, h(text_seed, 999, 1))}
    artist = (settings.artist or "").strip()
    if artist and end - TITLE_START - ARTIST_DELAY > 0.5:
        # the title's letter size as baked (a long title shrinks to the widest line), roughly in angles
        full = model.text_angle("mid", True)
        size = min(full, model.MAX_LINE_ANGLE / max(registry.text_width(text), 1e-6))
        out["artist"] = card(-2, artist, TITLE_START + ARTIST_DELAY, styles.STYLES[style]["body"], "fade", "fade",
                             (0.0, -ARTIST_BELOW * size * DEG), ARTIST_SIZE * size / full, h(text_seed, 999, 2))
    return out


class _Ctx:
    """What a layout's plan() may look at before placement."""

    def __init__(self, text, chunks):
        self.text = text
        self.chunks = chunks or lyrics.chunk_text(text)


def subset(plan, t0, t1, line=None):
    """What the trial view shows from t0 to t1: one line (or none) with its stage object, and the world around it."""
    return replace(plan, lines=[x for x in plan.lines if x.index == line],
                   title=plan.title if plan.title and plan.title.start < t1 and plan.title.end > t0 else None,
                   artist=plan.artist if plan.artist and plan.artist.start < t1 and plan.artist.end > t0 else None,
                   gimmicks=[g for g in plan.gimmicks if g["line"] == line],
                   emitters=[e for e in plan.emitters if e["start"] < t1 and e["end"] > t0],
                   events=[e for e in plan.events if t0 <= e["t"] <= t1])

