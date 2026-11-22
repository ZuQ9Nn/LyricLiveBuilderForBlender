"""UILists: sections, lines and the part switches of the effects panel."""
import bpy
from bpy.app.translations import pgettext_iface as iface_

from ..props import SECTION_KIND_ITEMS

KIND_LABELS = {k: name for k, name, _ in SECTION_KIND_ITEMS}


def fmt_time(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def section_tag(proj, k):
    """Short name of section k for the line list: "4.Chorus"."""
    if not 0 <= k < len(proj.sections):
        return ""
    sec = proj.sections[k]
    return f"{k + 1}.{sec.label or iface_(KIND_LABELS[sec.kind])}"


class LLB_UL_lines(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        # the section the line is in (spec §6.2): plain on its first line, dimmed on the others
        first = index == 0 or data.lines[index - 1].section_index != item.section_index
        split = row.split(factor=0.26)
        sub = split.row()
        sub.active = first
        sub.label(text=section_tag(data, item.section_index), translate=False)
        split = split.split(factor=0.3)
        # short, and without the source icon (shown below the list): room for the section and the text
        split.label(text=f"{int(item.start // 60)}:{int(item.start % 60):02d}", translate=False)
        split.label(text=item.text, translate=False, icon="LOCKED" if item.locked else "NONE")
        # set on the line itself: particles added, background changed
        if item.particle != "AUTO":
            row.label(text="", icon="PARTICLES")
        if item.background != "AUTO":
            row.label(text="", icon="WORLD")
        row.operator("llb.line_details", text="", icon="PREFERENCES", emboss=False).index = index     # spec §6.2


class LLB_UL_parts(bpy.types.UIList):
    """Part switches, showing only the kind chosen above the list."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "enabled", text=iface_(item.label), translate=False)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flags = [self.bitflag_filter_item if it.kind == data.parts_kind else 0 for it in items]
        return flags, []


CLASSES = (LLB_UL_lines, LLB_UL_parts)
