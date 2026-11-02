"""Scene data of a LyricLive project (saved in the .blend as Scene.llb)."""
import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)

SECTION_KIND_ITEMS = [
    ("intro", "Intro", ""),
    ("verse", "Verse", ""),
    ("prechorus", "Pre-Chorus", ""),
    ("chorus", "Chorus", ""),
    ("interlude", "Interlude", ""),
    ("bridge", "Bridge", ""),
    ("outro", "Outro", ""),
    ("custom", "Other Section", ""),
]
SOURCE_ITEMS = [
    ("auto", "Estimated", "Estimated from the number of characters"),
    ("tap", "Tap", "Recorded with Tap Sync"),
    ("lrc", "LRC", "LRC timestamp in the lyrics"),
    ("manual", "By Hand", "Entered by hand"),
]
FONT_ROLES = ("display", "serif", "body", "mono")
AUTO = "AUTO"
DISTANCE_ITEMS = [(AUTO, "Planner's Choice", ""), ("near", "Near Layer", "1.2 m"), ("mid", "Middle Layer", "3.5 m"), ("far", "Far Layer", "8 m")]
PERSIST_ITEMS = [(AUTO, "Planner's Choice", ""), ("next", "Until the Next Line", ""),
                 ("section", "Until the Section Ends", "Stays on stage and leaves with the rest of the section")]
BEVEL_ITEMS = [("0.0", "No Bevel", ""), ("0.015", "Small Bevel", ""), ("0.04", "Large Bevel", "")]


def _part_items(kind):
    from .core import registry
    items = [(AUTO, "Planner's Choice", "Chosen by the planner")]
    for p in registry.parts(kind):
        items.append((p.key, p.name, "3D lines only" if getattr(p, "only_3d", False) else ""))
    return items


# built once: enum items must outlive the property (Blender keeps pointers to the strings)
LAYOUT_ITEMS = _part_items("layout")
ENTER_ITEMS = _part_items("enter")
HOLD_ITEMS = _part_items("hold")
EXIT_ITEMS = _part_items("exit")


def _recompute(self, context):
    from .ui import project
    project.recompute(context.scene)


def _latency_set(self, context):
    # a measured or hand-entered value belongs to this file from now on;
    # the measuring operator sets latency_fps after this
    self.latency_measured = True
    self.latency_fps = 0.0


class LLBFontRole(bpy.types.PropertyGroup):
    filepath: StringProperty(name="Font File", subtype="FILE_PATH",
                             description="TrueType / OpenType font (.ttf, .otf, .ttc: first face only)")


def _kind_set_by_user(self, context):
    from .ui import project
    if not project.is_busy():
        self.user_kind = True


class LLBSection(bpy.types.PropertyGroup):
    kind: EnumProperty(name="Kind", items=SECTION_KIND_ITEMS, default="verse", update=_kind_set_by_user)
    user_kind: BoolProperty(description="Kind was changed by hand; kept when the lyrics are read again")
    label: StringProperty(name="Heading Text", description="Heading text from the lyrics")
    start: FloatProperty(name="Start", unit="TIME_ABSOLUTE")
    end: FloatProperty(name="End", unit="TIME_ABSOLUTE")


class LLBLine(bpy.types.PropertyGroup):
    index: IntProperty(name="Lyric Line Number")
    text: StringProperty(name="Line Text")
    start: FloatProperty(name="Start", unit="TIME_ABSOLUTE", description="Resolved start time")
    end: FloatProperty(name="End", unit="TIME_ABSOLUTE")
    source: EnumProperty(name="Time Source", items=SOURCE_ITEMS, default="auto")
    section_index: IntProperty(name="Section")
    char_times: StringProperty(name="Character Times", description="JSON list of seconds")
    tap_time: FloatProperty(name="Tap", default=-1.0, unit="TIME_ABSOLUTE",
                            description="Latency-corrected tap time (negative = not tapped)")
    use_manual: BoolProperty(name="Manual Time", update=_recompute,
                             description="Use the time entered here instead of the tap / estimate")
    manual_start: FloatProperty(name="Manual Start", min=0.0, unit="TIME_ABSOLUTE", update=_recompute)
    # text details (spec §6.2); AUTO = left to the planner
    is_3d: BoolProperty(name="3D Text", description="Extruded letters with visible sides")
    depth: FloatProperty(name="Text Thickness", default=0.15, min=0.02, max=1.0, subtype="FACTOR",
                         description="Thickness of 3D letters relative to their size")
    bevel: EnumProperty(name="Bevel", items=BEVEL_ITEMS, default="0.015")
    layout: EnumProperty(name="Layout", items=LAYOUT_ITEMS)
    enter: EnumProperty(name="Entrance", items=ENTER_ITEMS)
    hold: EnumProperty(name="Hold", items=HOLD_ITEMS)
    exit: EnumProperty(name="Exit Motion", items=EXIT_ITEMS)
    distance_layer: EnumProperty(name="Distance Layer", items=DISTANCE_ITEMS)
    persist: EnumProperty(name="Leaves", items=PERSIST_ITEMS)


class LLBProject(bpy.types.PropertyGroup):
    lyrics_text: PointerProperty(name="Lyrics", type=bpy.types.Text)
    font_display: PointerProperty(type=LLBFontRole)
    font_serif: PointerProperty(type=LLBFontRole)
    font_body: PointerProperty(type=LLBFontRole)
    font_mono: PointerProperty(type=LLBFontRole)
    audio_path: StringProperty(name="Song", subtype="FILE_PATH")
    audio_duration: FloatProperty(name="Song Length", unit="TIME_ABSOLUTE")
    duration: FloatProperty(name="Length", unit="TIME_ABSOLUTE", description="Song or lyrics, whichever is longer")
    bpm: FloatProperty(name="BPM", min=0.0, max=400.0, precision=1, update=_recompute,
                       description="Tempo. Estimated times snap to its beats (0 = no snapping)")
    beat_offset: FloatProperty(name="First Beat", min=0.0, unit="TIME_ABSOLUTE",
                               description="Time of the first beat")
    tap_latency_ms: FloatProperty(name="Tap Latency (ms)", soft_min=-200.0, soft_max=300.0, update=_latency_set,
                                  description="Subtracted from tap times. Measure it, or enter it by hand")
    latency_measured: BoolProperty(default=False)
    seed: IntProperty(name="Seed", default=1, min=0, description="Same seed, same result")
    latency_fps: FloatProperty(description="Scene frame rate when the latency was measured (0 = entered by hand)")
    sections_from_headings: BoolProperty(default=False)
    sections: CollectionProperty(type=LLBSection)
    lines: CollectionProperty(type=LLBLine)
    section_active: IntProperty()
    line_active: IntProperty()

    def font(self, role):
        return getattr(self, "font_" + role)


CLASSES = (LLBFontRole, LLBSection, LLBLine, LLBProject)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.llb = PointerProperty(type=LLBProject)


def unregister():
    del bpy.types.Scene.llb
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
