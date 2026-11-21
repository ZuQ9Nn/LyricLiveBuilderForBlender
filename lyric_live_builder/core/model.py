"""Data passed between planner, parts, bake, preview and export (no bpy)."""
import math
from dataclasses import dataclass, field

import numpy as np

# distance layers (metres from the eye to the line, design §7.1)
DISTANCE = {"near": 1.2, "mid": 3.5, "far": 8.0}
EYE_HEIGHT = 1.5
MIN_EYE_DISTANCE = 0.6            # nothing comes closer to the eye (design §7.2)

# ---------------- text size: a developer setting, not on the panels (internal-docs/text_size.md) ----------------
# Visual angle of one character (1 em), degrees, per distance layer. ParticleLive's mid lines are about 12°; 12°
# still read small in VR once long lines shrank to fit, so lines too wide are cut into parts instead (design §7.3).
# 28° cut long Japanese lines too often: 21° (about 3 times the earlier real size, 5 letters a part).
TEXT_ANGLE = {"near": 21.0, "mid": 21.0, "far": 21.0}
EMPH_FACTOR = 5.5 / 3.5           # emphasized lines are this much bigger
TEXT_SCALE = 1.0                  # multiplies every text size (1.2 = 20 % bigger)
MAX_LINE_ANGLE = 70.0             # widest horizontal extent of a flat line, degrees: longer lines get smaller letters
KEPT_LINE_ANGLE = 38.0            # lines kept in the side slots (±62°, ±105°) stay this narrow: clear of each other
SIZE_KEEP = 0.7                   # a line (or part) may shrink to this share of the size; wider ones are cut into parts


def text_angle(distance, emphasis=False):
    """Visual angle (degrees) of 1 em of a line at a distance layer ("near" | "mid" | "far")."""
    return TEXT_ANGLE[distance] * TEXT_SCALE * (EMPH_FACTOR if emphasis else 1.0)


def text_em(distance, emphasis=False):
    """1 em in metres of a line at a distance layer."""
    return 2 * DISTANCE[distance] * math.tan(math.radians(text_angle(distance, emphasis)) / 2)


@dataclass
class LineInput:
    """One lyric line as the planner sees it (from the scene properties)."""
    index: int
    text: str
    start: float
    end: float
    section_index: int = 0
    char_times: list = None
    emph_words: list = field(default_factory=list)
    impact: bool = False
    chunks: list = None
    # per-line overrides; "" / None = left to the planner
    is_3d: bool = False
    depth: float = 0.15
    bevel: float = 0.02
    layout: str = ""
    enter: str = ""
    hold: str = ""
    exit: str = ""
    distance: str = ""
    persist: str = ""                # "" | "next" | "section"
    cuts: int = 0                    # shown in this many parts in turn (0 / 1 = whole, design §5.5.1)
    cut_specs: list = None           # locked line: layout / motions / distance of each cut
    particle: str = ""               # particle preset added while the line is on stage
    background: str = ""             # background preset from this line on
    transition: str = ""             # transition into that background
    guide: str = ""                  # "" (auto) | "on" | "off"
    gimmick: str = ""                # "" (auto) | "none" | "emblem" | a tag
    gimmick_show: str = ""           # way of appearing (core/parts/gimmicks.py)
    gimmick_word: str = ""           # the emblem's word
    seed_offset: int = 0             # per-line re-roll count
    look_seed: int = 0               # pasted line: the copied line's look (motions, layout details); 0 = its own


FX_DEFAULTS = {"motion": 0.7, "particles": 0.6, "decor": 0.5, "density": 0.5, "world_switch": 0.6, "koma": 0,
               "guide": 0.7, "flash": True, "gimmick": 0.6, "spectrum": "chorus"}


@dataclass
class SectionInput:
    start: float
    end: float
    kind: str = "verse"
    particle: str = ""               # the section's first particles ("" = planner, overrides below likewise)
    background: str = ""
    transition: str = ""
    particle2: str = "none"         # the second particles ("none" = nothing, "" = planner)


@dataclass
class Settings:
    """Everything おまかせ decides besides the per-line choices (spec §6.1)."""
    mood: str = ""
    style: str = ""
    fx: dict = field(default_factory=dict)
    disabled: dict = field(default_factory=dict)     # kind -> keys turned off in the effects panel
    stage_offsets: dict = field(default_factory=dict)  # stage -> re-roll count ("change only this")
    accent: str = ""                 # '#RRGGBB' replacing the style accent
    energy: object = None            # loudness envelope (0..1) at energy_rate, or None
    energy_rate: float = 50.0
    beats: object = None             # beat times (seconds) or None
    panorama: bool = False           # a panorama image is set (the image background may be used)
    spectrum: object = None          # band levels (frames, bands) 0..1 at energy_rate, or None
    user_assets: dict = field(default_factory=dict)  # tag -> {"file", "name"} (the user's asset library)
    user_words: dict = field(default_factory=dict)   # tag -> extra words (preferences)
    title: str = ""                  # the song title ([ti:] in the lyrics): a title card in the intro
    artist: str = ""                 # [ar:]: small under the title

    def fx_value(self, key):
        return self.fx.get(key, FX_DEFAULTS[key])


@dataclass
class LinePlan:
    index: int
    text: str
    start: float
    end: float                        # when the line has left (exit finished)
    section_index: int
    char_times: list
    emph_mask: list                   # per character: inside an *emphasis*
    is_3d: bool
    depth: float
    bevel: float
    font_role: str
    layout: str
    layout_params: dict
    enter: str
    hold: str
    exit: str
    enter_dur: float
    exit_dur: float
    distance: str
    persist: bool
    anchor: tuple                     # (azimuth, elevation) in radians chosen by the planner
    emphasis: bool
    seed: int
    glide: tuple = None               # (start, end): a kept line appears in front and moves to its slot
    colors: dict = None               # {"fg": linear rgb, "accent": linear rgb}; None = white / gold
    guide: str = ""
    particle: str = ""
    impact: bool = False
    cut: int = 0                      # number of this cut within the line
    cuts: list = None                 # a split line: a LinePlan per cut; these are baked instead of the line
    size: float = 1.0                 # text size factor (the artist under the title card)


@dataclass
class SectionPlan:
    index: int
    kind: str
    start: float
    end: float
    background: dict                  # resolved background spec at the section start
    particles: list                   # preset keys
    palette: dict                     # role -> '#RRGGBB' for the section's backdrop
    background_from: str = "style"    # style (its scheme colours) | section (set on the section) | line (see line)
    background_line: int = -1
    slots: tuple = ("", "none")       # the section's two particle settings ("" = planner, "none" = nothing)
    picks: tuple = (None, None)       # what each slot gives (None: nothing)
    particle_from: list = field(default_factory=list)   # per key of particles: "set" | "auto"


@dataclass
class Plan:
    seed: int
    duration: float
    bpm: float
    lines: list
    sections: list                    # [(start, end)]
    version: int = 1
    mood: str = ""
    style: str = ""
    fx: dict = field(default_factory=dict)
    section_plans: list = field(default_factory=list)
    world: list = field(default_factory=list)       # background changes: {t, dur, spec, transition}
    emitters: list = field(default_factory=list)    # particle emitter specs (core/parts/particles.py)
    events: list = field(default_factory=list)      # {type: flash|pulse, t, amp, dur, color}
    gimmicks: list = field(default_factory=list)    # core/parts/gimmicks.py
    spectrum: dict = None                           # {levels, rate, windows [(start, end, rgb)]}
    title: object = None                            # LinePlan of the title card (index -1), or None
    artist: object = None                           # LinePlan of the artist under it (index -2), or None


@dataclass
class Node:
    id: str
    name: str
    parent: str                       # node id or ""
    category: str                     # text | particles | background | gimmicks
    kind: str                         # group | glyph | ...
    mesh: str = ""                    # key into BakedScene.meshes
    material: str = ""
    loc: tuple = (0.0, 0.0, 0.0)
    rot: tuple = (1.0, 0.0, 0.0, 0.0)
    scale: tuple = (1.0, 1.0, 1.0)
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    default_active: bool = True


@dataclass
class MeshSource:
    key: str
    kind: str                         # glyph2d | glyph3d
    args: dict


@dataclass
class Track:
    node: str
    prop: str                         # active | location | rotation | scale | color
    interp: str                       # linear | constant
    times: np.ndarray                 # (N,) seconds
    values: np.ndarray                # (N, C)


@dataclass
class BakedScene:
    duration: float
    nodes: list
    meshes: dict
    tracks: list
    sections: list
    emitters: list = field(default_factory=list)    # {node, spec}
    guides: list = field(default_factory=list)      # {line, t_on, t_hit, from, to, kinds}
