"""Stage gimmicks: an object × a way of appearing × the moment of a line (spec §8.3, design §8.3)."""
import math

from .. import color, gimmick_shapes as shapes, model
from .. import synonyms
from ..rng import Rng, h

DEG = math.pi / 180
ANGLE = 20.0                         # visual angle of a standard object, degrees (a 1.4 m object at 4 m; 40° was too big)
RADIUS = 4.0                         # where objects stand, metres from the audience
AIR = 2.3                            # base height of floating objects
SIDE = (38.0, 58.0)                  # degrees beside the line: objects stay out of the text
MIN_TIME, MAX_TIME = 2.5, 6.0        # stay on stage, seconds (a line kept for a whole section does not hold it)
PER_SECTION = 3
MIN_CHANCE = 0.35                    # a matching line gets an object with this chance at strength 0...

SHOWS = {"floor": {"name": "Rise from the Floor", "dur": 0.7}, "sky": {"name": "Fall from the Sky", "dur": 0.9},
         "wall": {"name": "Push out of the Wall", "dur": 0.7}, "pop": {"name": "Pop", "dur": 0.4},
         "flip": {"name": "Flip the Floor", "dur": 0.9}, "open": {"name": "Open a Box", "dur": 1.1},
         "dissolve": {"name": "Melt Away", "dur": 0.8}}
SHOW_ORDER = tuple(SHOWS)
EXIT = 0.35                          # shrink away (Melt Away uses its own duration)
BARS = 24
BAR_RADIUS = 8.4                     # outside the objects (RADIUS); the bars are as big to the eye as at 4.2 m
BAR_WIDTH = 0.44
BAR_MIN = 0.08
BAR_HEIGHT = 2.4
BAR_RATE = 20.0                      # keys per second before decimation


def _pick_show(rng, spec_air, off):
    # falling and rising need the floor, so floating objects only pop, push out or melt
    pool = [k for k in SHOW_ORDER if k not in off and not (spec_air and k in ("floor", "flip", "open", "sky"))]
    return rng.pick(pool) if pool else "pop"


def _word(ln, chunks):
    """The emblem's word: an emphasized word, else the longest chunk."""
    if ln.emph_words:
        return ln.emph_words[0]
    return max(chunks or [ln.text], key=len).strip()[:8]


def plan(lines, inputs, duration, seed, fx, stage, disabled=None, user_assets=None, user_words=None, chunk=None):
    """lines: LinePlans; inputs: their LineInputs; seed: the gimmick stage's seed; stage: its number.
    user_assets: {tag: {"file", "name"}}. Returns [{line, tag, word, source, show, ...}]."""
    strength = fx.get("gimmick", 0.6)
    off_tags = set((disabled or {}).get("gimmick", ()))
    off_shows = set((disabled or {}).get("show", ()))
    chance = MIN_CHANCE + (1 - MIN_CHANCE) * strength
    used, last_side, out = {}, {}, []
    by_index = {x.index: x for x in inputs}
    for ln in lines:
        inp = by_index[ln.index]
        wanted = inp.gimmick
        if wanted == "none":
            continue
        rng = Rng(h(seed, stage, ln.index + 1))
        tag, word = "", inp.gimmick_word
        if wanted == "emblem":
            source = "emblem"
        else:
            hits = [x for x in synonyms.find(ln.text, user_words) if x[0] not in off_tags or wanted]
            if wanted:
                tag = wanted
            elif hits:
                tag, word = hits[0][0], word or hits[0][1]
            if not tag:
                continue
            source = ("user" if tag in (user_assets or {}) else "builtin" if tag in shapes.SHAPES else "emblem")
        roll = rng()                                         # drawn always: a choice here leaves the others alone
        if not wanted:
            count = used.get(ln.section_index, 0)
            if strength <= 0 or count >= max(1, round(PER_SECTION * (0.4 + strength))):
                continue
            if roll > chance and not ln.emphasis:
                continue
        used[ln.section_index] = used.get(ln.section_index, 0) + 1
        word = word or _word(inp, chunk(ln.text) if chunk else None)
        air = source != "user" and source != "emblem" and shapes.SHAPES[tag][3]
        show = inp.gimmick_show or _pick_show(rng, air, off_shows)
        if air and show in ("floor", "flip", "open"):
            air = False                                      # chosen by hand: it stands on the floor
        side = last_side.get(ln.section_index, 1 if rng.chance(0.5) else -1) * -1
        last_side[ln.section_index] = side
        rel = shapes.SHAPES[tag][4] if source == "builtin" else 1.0
        az = ln.anchor[0] + side * rng.range(*_side(ln, rel)) * DEG
        size = 2 * RADIUS * math.tan(ANGLE * DEG / 2) * rel
        end = min(min(max(ln.end, ln.start + MIN_TIME), ln.start + MAX_TIME) + 0.3, duration)
        colour = shapes.SHAPES[tag][2] if source == "builtin" else ""
        out.append({"line": ln.index, "tag": tag, "word": word, "source": source, "show": show, "start": ln.start,
                    "end": max(end, ln.start + 0.1), "az": az, "air": bool(air), "size": size, "color": colour,
                    "asset": (user_assets or {}).get(tag), "role": ln.font_role, "accent": (ln.colors or {}).get("accent")})
    return out


def _side(ln, rel):
    """Degrees beside the line's anchor: SIDE, or further out when the line is wide (big letters)."""
    n = sum(1 for c in ln.text if not c.isspace())
    limit = model.KEPT_LINE_ANGLE if ln.glide else model.MAX_LINE_ANGLE
    half = min(limit, n * model.text_angle(ln.distance, ln.emphasis)) / 2
    lo = max(SIDE[0], half + ANGLE * rel / 2 + 4.0)
    return lo, max(SIDE[1], lo + 20.0)


def plan_spectrum(section_plans, fx, levels, rate):
    """Bars for the sections chosen in the effects panel, in each section's accent colour."""
    mode = fx.get("spectrum", "chorus")
    if levels is None or not len(levels) or mode == "off":
        return None
    windows = [(s.start, s.end, tuple(color.linear(s.palette.get("accent", "#FFFFFF"))))
               for s in section_plans if mode == "all" or s.kind == "chorus"]
    return {"levels": levels, "rate": rate, "windows": windows}
