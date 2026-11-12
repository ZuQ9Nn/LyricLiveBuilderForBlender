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


CUT_ITEMS = [(AUTO, "Planner's Choice", "")] + [(str(n), str(n), "") for n in range(1, 7)]


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
PARTICLE_ITEMS.insert(1, ("lyrics", "From the Lyrics", "A word in the line picks the particles (none: Planner's Choice)"))


def _gimmick_items():
    from .core import gimmick_shapes as shapes
    from .core.parts import gimmicks
    objects = [(AUTO, "From the Lyrics", "A keyword in the line picks the object"), ("none", "No Stage Object", ""),
               ("emblem", "Keyword Emblem", "The word in 3D letters on a disc")]
    objects += [(k, v[0], "") for k, v in shapes.SHAPES.items()]
    return objects, _items(gimmicks.SHOWS, gimmicks.SHOW_ORDER)


GIMMICK_ITEMS, SHOW_ITEMS = _gimmick_items()
PART_GROUP_ITEMS = [("all", "Every Part Group", ""), ("basic", "Basic", ""), ("extra", "Extra Parts", ""),
                    ("kinetic", "Kinetic", "Word by word; Make It for Me uses them with pop, glitch and graphic moods"),
                    ("typo", "Typography", "Make It for Me uses them with editorial and graphic moods"),
                    ("horror", "Horror", "Make It for Me uses them only with the horror mood")]
TAP_SPEED_ITEMS = [("1", "Normal Speed", ""), ("0.75", "0.75× Speed", ""), ("0.5", "0.5× Speed", "")]
SPECTRUM_ITEMS = [("off", "No Spectrum Bars", ""), ("chorus", "Bars in Choruses", ""), ("all", "Bars All Through", "")]
GUIDE_ITEMS = [(AUTO, "Automatic Guide", "Only when the line appears away from where the audience is looking"),
               ("on", "Always Guide", ""), ("off", "No Guide", "")]
KOMA_ITEMS = [("0", "Every Frame", "Every frame (recommended for VR)"), ("12", "12 Steps per Second", ""),
              ("8", "8 Steps per Second", "")]
PART_KINDS = [("layout", "Layouts", ""), ("enter", "Entrances", ""), ("hold", "Hold Motions", ""), ("exit", "Exits", ""),
              ("theme", "Themes", ""), ("particle", "Particle Presets", ""), ("background", "Backgrounds", ""),
              ("transition", "Transitions", ""), ("gimmick", "Stage Objects", ""), ("show", "Ways of Appearing", "")]
REROLL_ITEMS = [("style", "Style", "Text and particle colours"), ("colors", "Accent Color", ""),
                ("mood", "Mood", "Mood, effect strengths and the parts in use"),
                ("text", "Text Composition", "Layouts and motions of the lines"),
                ("particles", "Particles", ""), ("background", "Background", "Backgrounds and transitions"),
                ("gimmicks", "Stage Objects", "Which lines get an object, how and where it appears")]


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
    _trial(self, context)


def _trial(self, context):
    """A line / section setting changed: the trial window's After follows (spec §6.3)."""
    from .ui import trial
    trial.changed()


def _trial_mute(self, context):
    from .ui import trial
    trial.set_mute(context.scene)


def _pick_line(self, context):
    from .ui import details, trial
    self.trial_focus = "line"
    trial.changed(both=True)
    details.picked()


def _pick_section(self, context):
    from .ui import trial
    self.trial_focus = "section"
    trial.changed(both=True)


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
    gimmick: FloatProperty(name="Stage Object Amount", default=0.6, min=0.0, max=1.0, subtype="FACTOR",
                           description="How often a keyword in the lyrics brings an object on stage (0 = only lines set by hand)")
    spectrum: EnumProperty(name="Spectrum Bars", items=SPECTRUM_ITEMS, default="chorus",
                           description="24 bars around the audience, moving with the song (needs a song)")


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
    theme: EnumProperty(name="Theme", items=THEME_ITEMS, update=_trial)
    background: EnumProperty(name="Background", items=BACKGROUND_ITEMS, update=_trial)
    transition: EnumProperty(name="Transition", items=TRANSITION_ITEMS, update=_trial)
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
    is_3d: BoolProperty(name="3D Text", description="Extruded letters with visible sides", update=_trial)
    depth: FloatProperty(name="Text Thickness", default=0.15, min=0.02, max=1.0, subtype="FACTOR",
                         description="Thickness of 3D letters relative to their size", update=_trial)
    bevel: EnumProperty(name="Bevel", items=BEVEL_ITEMS, default="0.015", update=_trial)
    layout: EnumProperty(name="Layout", items=LAYOUT_ITEMS, update=_trial)
    enter: EnumProperty(name="Entrance", items=ENTER_ITEMS, update=_trial)
    hold: EnumProperty(name="Hold", items=HOLD_ITEMS, update=_trial)
    exit: EnumProperty(name="Exit Motion", items=EXIT_ITEMS, update=_trial)
    distance_layer: EnumProperty(name="Distance Layer", items=DISTANCE_ITEMS, update=_trial)
    cuts: EnumProperty(name="Line Cuts", items=CUT_ITEMS,
                       description="Show this line in parts one after the other, as they are sung. Planner's Choice keeps it whole", update=_trial)
    persist: EnumProperty(name="Leaves", items=PERSIST_ITEMS, update=_trial)
    guide: EnumProperty(name="Gaze Guide", items=GUIDE_ITEMS, update=_trial)
    gimmick: EnumProperty(name="Stage Object", items=GIMMICK_ITEMS, update=_trial)
    gimmick_show: EnumProperty(name="How It Appears", items=SHOW_ITEMS, update=_trial)
    gimmick_word: StringProperty(name="Emblem Word", description="The emblem's text (empty = the keyword or the longest chunk)", update=_trial)
    particle: EnumProperty(name="Line Particles", items=PARTICLE_ITEMS,
                           description="Particles added while this line is on stage", update=_trial)
    background: EnumProperty(name="Background from Here", items=BACKGROUND_ITEMS, update=_trial)
    transition: EnumProperty(name="Transition", items=TRANSITION_ITEMS, update=_trial)
    locked: BoolProperty(name="Lock State", description="Make It for Me and re-rolls keep this line as it is")
    lock_frozen: StringProperty(description="Fields the lock filled in (set back to automatic on unlock)")
    lock_cuts: StringProperty(description="JSON of what each cut had when the line was locked", update=_trial)
    seed_offset: IntProperty(name="Re-roll Count", min=0, update=_trial)
    # pasted effects (spec §6.2): the copied line's look seed (a 32-bit number, kept as text) and cut parts
    look_seed: StringProperty(description="Seed of the look copied from another line (empty = this line's own)",
                              update=_trial)
    paste_cuts: StringProperty(description="JSON of each cut's parts and seed copied from another line", update=_trial)


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
    tap_countdown: BoolProperty(name="Countdown", description="Count 3, 2, 1 before the song starts")
    tap_speed: EnumProperty(name="Tap Speed", items=TAP_SPEED_ITEMS, default="1",
                            description="Slow the song down while tapping, pitch kept. It can be changed while tapping. "
                                        "The real times are stored")
    seed: IntProperty(name="Seed", default=1, min=0, description="Same seed, same result")
    latency_fps: FloatProperty(description="Scene frame rate when the latency was measured (0 = entered by hand)")
    sections_from_headings: BoolProperty(default=False)
    sections: CollectionProperty(type=LLBSection)
    lines: CollectionProperty(type=LLBLine)
    section_active: IntProperty(update=_pick_section)
    line_active: IntProperty(update=_pick_line)
    line_clipboard: StringProperty(description="JSON of the line effects copied with Copy Effects")
    part_group: EnumProperty(name="Part Group", items=PART_GROUP_ITEMS,
                             description="Show only the layouts and motions of one group in the line details")
    ui_page: EnumProperty(name="LyricLive Page", items=[("setup", "Setup", "Lyrics, fonts, song and sync"),
                                              ("compose", "Compose", "Make It for Me, sections and lines"),
                                              ("output", "Effects & Output", "Stage effects, preview and Unity export")])
    trial_focus: EnumProperty(items=[("line", "Lyric Line", ""), ("section", "Section", "")],
                              description="What the trial window shows: the line or the section picked last")
    trial_mute: BoolProperty(name="Mute the Song", update=_trial_mute,
                             description="Silence the song while trying things out (back to as it was on close)")
    trial_snapshot: StringProperty(description="JSON of the settings at the last Generate (the trial's Before)")
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
