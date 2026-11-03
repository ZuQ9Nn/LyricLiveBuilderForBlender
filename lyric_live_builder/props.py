"""Scene data of a LyricLive project (saved in the .blend as Scene.llb)."""
import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, IntVectorProperty, PointerProperty, StringProperty)

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


def _items(table, order, auto="Planner's Choice"):
    items = [(AUTO, auto, "Chosen by the planner")] if auto else []
    return items + [(k, table[k]["name"], "") for k in order]


def _world_items():
    from .core import moods, styles, themes
    from .core.parts import backgrounds as bgs
    from .core.parts import particles as pts
    return (_items(themes.THEMES, themes.ORDER), _items(bgs.PRESETS, bgs.ORDER),
            _items(bgs.TRANSITIONS, bgs.TRANSITION_ORDER), _items(pts.PRESETS, list(pts.PRESETS)),
            _items(moods.MOODS, moods.ORDER, None), _items(styles.STYLES, styles.ORDER, None))


# built once: enum items must outlive the property (Blender keeps pointers to the strings)
LAYOUT_ITEMS = _part_items("layout")
ENTER_ITEMS = _part_items("enter")
HOLD_ITEMS = _part_items("hold")
EXIT_ITEMS = _part_items("exit")
THEME_ITEMS, BACKGROUND_ITEMS, TRANSITION_ITEMS, PARTICLE_ITEMS, MOOD_ITEMS, STYLE_ITEMS = _world_items()
GUIDE_ITEMS = [(AUTO, "Automatic Guide", "Only when the line appears away from where the audience is looking"),
               ("on", "Always Guide", ""), ("off", "No Guide", "")]
KOMA_ITEMS = [("0", "Every Frame", "Every frame (recommended for VR)"), ("12", "12 Steps per Second", ""),
              ("8", "8 Steps per Second", "")]
PART_KINDS = [("layout", "Layouts", ""), ("enter", "Entrances", ""), ("hold", "Hold Motions", ""), ("exit", "Exits", ""),
              ("theme", "Themes", ""), ("particle", "Particle Presets", ""), ("background", "Backgrounds", ""),
              ("transition", "Transitions", "")]
REROLL_ITEMS = [("style", "Style", "Text and particle colours"), ("colors", "Accent Color", ""),
                ("mood", "Mood", "Mood, effect strengths and the parts in use"),
                ("text", "Text Composition", "Layouts and motions of the lines"),
                ("particles", "Particles", ""), ("background", "Background", "Backgrounds and transitions")]


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


class LLBFx(bpy.types.PropertyGroup):
    motion: FloatProperty(name="Motion Strength", default=0.7, min=0.0, max=1.0, subtype="FACTOR")
    particles: FloatProperty(name="Amount of Particles", default=0.6, min=0.0, max=1.0, subtype="FACTOR")
    decor: FloatProperty(name="Decoration", default=0.5, min=0.0, max=1.0, subtype="FACTOR",
                         description="Sparkle bursts on emphasized lines")
    density: FloatProperty(name="Density", default=0.5, min=0.0, max=1.0, subtype="FACTOR",
                           description="How often lines stay on stage until the section ends")
    world_switch: FloatProperty(name="Background Changes", default=0.6, min=0.0, max=1.0, subtype="FACTOR",
                                description="How often the background changes at a section boundary")
    koma: EnumProperty(name="Frame Stepping", items=KOMA_ITEMS, default="0")
    guide: FloatProperty(name="Gaze Guide", default=0.7, min=0.0, max=1.0, subtype="FACTOR",
                         description="Light that leads the eye to lines appearing out of view (0 = off)")
    flash: BoolProperty(name="Flashes", default=True, description="Brief white flashes on strong lines and choruses")


class LLBPartToggle(bpy.types.PropertyGroup):
    kind: StringProperty()
    key: StringProperty()
    label: StringProperty()
    enabled: BoolProperty(name="Use Part", default=True)


class LLBHistoryItem(bpy.types.PropertyGroup):
    data: StringProperty(description="JSON of one proposal")


class LLBExportSettings(bpy.types.PropertyGroup):
    project_path: StringProperty(name="Unity Project", subtype="DIR_PATH",
                                 description="The VRChat world project (the folder that holds Assets)")
    unity_path: StringProperty(name="Unity Editor Path", subtype="FILE_PATH",
                               description="Unity.exe (empty = the preferences value, or found automatically)")
    folder_name: StringProperty(name="Song Folder", description="Assets/LyricLive/Songs/<this> (empty = the song file name)")
    material_mode: EnumProperty(name="Material Set", items=[
        ("VRCHAT", "VRChat Worlds", "The add-on's own shaders (tested on PC, Quest and iOS)"),
        ("STANDARD", "Standard Unity", "The same shaders; for non-VRChat projects")], default="VRCHAT")
    use_mobile: BoolProperty(name="Mobile Optimization",
                             description="Lighter letters, still lines merged, one text material, fewer particles (Quest / phones)")
    particle_ratio: FloatProperty(name="Particle Share", default=0.5, min=0.05, max=1.0, subtype="FACTOR",
                                  description="Share of the particle counts kept by Mobile Optimization")
    use_tmp: BoolProperty(name="TextMesh Pro",
                          description="Flat lines become TextMesh Pro letters (a static atlas of the lyric's characters; "
                                      "the font file is not part of the build). 3D lines stay meshes")
    use_udon_sync: BoolProperty(name="Udon Sync",
                                description="A start button that plays the show in sync for everyone, late joiners too, "
                                            "and gaze guides that follow each viewer's own view (needs UdonSharp)")
    limit_tris: IntProperty(name="Triangles on Stage", default=100000, min=1000)
    limit_particles: IntProperty(name="Particles Alive", default=3000, min=100)
    limit_materials: IntProperty(name="Material Count", default=16, min=1)
    budget: StringProperty(description="JSON of the last budget check")
    status: StringProperty(name="Export Status")
    log_path: StringProperty(subtype="FILE_PATH")


class LLBSection(bpy.types.PropertyGroup):
    kind: EnumProperty(name="Kind", items=SECTION_KIND_ITEMS, default="verse", update=_kind_set_by_user)
    user_kind: BoolProperty(description="Kind was changed by hand; kept when the lyrics are read again")
    label: StringProperty(name="Heading Text", description="Heading text from the lyrics")
    start: FloatProperty(name="Start", unit="TIME_ABSOLUTE")
    end: FloatProperty(name="End", unit="TIME_ABSOLUTE")
    theme: EnumProperty(name="Theme", items=THEME_ITEMS)
    background: EnumProperty(name="Background", items=BACKGROUND_ITEMS)
    transition: EnumProperty(name="Transition", items=TRANSITION_ITEMS)
    locked: BoolProperty(name="Lock State", description="Keep the theme, background and transition")
    lock_frozen: StringProperty(description="Fields the lock filled in (set back to automatic on unlock)")


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
    guide: EnumProperty(name="Gaze Guide", items=GUIDE_ITEMS)
    particle: EnumProperty(name="Line Particles", items=PARTICLE_ITEMS,
                           description="Particles added while this line is on stage")
    background: EnumProperty(name="Background from Here", items=BACKGROUND_ITEMS)
    transition: EnumProperty(name="Transition", items=TRANSITION_ITEMS)
    locked: BoolProperty(name="Lock State", description="Make It for Me and re-rolls keep this line as it is")
    lock_frozen: StringProperty(description="Fields the lock filled in (set back to automatic on unlock)")
    seed_offset: IntProperty(name="Re-roll Count", min=0)


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
    # Make It for Me (spec §6.1)
    mood: EnumProperty(name="Mood", items=MOOD_ITEMS, default="chaos")
    style: EnumProperty(name="Style", items=STYLE_ITEMS, default="noir")
    fx: PointerProperty(type=LLBFx)
    use_accent: BoolProperty(name="Own Accent", description="Replace the style's accent colour")
    accent: FloatVectorProperty(name="Accent", subtype="COLOR_GAMMA", size=3, min=0.0, max=1.0, default=(1.0, 0.65, 0.05))
    stage_offsets: IntVectorProperty(size=8, description="Re-roll count of each planning stage")
    parts: CollectionProperty(type=LLBPartToggle)
    parts_kind: EnumProperty(name="Kind", items=PART_KINDS)
    parts_active: IntProperty()
    history: CollectionProperty(type=LLBHistoryItem)
    history_index: IntProperty(default=-1)
    reroll_target: EnumProperty(name="Change Only", items=REROLL_ITEMS, default="particles")
    export: PointerProperty(type=LLBExportSettings)
    panorama_path: StringProperty(name="Panorama Image", subtype="FILE_PATH",
                                  description="360° equirectangular image for the Panorama Image background")

    def font(self, role):
        return getattr(self, "font_" + role)


CLASSES = (LLBFontRole, LLBFx, LLBPartToggle, LLBHistoryItem, LLBExportSettings, LLBSection, LLBLine, LLBProject)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.llb = PointerProperty(type=LLBProject)


def unregister():
    del bpy.types.Scene.llb
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
