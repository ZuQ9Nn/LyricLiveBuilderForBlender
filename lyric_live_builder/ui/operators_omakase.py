"""おまかせ, proposal history, "change only this", locks and re-rolls, part switches (spec §6)."""
import bpy
from bpy.app.translations import pgettext_iface as iface_

from ..core import omakase
from . import planning


def _build(op, context):
    try:
        n, dt = planning.build_preview(context)
    except ValueError as e:
        op.report({"ERROR"}, iface_(str(e)))
        return {"CANCELLED"}
    op.report({"INFO"}, iface_("{} characters in {:.1f} s").format(n, dt))
    return {"FINISHED"}


class _NeedsLines:
    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.lines) > 0


class LLB_OT_omakase(_NeedsLines, bpy.types.Operator):
    bl_idname = "llb.omakase"
    bl_label = "Make It for Me"
    bl_description = ("Roll a mood, a style, effect strengths, parts and colours, then build everything. "
                      "Lyrics, timing, sections and locked lines stay")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        proj = context.scene.llb
        planning.sync_parts(proj)
        if not len(proj.history):
            planning.push_history(proj, planning.state(proj))
        st = omakase.omakase(planning.state(proj), planning.random())
        planning.apply_state(proj, st)
        planning.push_history(proj, st)
        return _build(self, context)


class LLB_OT_history_step(_NeedsLines, bpy.types.Operator):
    bl_idname = "llb.history_step"
    bl_label = "Previous / Next Proposal"
    bl_description = "Go back or forward through the proposals"
    bl_options = {"REGISTER", "UNDO"}
    step: bpy.props.IntProperty(default=-1)

    @classmethod
    def description(cls, context, props):
        return iface_("Previous proposal") if props.step < 0 else iface_("Next proposal")

    def execute(self, context):
        proj = context.scene.llb
        i = proj.history_index + self.step
        if not 0 <= i < len(proj.history):
            return {"CANCELLED"}
        proj.history_index = i
        planning.apply_state(proj, planning.history_state(proj, i))
        return _build(self, context)


class LLB_OT_reroll(_NeedsLines, bpy.types.Operator):
    bl_idname = "llb.reroll"
    bl_label = "Change Only This"
    bl_description = "Roll only the chosen aspect again; everything else stays"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        proj = context.scene.llb
        planning.sync_parts(proj)
        if not len(proj.history):
            planning.push_history(proj, planning.state(proj))
        st = omakase.reroll(planning.state(proj), proj.reroll_target, planning.random())
        planning.apply_state(proj, st)
        planning.push_history(proj, st)
        return _build(self, context)


class LLB_OT_line_lock(_NeedsLines, bpy.types.Operator):
    bl_idname = "llb.line_lock"
    bl_label = "Lock Line"
    bl_description = "Lock: keep this line's layout and motions through Make It for Me. Unlock: back to automatic"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        proj = context.scene.llb
        i = proj.line_active
        if not 0 <= i < len(proj.lines):
            return {"CANCELLED"}
        if proj.lines[i].locked:
            planning.unlock(proj.lines[i])
        else:
            planning.lock_line(proj, i)
        return {"FINISHED"}


class LLB_OT_line_reroll(_NeedsLines, bpy.types.Operator):
    bl_idname = "llb.line_reroll"
    bl_label = "Re-roll Line"
    bl_description = "Choose this line's layout and motions again (the other lines stay)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        proj = context.scene.llb
        ln = proj.lines[proj.line_active]
        if ln.locked:
            self.report({"WARNING"}, iface_("Unlock the line first"))
            return {"CANCELLED"}
        ln.seed_offset += 1
        return _build(self, context)


class LLB_OT_section_lock(_NeedsLines, bpy.types.Operator):
    bl_idname = "llb.section_lock"
    bl_label = "Lock Section"
    bl_description = "Lock: keep this section's theme, background and transition. Unlock: back to automatic"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        proj = context.scene.llb
        i = proj.section_active
        if not 0 <= i < len(proj.sections):
            return {"CANCELLED"}
        if proj.sections[i].locked:
            planning.unlock(proj.sections[i])
        else:
            planning.lock_section(proj, i)
        return {"FINISHED"}


class LLB_OT_parts_set(bpy.types.Operator):
    bl_idname = "llb.parts_set"
    bl_label = "Switch All"
    bl_description = "Turn every part of the shown kind on or off"
    bl_options = {"REGISTER", "UNDO"}
    enable: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        proj = context.scene.llb
        planning.sync_parts(proj)
        for p in proj.parts:
            if p.kind == proj.parts_kind:
                p.enabled = self.enable
        return {"FINISHED"}


class LLB_OT_view_standard(bpy.types.Operator):
    bl_idname = "llb.view_standard"
    bl_label = "Use Standard Colors"
    bl_description = "Set the view transform to Standard so colours look as they will in Unity (unlit)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.scene.view_settings.view_transform = "Standard"
        context.scene.view_settings.look = "None"
        return {"FINISHED"}


class LLB_OT_pick_part(bpy.types.Operator):
    bl_idname = "llb.pick_part"
    bl_label = "Pick a Part"
    bl_description = "Use this layout or motion for the line"
    bl_options = {"UNDO", "INTERNAL"}

    field: bpy.props.StringProperty()
    key: bpy.props.StringProperty()

    def execute(self, context):
        proj = context.scene.llb
        if not 0 <= proj.line_active < len(proj.lines):
            return {"CANCELLED"}
        setattr(proj.lines[proj.line_active], self.field, self.key)
        return {"FINISHED"}


CLASSES = (LLB_OT_pick_part, LLB_OT_omakase, LLB_OT_history_step, LLB_OT_reroll, LLB_OT_line_lock, LLB_OT_line_reroll,
           LLB_OT_section_lock, LLB_OT_parts_set, LLB_OT_view_standard)
