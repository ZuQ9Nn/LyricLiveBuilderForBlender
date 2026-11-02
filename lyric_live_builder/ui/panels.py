"""Sidebar panels (3D Viewport > N > LyricLive), in work order."""
import os

import bpy
from bpy.app.translations import pgettext_iface as iface_

from ..props import FONT_ROLES, SECTION_KIND_ITEMS
from . import project

ROLE_LABELS = {"display": "Display", "serif": "Serif", "body": "Body", "mono": "Mono"}
KIND_LABELS = {k: name for k, name, _ in SECTION_KIND_ITEMS}
NOTATION = (
    ("A/B", "Chunk break"),
    ("*word*", "Emphasis"),
    ("line!", "Strong accent"),
    ("line|note", "Annotation"),
    ("[01:23.45]line", "LRC time"),
    ("[A] [Chorus] [サビ]", "Section heading"),
    ("# ...", "Comment"),
    ("[ti:Title] [ar:Artist]", "Meta data"),
)


def fmt_time(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def labels(layout, msg, icon="NONE"):
    """A translated message on several rows (split at '\n'), so the narrow sidebar does not cut it."""
    for i, line in enumerate(iface_(msg).split("\n")):
        layout.label(text=line, icon=icon if i == 0 else "BLANK1", translate=False)


class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LyricLive"


class LLB_PT_lyrics(_Panel, bpy.types.Panel):
    bl_idname = "LLB_PT_lyrics"
    bl_label = "Lyrics"
    bl_order = 1

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
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
            row.label(text=sample, translate=False)
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
        col.operator("llb.tap_sync", icon="REC")
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


class LLB_UL_sections(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.label(text=f"{index + 1}. {item.label or iface_(KIND_LABELS[item.kind])}", translate=False)
        sub = row.row()
        sub.alignment = "RIGHT"
        sub.label(text=fmt_time(item.start), translate=False)


class LLB_UL_lines(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.38)
        split.label(text=fmt_time(item.start), translate=False,
                    icon={"tap": "REC", "lrc": "TIME", "manual": "GREASEPENCIL"}.get(item.source, "BLANK1"))
        split.label(text=item.text, translate=False)


class LLB_PT_sections(_Panel, bpy.types.Panel):
    bl_label = "Sections and Lines"
    bl_order = 6

    def draw(self, context):
        proj = context.scene.llb
        col = self.layout.column()
        labels(col, "Sections from headings" if proj.sections_from_headings else "Sections estimated\n(no headings)", "INFO")
        col.template_list("LLB_UL_sections", "", proj, "sections", proj, "section_active", rows=4)
        if 0 <= proj.section_active < len(proj.sections):
            sec = proj.sections[proj.section_active]
            col.prop(sec, "kind")
            col.label(text=f"{fmt_time(sec.start)} – {fmt_time(sec.end)}", translate=False)
        col.separator()
        col.template_list("LLB_UL_lines", "", proj, "lines", proj, "line_active", rows=6)
        if 0 <= proj.line_active < len(proj.lines):
            ln = proj.lines[proj.line_active]
            box = col.box()
            box.label(text=ln.text, translate=False)
            box.label(text=iface_("Start {}  End {}  ({})").format(
                fmt_time(ln.start), fmt_time(ln.end), iface_(ln.bl_rna.properties["source"].enum_items[ln.source].name)),
                translate=False)
            if 0 <= ln.section_index < len(proj.sections):
                sec = proj.sections[ln.section_index]
                box.label(text=iface_("Section {}").format(
                    f"{ln.section_index + 1}. {sec.label or iface_(KIND_LABELS[sec.kind])}"), translate=False)
            if ln.tap_time >= 0:
                box.label(text=iface_("Tap {}").format(fmt_time(ln.tap_time)), translate=False)
            row = box.row()
            row.prop(ln, "use_manual")
            sub = row.row()
            sub.active = ln.use_manual
            sub.prop(ln, "manual_start", text="")


CLASSES = (LLB_PT_lyrics, LLB_PT_lyrics_notation, LLB_PT_fonts, LLB_PT_song, LLB_PT_sync,
           LLB_UL_sections, LLB_UL_lines, LLB_PT_sections)
