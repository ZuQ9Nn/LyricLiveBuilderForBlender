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
    ("custom", "Custom", ""),
]
SOURCE_ITEMS = [
    ("auto", "Estimated", "Estimated from the number of characters"),
    ("tap", "Tap", "Recorded with Tap Sync"),
    ("lrc", "LRC", "LRC timestamp in the lyrics"),
    ("manual", "Manual", "Entered by hand"),
]
FONT_ROLES = ("display", "serif", "body", "mono")


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
    label: StringProperty(name="Label", description="Heading text from the lyrics")
    start: FloatProperty(name="Start", unit="TIME_ABSOLUTE")
    end: FloatProperty(name="End", unit="TIME_ABSOLUTE")


class LLBLine(bpy.types.PropertyGroup):
    index: IntProperty(name="Line")
    text: StringProperty(name="Text")
    start: FloatProperty(name="Start", unit="TIME_ABSOLUTE", description="Resolved start time")
    end: FloatProperty(name="End", unit="TIME_ABSOLUTE")
    source: EnumProperty(name="Source", items=SOURCE_ITEMS, default="auto")
    section_index: IntProperty(name="Section")
    char_times: StringProperty(name="Character Times", description="JSON list of seconds")
    tap_time: FloatProperty(name="Tap", default=-1.0, unit="TIME_ABSOLUTE",
                            description="Latency-corrected tap time (negative = not tapped)")
    use_manual: BoolProperty(name="Manual Time", update=_recompute,
                             description="Use the time entered here instead of the tap / estimate")
    manual_start: FloatProperty(name="Manual Start", min=0.0, unit="TIME_ABSOLUTE", update=_recompute)


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
