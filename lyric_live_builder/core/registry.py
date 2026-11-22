"""Part registry: layouts and motions register themselves by kind and key (design §5.6)."""
import math
from dataclasses import dataclass

import numpy as np

from . import xform

_parts = {"layout": {}, "enter": {}, "hold": {}, "exit": {}}
GROUPS = ("basic", "extra", "kinetic", "typo", "horror")
# moods in which おまかせ may pick a part of the group (spec §7.4); a part set by hand is always used
GROUP_MOODS = {"kinetic": ("pop", "glitch", "graphic", "chaos"), "typo": ("editorial", "graphic", "chaos"),
               "horror": ("horror",)}


def group_ok(part, mood):
    allowed = GROUP_MOODS.get(getattr(part, "group", "basic"))
    return allowed is None or (mood or "chaos") in allowed


def register(kind, key):
    def deco(cls):
        part = cls()
        part.key = key
        part.kind = kind
        _parts[kind][key] = part
        return cls
    return deco


def get(kind, key):
    _load()                                   # a hand-picked part must be found before anything listed the parts
    return _parts[kind].get(key)


def keys(kind):
    _load()
    return list(_parts[kind])


def parts(kind):
    _load()
    return list(_parts[kind].values())


def _adv(c):
    from .lyrics import is_latin
    return 0.3 if c.isspace() else 0.55 if is_latin(c) else 1.0


def text_width(text):
    """Width of a line in em, estimated without the font (as the planner runs before baking)."""
    return sum(_adv(c) for c in text)


def size_ratio(part, text, chunks=None, params=None, rng=None):
    """Placed em / set em of `text` in the layout (mid layer, estimated advances): below model.SIZE_KEEP, the
    layout shrinks the text too much (design §7.3). params: the line's own, else drawn from rng."""
    from . import model
    from .lyrics import chunk_text
    em = model.text_em("mid")
    ctx = LayoutCtx(text=text, adv=[_adv(c) for c in text], vadv=[1.0] * len(text), em=em,
                    distance=model.DISTANCE["mid"], eye=model.EYE_HEIGHT, is_3d=part.only_3d, depth=0.15,
                    chunks=chunks or chunk_text(text), char_times=[0.2 * k for k in range(len(text))],
                    anchor=(0.0, 0.0), span=(0.0, 4.0))
    return part.place(ctx, part.plan(rng, ctx) if params is None else params).em / em


_capacity = {}
PROBES = 4                                    # draws of a layout's details tried per width


def capacity(part):
    """Widest line (em of full-width letters) the layout shows at SIZE_KEEP of the text size or more, found by
    placing 1, 2, ... letters once (per text size setting). A quick filter: the planner then checks the line's
    own text and details with size_ratio (design §7.3)."""
    from . import model
    from .rng import Rng
    key = (part.key, model.TEXT_SCALE, tuple(model.TEXT_ANGLE.values()), model.MAX_LINE_ANGLE, model.SIZE_KEEP)
    if key not in _capacity:
        best = 0
        for n in range(1, 25):
            if not part.fits(n):
                continue
            # the layout's own details are drawn per line: a few draws stand in for them
            if all(size_ratio(part, "あ" * n, rng=Rng(n + 100 * k)) >= model.SIZE_KEEP - 1e-9 for k in range(PROBES)):
                best = n
            elif best:
                break
        _capacity[key] = best
    return _capacity[key]


def even_size(lp, pl, params, eye, angle):
    """Scale a placed line as a whole (letters and their spacing, about the letters' middle) so that its biggest
    letter is `angle` degrees seen from the eye (model.EVEN_ANGLE). The motions follow: they work in its em."""
    if not pl.glyphs or lp.own_size:
        return pl
    loc = np.array([g.loc for g in pl.glyphs], dtype=np.float64)
    size = np.array([g.size for g in pl.glyphs], dtype=np.float64)
    mid = loc.mean(axis=0)
    rot = np.broadcast_to(np.asarray(pl.rot, dtype=np.float64), (len(loc), 4))
    want = math.tan(math.radians(angle) / 2)
    k = 1.0
    for _ in range(12):                                   # the distances change as the line grows: until it settles
        d = np.linalg.norm(pl.loc + xform.rotate(rot, mid + k * (loc - mid)) - eye, axis=1)
        step = want / max(float(np.max(k * pl.em * size / 2 / np.maximum(d, 1e-6))), 1e-9)
        k *= step
        if abs(step - 1) < 1e-3:
            break
    for g, p in zip(pl.glyphs, loc):
        g.loc = mid + k * (p - mid)
    if "_em" in params:                                   # the panels' own motion is in board em
        params["_em"] *= k
    pl.em *= k
    return pl


_top = {}


def top(part):
    """Highest point (degrees above the eye) of a line in the layout at the evened size (model.EVEN_ANGLE, or its
    own without it), over probe lines of 2, 4 and 6 letters and two draws of its details. A line kept above the front
    (model.KEEP_ABOVE) is clear of layouts that stay low (design §7.2)."""
    from . import model
    from .lyrics import chunk_text
    from .rng import Rng
    key = (part.key, model.TEXT_SCALE, tuple(model.TEXT_ANGLE.values()), model.EVEN_ANGLE)
    if key not in _top:
        eye = np.array([0.0, 0.0, model.EYE_HEIGHT])
        best = -90.0
        for n in (2, 4, 6):
            if not part.fits(n):
                continue
            text = "あ" * n
            dist = part.fixed_distance or "mid"
            for k in range(2):
                ctx = LayoutCtx(text=text, adv=[1.0] * n, vadv=[1.0] * n, em=model.text_em(dist),
                                distance=model.DISTANCE[dist], eye=model.EYE_HEIGHT, is_3d=part.only_3d, depth=0.15,
                                chunks=chunk_text(text), char_times=[0.2 * i for i in range(n)], anchor=(0.0, 0.0),
                                span=(0.0, 4.0))
                params = part.plan(Rng(n + 100 * k), ctx)
                pl = part.place(ctx, params)
                if model.EVEN_ANGLE:
                    pl = even_size(part, pl, params, eye, model.EVEN_ANGLE * model.TEXT_SCALE)
                if not pl.glyphs:
                    continue
                rot = np.broadcast_to(np.asarray(pl.rot, dtype=np.float64), (len(pl.glyphs), 4))
                v = pl.loc + xform.rotate(rot, np.array([g.loc for g in pl.glyphs])) - eye
                d = np.linalg.norm(v, axis=1)
                el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(d, 1e-9), -1, 1)))
                half = np.degrees(np.arctan(pl.em * np.array([g.size for g in pl.glyphs]) / 2 / np.maximum(d, 1e-9)))
                best = max(best, float((el + half).max()))
        _top[key] = best
    return _top[key]


_above = {}


def from_above(part):
    """An entrance whose letters come down from more than a letter above their place (falling, dropping)."""
    if part.key not in _above:
        n = 4
        ctx = MotionCtx(n=n, rest=np.zeros((n, 3)), em=1.0, start=0.0, end=4.0, char_times=np.linspace(0, 0.3, n),
                        bpm=120.0, seed=3, strength=1.0, words=np.zeros(n, dtype=int), chars=tuple("あいうえ"))
        p = np.broadcast_to(np.linspace(0.0, 1.0, 25), (n, 25))
        d = part.evaluate(ctx, p)
        _above[part.key] = bool(np.asarray(d.loc)[..., 2].max() > 1.0)
    return _above[part.key]


def _load():
    # importing the part modules runs their @register decorators
    from .parts import layouts_3d, layouts_basic, motions_enter, motions_enter_jz, motions_exit, motions_exit_jz, motions_hold, motions_hold_jz, layouts_jz  # noqa: F401


# ---------------- layouts ----------------

@dataclass
class GlyphPlacement:
    char_index: int                   # index into the line text
    loc: np.ndarray                   # (3,) in the line frame
    rot: np.ndarray = None            # (4,) ; None = identity
    vertical: bool = False            # rotated 90° for vertical writing
    size: float = 1.0                 # times the line's em (mixed sizes)


@dataclass
class Placement:
    loc: np.ndarray                   # line group position (world)
    rot: np.ndarray                   # line group rotation (world)
    em: float                         # glyph size in metres
    glyphs: list


@dataclass
class LayoutCtx:
    text: str
    adv: list                         # horizontal advance per character, em
    vadv: list                        # vertical advance per character, em
    em: float                         # glyph size from the visual angle at `distance`
    distance: float
    eye: float
    is_3d: bool
    depth: float
    chunks: list
    char_times: list
    anchor: tuple                     # (azimuth, elevation)
    span: tuple = (0.0, 0.0)          # (start, end) of the line on stage


class LayoutPart:
    name = ""
    tags = ()
    weight = 1.0
    group = "basic"
    supports_2d = True
    supports_3d = True
    only_3d = False
    big = False                       # occupies a wide region; not used while lines are kept on stage
    anchored = True                   # honours the planner's anchor
    keepable = True                   # may stay in a side slot until the section ends
    fixed_distance = None             # distance layer forced by the layout
    own_size = False                  # its size is part of the effect: not evened out (model.EVEN_ANGLE)
    enter_ok = None                   # allowed entrances (None = any)
    exit_ok = None
    vertical = False

    def fits(self, n_chars):
        return n_chars >= 1

    def plan(self, rng, ctx):
        return {}

    def place(self, ctx, params):
        raise NotImplementedError

    def group_motion(self, ctx, params, placement, t):
        """Optional animation of the line group: t (T,) -> (loc (T,3), rot (T,4)) or None."""
        return None

    def shown(self, ctx, params, placement):
        """Optional per-glyph (on, off) times that narrow the line's visibility, or None."""
        return None


# ---------------- motions ----------------

class Delta:
    """Offsets added to the rest pose, per glyph (G) and time sample (T); location is in the
    glyph's own rest frame (x along the text, z up, -y toward the viewer)."""

    def __init__(self, g, t, loc=None, rot=None, scale=None, alpha=None, mask=None):
        shape = (g, t)
        self.loc = np.zeros(shape + (3,)) if loc is None else np.broadcast_to(loc, shape + (3,)).astype(np.float64)
        self.rot = np.broadcast_to(xform.IDENTITY, shape + (4,)).copy() if rot is None else \
            np.broadcast_to(rot, shape + (4,)).astype(np.float64)
        self.scale = np.ones(shape + (3,)) if scale is None else np.broadcast_to(scale, shape + (3,)).astype(np.float64)
        self.alpha = np.ones(shape) if alpha is None else np.broadcast_to(alpha, shape).astype(np.float64)
        # how much of the glyph its part's mask shows (1 = all; design §5.6)
        self.mask = np.ones(shape) if mask is None else np.broadcast_to(mask, shape).astype(np.float64)

    def then(self, other):
        """Combine two deltas (both apply)."""
        return Delta(self.loc.shape[0], self.loc.shape[1], self.loc + other.loc, xform.mul(other.rot, self.rot),
                     self.scale * other.scale, self.alpha * other.alpha, self.mask * other.mask)


@dataclass
class MotionCtx:
    n: int                            # glyphs
    rest: np.ndarray                  # (G, 3) rest positions in the line frame
    em: float
    start: float
    end: float
    char_times: np.ndarray            # (G,) absolute seconds
    bpm: float
    seed: int
    strength: float = 0.7             # fx motion (0..1)
    words: np.ndarray = None          # (G,) number of the chunk (word) each glyph belongs to
    chars: tuple = None               # (G,) the glyphs' characters


class MotionPart:
    name = ""
    tags = ()
    weight = 1.0
    group = "basic"
    stagger = 0.04                    # seconds between glyphs
    uses_mask = False                 # returns Delta.mask; mask_shape() says how it cuts
    line_fx = False                   # draws on a plane in front of the line too (wipe bar, checker tiles)
    band_copies = 0                   # slides the glyphs in as bands (copies, design §5.6); see band_count
    band_axis = "y"                   # "y": horizontal bands (mask kind 4), "x": vertical bands (kind 10)
    mask_cell = None                  # (x0, y0, x1, y1) em: the mask's frame is each glyph's own, not the line

    def band_count(self, width_em):
        return self.band_copies

    def band_start(self, b, k, g):
        """Progress at which band b of glyph k (of g) appears."""
        return 0.0

    def band_motion(self, p, b, n, k, g, width, height, em):
        """(dx, dz) in metres of band b (of n) of glyph k (of g) at progress p."""
        return 0.0 * p, 0.0 * p

    def band_fade(self, p, b, n, k, g):
        """Opacity of a band copy at progress p (None: always opaque)."""
        return None

    def mask_shape(self, ctx):
        """(kind, value, seed, w): 1 wipe (value 0 from the left, 1 from the right), 2 bands (value: count,
        alternate sides), 3 checker (value: cell size in em), 4 one band only (value: count, seed: the band),
        5 iris, 6 diagonal (value: direction), 7 blinds, 8 shutter, 9 window (value / seed: the glyph's x / up
        offset in em at progress 0), 10 one vertical band only. See LLBMask.cginc / preview mask_reveal."""
        return (0.0, 0.0, 0.0, 0.0)

    def windows(self, ctx, dur):
        """Per glyph start times (G,) of this motion's window of length dur."""
        return ctx.start + np.arange(ctx.n) * self.stagger

    def evaluate(self, ctx, p):
        """p (G, T): progress 0..1 (enter/exit) or seconds since the hold began. -> Delta."""
        raise NotImplementedError
