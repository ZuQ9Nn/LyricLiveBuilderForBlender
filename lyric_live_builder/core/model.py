"""Data passed between planner, parts, bake, preview and export (no bpy)."""
from dataclasses import dataclass, field

import numpy as np

# distance layers (metres from the eye to the line, design §7.1)
DISTANCE = {"near": 1.2, "mid": 3.5, "far": 8.0}
EYE_HEIGHT = 1.5
MIN_EYE_DISTANCE = 0.6            # nothing comes closer to the eye (design §7.2)
ANGLE_BODY = 3.5                  # visual angle of a character, degrees (2.5 looked like subtitles)
ANGLE_EMPH = 5.5
MAX_LINE_ANGLE = 70.0             # widest horizontal extent of a flat line, degrees


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


@dataclass
class Plan:
    seed: int
    duration: float
    bpm: float
    lines: list
    sections: list                    # [(start, end)]
    version: int = 1


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
