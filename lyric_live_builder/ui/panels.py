"""Sidebar panels (3D Viewport > N > LyricLive), in work order."""
import json
import os

import bpy
from bpy.app.translations import pgettext_iface as iface_

from ..core import registry, themes
from ..core.parts import backgrounds as bgs
from ..core.parts import particles as pts
from ..props import FONT_ROLES, SECTION_KIND_ITEMS
from . import details, operators_input, planning, project, tap_sync, trial
from .lists import fmt_time

ROLE_LABELS = {"display": "Heading Font", "serif": "Serif Font", "body": "Body Font", "mono": "Mono Font"}
KIND_LABELS = {k: name for k, name, _ in SECTION_KIND_ITEMS}
NOTATION = (
    ("A/B", "Chunk break"),
    ("*word*", "Emphasis"),
    ("line!", "Strong accent"),
    ("line|note", "Small Annotation"),
    ("[01:23.45]line", "LRC time"),
    ("[A] [Chorus] [Outro]", "Section heading"),
    ("# ...", "Comment"),
    ("[ti:Title] [ar:Artist]", "Meta data"),
)


def labels(layout, msg, icon="NONE"):
    """A translated message on several rows (split at '\n'), so the narrow sidebar does not cut it."""
    for i, line in enumerate(iface_(msg).split("\n")):
        layout.label(text=line, icon=icon if i == 0 else "BLANK1", translate=False)


def prop_above(layout, data, name):
    """A property with its name on its own row (long names would be cut in the narrow sidebar)."""
    col = layout.column(align=True)
    col.label(text=data.bl_rna.properties[name].name)
    col.prop(data, name, text="")
    return col


class _Panel:
    """One of the pages switched at the top of the LyricLive tab (design §13)."""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LyricLive"
    page = "setup"

    @classmethod
    def poll(cls, context):
        return context.scene.llb.ui_page == cls.page and not details.is_details_area(getattr(context, "area", None))


class LLB_PT_pages(bpy.types.Panel):
    """Setup | Compose | Effects & Output: shorter than every panel in one column."""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LyricLive"
    bl_label = "LyricLive Pages"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return not details.is_details_area(getattr(context, "area", None))
    bl_order = 0

    def draw(self, context):
        row = self.layout.row(align=True)
        row.scale_y = 1.3
        row.prop(context.scene.llb, "ui_page", expand=True)


class LLB_PT_lyrics(_Panel, bpy.types.Panel):
    bl_idname = "LLB_PT_lyrics"
    bl_label = "Lyrics"
    bl_order = 1

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        col.operator("llb.edit_lyrics", icon="GREASEPENCIL")
        if operators_input.watching():
            labels(col, "Saving in the editor\nupdates the lyrics here", "INFO")
        col.operator("llb.paste_lyrics", icon="PASTEDOWN")
        col.operator("llb.load_lyrics", icon="FILE_TEXT")
        col.separator()
        col.operator("llb.open_lyrics", icon="TEXT")
        col.prop(proj, "lyrics_text", text="")
        col.operator("llb.refresh", icon="FILE_REFRESH")


class LLB_PT_lyrics_notation(_Panel, bpy.types.Panel):
    bl_label = "Notation"
    bl_parent_id = "LLB_PT_lyrics"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        for sample, meaning in NOTATION:
            row = col.row()
            row.label(text=sample)
            row.label(text=meaning)


class LLB_PT_fonts(_Panel, bpy.types.Panel):
    bl_label = "Fonts"
    bl_order = 2

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        for role in FONT_ROLES:
            col.prop(proj.font(role), "filepath", text=ROLE_LABELS[role])
            info, err = project.font_status(proj, role)
            if err:
                col.label(text=err, icon="ERROR")
            elif info:
                miss = project.missing_chars(proj, role)
                if miss:
                    box = col.box()
                    box.label(text=iface_("{} missing characters").format(len(miss)), icon="ERROR", translate=False)
                    for k in range(0, min(len(miss), 48), 16):
                        box.label(text="".join(miss[k:k + 16]) + (" …" if k + 16 >= 48 and len(miss) > 48 else ""),
                                  translate=False)
        if not project.has_any_font(proj):
            labels(col, "Set at least\nthe Body font", "INFO")
        elif not proj.font_body.filepath:
            labels(col, "Roles without a file\nuse the Body font", "INFO")
        labels(col, "Glyphs are exported as meshes.\nCheck the font license", "QUESTION")


class LLB_PT_song(_Panel, bpy.types.Panel):
    bl_label = "Song"
    bl_order = 3

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        col.operator("llb.load_audio", icon="SOUND")
        if proj.audio_path:
            path = bpy.path.abspath(proj.audio_path)
            col.label(text=os.path.basename(path), icon="FILE_SOUND", translate=False)
            if not os.path.isfile(path):
                col.label(text="File not found", icon="ERROR")
            col.label(text=iface_("Length {}").format(fmt_time(proj.audio_duration)), translate=False)
        row = col.row(align=True)
        row.prop(proj, "bpm")
        row.operator("llb.analyze_audio", text="", icon="FILE_REFRESH")
        col.prop(proj, "beat_offset")


class LLB_PT_sync(_Panel, bpy.types.Panel):
    bl_label = "Sync"
    bl_order = 4

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        if tap_sync.tapping():
            col.operator("llb.tap_stop", icon="CANCEL")
        else:
            col.operator("llb.tap_sync", icon="REC")
        col.prop(proj, "tap_speed")
        col.prop(proj, "tap_countdown")
        tapped = sum(1 for ln in proj.lines if ln.tap_time >= 0)
        col.label(text=iface_("Tapped {} / {} lines").format(tapped, len(proj.lines)), translate=False)
        col.operator("llb.import_markers", icon="MARKER_HLT")
        col.separator()
        row = col.row(align=True)
        row.prop(proj, "tap_latency_ms")
        row.operator("llb.measure_latency", text="", icon="TIME")
        if not proj.latency_measured:
            labels(col, "Not measured in this file.\nThe preferences value is used", "INFO")
        elif proj.latency_fps > 0:
            col.label(text=iface_("Measured at {:g} fps").format(proj.latency_fps), icon="CHECKMARK", translate=False)
        else:
            col.label(text="Entered by hand", icon="CHECKMARK")


class LLB_PT_omakase(_Panel, bpy.types.Panel):
    page = "compose"
    bl_label = "Auto Compose"
    bl_order = 5

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        row = col.row()
        row.scale_y = 1.6
        row.operator("llb.omakase", icon="SHADERFX")
        row = col.row(align=True)
        sub = row.row(align=True)
        sub.enabled = proj.history_index > 0
        sub.operator("llb.history_step", text="Previous Proposal", icon="TRIA_LEFT").step = -1
        row.label(text=f"{proj.history_index + 1} / {len(proj.history)}" if len(proj.history) else "–",
                  translate=False)
        sub = row.row(align=True)
        sub.enabled = proj.history_index < len(proj.history) - 1
        sub.operator("llb.history_step", text="Next Proposal", icon="TRIA_RIGHT").step = 1
        col.separator()
        col.prop(proj, "mood")
        col.prop(proj, "style")
        col.separator()
        row = col.row(align=True)
        row.prop(proj, "reroll_target", text="")
        row.operator("llb.reroll", icon="FILE_REFRESH")


class LLB_PT_trial(_Panel, bpy.types.Panel):
    """The trial buttons, above the sections and lines (no header: always there)."""
    page = "compose"
    bl_label = "Try Out"
    bl_options = {"HIDE_HEADER"}
    bl_order = 6

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        if trial.is_open():
            trial.draw_buttons(col, proj)
            col.operator("llb.trial_refresh", icon="FILE_REFRESH")
            if trial.error:
                labels(col, trial.error, "ERROR")
        else:
            col.operator("llb.trial_open", icon="SPLIT_VERTICAL")
        labels(col, "Changes show in the preview\nafter Generate", "INFO")


class LLB_PT_sections(_Panel, bpy.types.Panel):
    page = "compose"
    bl_label = "Song Sections"
    bl_order = 7

    def draw(self, context):
        draw_sections(self.layout.column(), context.scene.llb)


class LLB_PT_lines(_Panel, bpy.types.Panel):
    page = "compose"
    bl_label = "Lyric Lines"
    bl_order = 8

    def draw(self, context):
        draw_lines(self.layout.column(), context.scene.llb)


def part_field(layout, proj, ln, field, above=False):
    """A layout / motion field; with a group picked, a menu of that group's parts only (design §13)."""
    if proj.part_group == "all":
        (prop_above(layout, ln, field) if above else layout.prop(ln, field))
        return
    prop = ln.bl_rna.properties[field]
    current = iface_(prop.enum_items[getattr(ln, field)].name)
    row = layout.column(align=True) if above else layout.row()
    row.label(text=iface_(prop.name) + ("" if above else ":"), translate=False)
    row.menu(f"LLB_MT_pick_{field}", text=current, translate=False)


class _PickMenu:
    bl_label = "Parts of the Group"
    field = ""

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        op = col.operator("llb.pick_part", text=iface_("Planner's Choice"), translate=False)
        op.field, op.key = self.field, "AUTO"
        for part in registry.parts(self.field):
            if part.group == proj.part_group:
                op = col.operator("llb.pick_part", text=iface_(part.name), translate=False)
                op.field, op.key = self.field, part.key


PICK_MENUS = tuple(type(f"LLB_MT_pick_{f}", (_PickMenu, bpy.types.Menu), {"bl_idname": f"LLB_MT_pick_{f}", "field": f})
                   for f in ("layout", "enter", "hold", "exit"))


def draw_in_use(layout, proj, index):
    """What the section really uses and where it comes from (spec §5: theme and background)."""
    try:
        summary = planning.section_summary(proj)
    except Exception as e:                                # the panel must always draw
        print("[LLB] section summary:", e)
        return
    if not 0 <= index < len(summary):
        return
    s = summary[index]
    theme = iface_(themes.THEMES[s["theme"]]["name"])
    bg = iface_(bgs.PRESETS[s["background"]]["name"]) if s["background"] in bgs.PRESETS else s["background"]
    box = layout.box()
    box.label(text="In Use", icon="VIEWZOOM")
    if s["background_from"] == "section":
        where = iface_("(set here)")
    elif s["background_from"] == "line":
        where = iface_("(from line {})").format(s["line"] + 1)
    else:
        where = iface_("(from theme “{}”)").format(theme)
    col = box.column(align=True)
    col.label(text=iface_("Background: {}").format(bg), translate=False)
    col.label(text=where, icon="BLANK1", translate=False)
    col = box.column(align=True)
    col.label(text=iface_("Particles from theme “{}”:").format(theme), translate=False)
    for key in s["particles"] or ():
        col.label(text=iface_(pts.PRESETS[key]["name"]), icon="BLANK1", translate=False)
    if not s["particles"]:
        col.label(text=iface_("No Particles"), icon="BLANK1", translate=False)


SECTION_PREVIEW = 1                                       # lines of a section always shown


def draw_section_lyrics(layout, proj, index):
    """The lyrics in a section (spec §6.2): the first lines, "… N more", and all of them in a fold."""
    lines = [ln for ln in proj.lines if ln.section_index == index]
    box = layout.box()
    col = box.column(align=True)
    if not lines:
        col.label(text="No Lyrics", icon="INFO")
        return
    for ln in lines[:SECTION_PREVIEW]:
        col.label(text=f"{fmt_time(ln.start)}  {ln.text}", translate=False)
    if len(lines) <= SECTION_PREVIEW:
        return
    col.label(text=iface_("… {} more").format(len(lines) - SECTION_PREVIEW), translate=False)
    header, body = box.panel("LLB_section_lyrics", default_closed=True)
    header.label(text=iface_("All Lyrics of the Section ({} Lines)").format(len(lines)), translate=False)
    if body:
        col = body.column(align=True)
        for ln in lines:
            col.label(text=f"{fmt_time(ln.start)}  {ln.text}", translate=False)


def draw_sections(col, proj):
    """The section list and the picked section's settings."""
    labels(col, "Sections from headings" if proj.sections_from_headings else "Sections estimated\n(no headings)", "INFO")
    col.template_list("LLB_UL_sections", "", proj, "sections", proj, "section_active", rows=4)
    if 0 <= proj.section_active < len(proj.sections):
        sec = proj.sections[proj.section_active]
        # the kind is shown, not set (spec §5.5): the headings or the estimate decide it
        where = iface_("set by hand") if sec.user_kind else \
            iface_("from the headings") if proj.sections_from_headings else iface_("estimated")
        col.label(text=iface_("Kind: {} ({})").format(iface_(KIND_LABELS[sec.kind]), where), translate=False)
        col.label(text=f"{fmt_time(sec.start)} – {fmt_time(sec.end)}", translate=False)
        draw_section_lyrics(col, proj, proj.section_active)
        box = col.box()
        box.enabled = not sec.locked
        box.prop(sec, "theme")
        if sec.background != "AUTO":
            labels(box, "The theme only picks\nthe particles here", "INFO")
        box.prop(sec, "background")
        prop_above(box, sec, "transition")
        draw_in_use(col, proj, proj.section_active)
        col.operator("llb.section_lock", text="Unlock Section" if sec.locked else "Lock Section",
                     icon="UNLOCKED" if sec.locked else "LOCKED", depress=sec.locked)


def draw_lines(col, proj):
    """The line buttons (on the picked line), the list with a details button per line, the picked line's timing."""
    ln = proj.lines[proj.line_active] if 0 <= proj.line_active < len(proj.lines) else None
    row = col.row(align=True)
    row.enabled = ln is not None
    row.operator("llb.tap_sync", text="Tap from This Line", icon="REC").first_line = max(proj.line_active, 0)
    row = col.row(align=True)
    row.enabled = ln is not None
    row.operator("llb.line_lock", text="Unlock Line" if ln and ln.locked else "Lock Line",
                 icon="UNLOCKED" if ln and ln.locked else "LOCKED", depress=bool(ln and ln.locked))
    sub = row.row(align=True)
    sub.enabled = ln is not None and not ln.locked
    sub.operator("llb.line_reroll", icon="FILE_REFRESH")
    row = col.row(align=True)                             # copy / paste a line's effects (spec §6.2)
    row.operator("llb.line_copy", icon="COPYDOWN")
    row.operator("llb.line_paste", icon="PASTEDOWN")
    if proj.line_clipboard:
        src = json.loads(proj.line_clipboard)
        col.label(text=iface_("Copied: line {} “{}”").format(src["line"] + 1, src["text"][:14]), icon="INFO",
                  translate=False)
    col.prop(proj, "all_3d")
    col.template_list("LLB_UL_lines", "", proj, "lines", proj, "line_active", rows=6)
    if ln is not None:
        box = col.box()
        box.label(text=ln.text, translate=False)
        draw_line_timing(box, proj, ln)
        if ln.tap_time >= 0:
            box.label(text=iface_("Tap {}").format(fmt_time(ln.tap_time)), translate=False)
        row = box.row()
        row.prop(ln, "use_manual")
        sub = row.row()
        sub.active = ln.use_manual
        sub.prop(ln, "manual_start", text="")


def draw_line_timing(layout, proj, ln):
    """Start, end (and where they come from) and the section of a line (the Lyric Lines panel and the details)."""
    layout.label(text=iface_("Start {}  End {}  ({})").format(
        fmt_time(ln.start), fmt_time(ln.end), iface_(ln.bl_rna.properties["source"].enum_items[ln.source].name)),
        translate=False)
    if 0 <= ln.section_index < len(proj.sections):
        sec = proj.sections[ln.section_index]
        layout.label(text=iface_("Section {}").format(
            f"{ln.section_index + 1}. {sec.label or iface_(KIND_LABELS[sec.kind])}"), translate=False)


def draw_line_details(col, proj, ln):
    """Layout and below (spec §6.2): drawn in the line details area beside the 3D view."""
    box = col
    box.prop(ln, "is_3d")
    if ln.is_3d:
        row = box.row(align=True)
        row.prop(ln, "depth")
        row.prop(ln, "bevel", text="")
    box.prop(proj, "part_group", text="")
    part_field(box, proj, ln, "layout", above=True)
    if not ln.is_3d and ln.layout != "AUTO" and getattr(registry.get("layout", ln.layout), "only_3d", False):
        labels(box, "This layout is for 3D lines.\nIt is chosen automatically", "ERROR")
    for field in ("enter", "hold", "exit"):
        part_field(box, proj, ln, field)
    box.prop(ln, "distance_layer")
    box.prop(ln, "cuts")
    sub = box.row()
    sub.active = ln.cuts in ("AUTO", "1")           # a split line never stays on stage
    sub.prop(ln, "persist")
    prop_above(box, ln, "guide")
    box.separator()
    prop_above(box, ln, "gimmick")
    sub = box.column()
    sub.active = ln.gimmick != "none"
    sub.prop(ln, "gimmick_show")
    if ln.gimmick == "emblem":
        sub.prop(ln, "gimmick_word")
    box.separator()
    prop_above(box, ln, "particle")
    prop_above(box, ln, "background")
    prop_above(box, ln, "transition").active = ln.background != "AUTO"
    if ln.background == "panorama" and not proj.panorama_path:
        labels(box, "Set the panorama image\nin the Effects panel", "ERROR")
    draw_line_in_use(col, proj, proj.line_active)


def draw_line_in_use(layout, proj, index):
    """The background and particles a line really gets, and where they come from (spec §6.2)."""
    try:
        lines, secs = planning.line_summary(proj), planning.section_summary(proj)
    except Exception as e:                                # the panel must always draw
        print("[LLB] line summary:", e)
        return
    if not 0 <= index < len(lines):
        return
    s = lines[index]
    sec = secs[s["section"]] if 0 <= s["section"] < len(secs) else None
    theme = iface_(themes.THEMES[sec["theme"]]["name"]) if sec else ""
    box = layout.box()
    box.label(text="In Use", icon="VIEWZOOM")
    bg = iface_(bgs.PRESETS[s["background"]]["name"]) if s["background"] in bgs.PRESETS else s["background"]
    where = {"this": iface_("(changed on this line)"), "line": iface_("(from line {})").format(s["line"] + 1),
             "section": iface_("(set in the section)")}.get(s["background_from"],
                                                           iface_("(from theme “{}”)").format(theme))
    col = box.column(align=True)
    col.label(text=iface_("Background: {}").format(bg), translate=False)
    col.label(text=where, icon="BLANK1", translate=False)
    col = box.column(align=True)
    col.label(text=iface_("Particles from theme “{}”:").format(theme), translate=False)
    for key in (sec["particles"] if sec else ()):
        col.label(text=iface_(pts.PRESETS[key]["name"]), icon="BLANK1", translate=False)
    if s["added"]:
        name = iface_(pts.PRESETS[s["added"]]["name"])
        col.label(text=iface_("+ {} (on its strong words)").format(name) if s["added_auto"]
                  else iface_("+ {} (added on this line)").format(name), icon="BLANK1", translate=False)


class LLB_PT_effects(_Panel, bpy.types.Panel):
    page = "output"
    bl_label = "Stage Effects"
    bl_order = 7

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        for k in ("motion", "particles", "decor", "density", "world_switch", "guide", "gimmick"):
            col.prop(proj.fx, k, slider=True)
        col.prop(proj.fx, "spectrum")
        col.prop(proj.fx, "koma")
        col.prop(proj.fx, "flash")
        row = col.row(align=True)
        row.prop(proj, "use_accent")
        sub = row.row()
        sub.active = proj.use_accent
        sub.prop(proj, "accent", text="")
        prop_above(col, proj, "panorama_path")
        col.separator()
        labels(col, "Parts used by Make It for Me", "INFO")
        col.prop(proj, "parts_kind", text="")
        col.template_list("LLB_UL_parts", "", proj, "parts", proj, "parts_active", rows=6)
        row = col.row(align=True)
        row.operator("llb.parts_set", text="All On").enable = True
        row.operator("llb.parts_set", text="All Off").enable = False


class LLB_PT_preview(_Panel, bpy.types.Panel):
    page = "output"
    bl_label = "Preview"
    bl_order = 8

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        row = col.row(align=True)
        row.scale_y = 1.4
        row.operator("llb.preview_build", icon="PLAY")
        row.operator("llb.preview_clear", text="", icon="TRASH")
        col.operator("llb.view_audience", icon="CAMERA_DATA")
        col.prop(proj, "seed")
        col.separator()
        col.operator("llb.check_budget", icon="VIEWZOOM")
        draw_budget(col, proj.export)
        if context.scene.view_settings.view_transform != "Standard":
            labels(col, "Colors differ from Unity\n(view transform is not Standard)", "ERROR")
            col.operator("llb.view_standard", icon="COLOR")


BUDGET_LABELS = {"letter_flat": "Triangles per Flat Letter", "letter_solid": "Triangles per 3D Letter",
                 "tris": "Triangles on Stage", "particles": "Particles Alive", "materials": "Material Count"}


def draw_budget(layout, st):
    import json
    if not st.budget:
        return
    box = layout.box()
    box.label(text="Mobile Optimization" if st.use_mobile else "Without Mobile Optimization",
              icon="CHECKMARK" if st.use_mobile else "INFO")
    for key, (value, limit, at) in json.loads(st.budget).items():
        if key == "letter_solid" and not value:
            continue
        over = value > limit
        text = f"{iface_(BUDGET_LABELS[key])}: {value:,} / {limit:,}" + (f"  ({at} s)" if at else "")
        box.label(text=text, icon="ERROR" if over else "CHECKMARK", translate=False)


class LLB_PT_export(_Panel, bpy.types.Panel):
    page = "output"
    bl_label = "Unity Export"
    bl_order = 9

    def draw(self, context):
        from . import operators_export
        proj = context.scene.llb
        st = proj.export
        col = self.layout.column()
        prop_above(col, st, "project_path")
        prop_above(col, st, "unity_path")
        unity, _ = operators_export.unity_path(context)
        if unity:
            col.label(text=unity, icon="CHECKMARK", translate=False)
        else:
            col.label(text="Unity 2022.3.22f1 was not found", icon="ERROR")
        prop_above(col, st, "folder_name")
        col.label(text=iface_("Folder: {}").format("Assets/LyricLive/Songs/" + operators_export.song_name(proj)),
                  translate=False)
        prop_above(col, st, "material_mode")
        col.prop(st, "use_mobile")
        if st.use_mobile:
            sub = col.column(align=True)
            sub.prop(st, "particle_ratio", slider=True)
            sub.prop(st, "limit_tris")
            sub.prop(st, "limit_particles")
            sub.prop(st, "limit_materials")
        col.prop(st, "use_tmp")
        col.prop(st, "use_udon_sync")
        row = col.row()
        row.scale_y = 1.4
        row.operator("llb.export_unity", icon="EXPORT")
        if st.status:
            box = col.box()
            labels(box, st.status, "INFO")
            if st.log_path:
                box.label(text=st.log_path, translate=False)


CLASSES = PICK_MENUS + (LLB_PT_pages, LLB_PT_lyrics, LLB_PT_lyrics_notation, LLB_PT_fonts, LLB_PT_song, LLB_PT_sync, LLB_PT_omakase,
           LLB_PT_trial, LLB_PT_sections, LLB_PT_lines, LLB_PT_effects, LLB_PT_preview, LLB_PT_export)
