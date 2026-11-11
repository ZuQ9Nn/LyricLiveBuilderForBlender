"""UILists: sections, lines and the part switches of the effects panel."""
import bpy
from bpy.app.translations import pgettext_iface as iface_

from ..props import SECTION_KIND_ITEMS

KIND_LABELS = {k: name for k, name, _ in SECTION_KIND_ITEMS}


def fmt_time(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


class LLB_UL_sections(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.label(text=f"{index + 1}. {item.label or iface_(KIND_LABELS[item.kind])}", translate=False,
                  icon="LOCKED" if item.locked else "NONE")
        sub = row.row()
        sub.alignment = "RIGHT"
        sub.label(text=fmt_time(item.start), translate=False)


class LLB_UL_lines(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        split = row.split(factor=0.38)
        split.label(text=fmt_time(item.start), translate=False,
                    icon={"tap": "REC", "lrc": "TIME", "manual": "GREASEPENCIL"}.get(item.source, "BLANK1"))
        split.label(text=item.text, translate=False, icon="LOCKED" if item.locked else "NONE")
        row.operator("llb.line_details", text="", icon="PREFERENCES", emboss=False).index = index     # spec §6.2


class LLB_UL_parts(bpy.types.UIList):
    """Part switches, showing only the kind chosen above the list."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "enabled", text=iface_(item.label), translate=False)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flags = [self.bitflag_filter_item if it.kind == data.parts_kind else 0 for it in items]
        return flags, []


CLASSES = (LLB_UL_sections, LLB_UL_lines, LLB_UL_parts)
