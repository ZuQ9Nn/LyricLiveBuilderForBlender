"""Preview operators: generate / delete / audience camera."""
import time

import bpy
from bpy.app.translations import pgettext_iface as iface_

from ..core import bake, planner
from ..preview import scene as preview_scene
from . import project


class LLB_OT_preview_build(bpy.types.Operator):
    bl_idname = "llb.preview_build"
    bl_label = "Generate"
    bl_description = "Build the lyric motion in the LyricLive collection (the same settings give the same result)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.lines) > 0

    def execute(self, context):
        scene = context.scene
        proj = scene.llb
        if not project.has_any_font(proj):
            self.report({"ERROR"}, iface_("Set at least the Body font"))
            return {"CANCELLED"}
        t0 = time.perf_counter()
        wm = context.window_manager
        wm.progress_begin(0, 3)
        try:
            lines = project.line_inputs(proj)
            secs = [(s.start, s.end) for s in proj.sections]
            plan = planner.plan(lines, secs, proj.duration, proj.seed, bpm=proj.bpm)
            wm.progress_update(1)
            baked = bake.bake(plan, project.metrics(proj))
            wm.progress_update(2)
            obs = preview_scene.build(scene, baked, lambda role: project.font_paths(proj, role))
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        finally:
            wm.progress_end()
        n = sum(1 for ob in obs.values() if ob.type == "MESH")
        self.report({"INFO"}, iface_("{} characters in {:.1f} s").format(n, time.perf_counter() - t0))
        return {"FINISHED"}


class LLB_OT_preview_clear(bpy.types.Operator):
    bl_idname = "llb.preview_clear"
    bl_label = "Delete"
    bl_description = "Remove the generated objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        preview_scene.clear(context.scene)
        return {"FINISHED"}


class LLB_OT_view_audience(bpy.types.Operator):
    bl_idname = "llb.view_audience"
    bl_label = "Audience View"
    bl_description = "Look through the audience camera with material preview shading"

    def execute(self, context):
        cam = bpy.data.objects.get(preview_scene.CAMERA_OBJECT)
        if cam is None:
            self.report({"ERROR"}, iface_("Generate the preview first"))
            return {"CANCELLED"}
        context.scene.camera = cam
        area = context.area if context.area and context.area.type == "VIEW_3D" else next(
            (a for a in context.screen.areas if a.type == "VIEW_3D"), None)
        if area:
            space = area.spaces.active
            space.region_3d.view_perspective = "CAMERA"
            space.shading.type = "MATERIAL"
        return {"FINISHED"}


CLASSES = (LLB_OT_preview_build, LLB_OT_preview_clear, LLB_OT_view_audience)
