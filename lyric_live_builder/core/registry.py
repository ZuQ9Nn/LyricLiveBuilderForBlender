"""Part registry: layouts and motions register themselves by kind and key (design §5.6)."""
from dataclasses import dataclass

import numpy as np

from . import xform

_parts = {"layout": {}, "enter": {}, "hold": {}, "exit": {}}


def register(kind, key):
    def deco(cls):
        part = cls()
        part.key = key
        part.kind = kind
        _parts[kind][key] = part
        return cls
    return deco


def get(kind, key):
    return _parts[kind].get(key)


def keys(kind):
    _load()
    return list(_parts[kind])


def parts(kind):
    _load()
    return list(_parts[kind].values())


def _load():
    # importing the part modules runs their @register decorators
    from .parts import layouts_3d, layouts_basic, motions_enter, motions_exit, motions_hold  # noqa: F401


# ---------------- layouts ----------------

@dataclass
class GlyphPlacement:
    char_index: int                   # index into the line text
    loc: np.ndarray                   # (3,) in the line frame
    rot: np.ndarray = None            # (4,) ; None = identity
    vertical: bool = False            # rotated 90° for vertical writing


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
    supports_2d = True
    supports_3d = True
    only_3d = False
    big = False                       # occupies a wide region; not used while lines are kept on stage
    anchored = True                   # honours the planner's anchor
    keepable = True                   # may stay in a side slot until the section ends
    fixed_distance = None             # distance layer forced by the layout
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

    def __init__(self, g, t, loc=None, rot=None, scale=None, alpha=None):
        shape = (g, t)
        self.loc = np.zeros(shape + (3,)) if loc is None else np.broadcast_to(loc, shape + (3,)).astype(np.float64)
        self.rot = np.broadcast_to(xform.IDENTITY, shape + (4,)).copy() if rot is None else \
            np.broadcast_to(rot, shape + (4,)).astype(np.float64)
        self.scale = np.ones(shape + (3,)) if scale is None else np.broadcast_to(scale, shape + (3,)).astype(np.float64)
        self.alpha = np.ones(shape) if alpha is None else np.broadcast_to(alpha, shape).astype(np.float64)

    def then(self, other):
        """Combine two deltas (both apply)."""
        return Delta(self.loc.shape[0], self.loc.shape[1], self.loc + other.loc, xform.mul(other.rot, self.rot),
                     self.scale * other.scale, self.alpha * other.alpha)


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


class MotionPart:
    name = ""
    tags = ()
    weight = 1.0
    stagger = 0.04                    # seconds between glyphs

    def windows(self, ctx, dur):
        """Per glyph start times (G,) of this motion's window of length dur."""
        return ctx.start + np.arange(ctx.n) * self.stagger

    def evaluate(self, ctx, p):
        """p (G, T): progress 0..1 (enter/exit) or seconds since the hold began. -> Delta."""
        raise NotImplementedError
