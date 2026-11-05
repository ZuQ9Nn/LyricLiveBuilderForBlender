"""Preview operators: generate / delete / audience camera."""
import bpy
from bpy.app.translations import pgettext_iface as iface_

from .. import prefs
from ..preview import gimmick_assets
from ..preview import scene as preview_scene
from . import planning


class LLB_OT_preview_build(bpy.types.Operator):
    bl_idname = "llb.preview_build"
    bl_label = "Generate"
    bl_description = "Build the lyric motion in the LyricLive collection (the same settings give the same result)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.lines) > 0

    def execute(self, context):
        try:
            n, dt = planning.build_preview(context)
        except ValueError as e:
            self.report({"ERROR"}, iface_(str(e)))
            return {"CANCELLED"}
        self.report({"INFO"}, iface_("{} characters in {:.1f} s").format(n, dt))
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


class LLB_OT_refresh_library(bpy.types.Operator):
    bl_idname = "llb.refresh_library"
    bl_label = "Refresh the Library"
    bl_description = "Read the tags of every object in the asset library. Nothing is added to the open file"

    def execute(self, context):
        p = prefs.get(context)
        folder = gimmick_assets.library_folder(p.asset_library) if p else ""
        if not folder:
            self.report({"ERROR"}, iface_("Choose an asset library first"))
            return {"CANCELLED"}
        count, tags = gimmick_assets.refresh(folder)
        p.library_status = iface_("{} objects, {} tags").format(count, tags)
        self.report({"INFO"}, p.library_status)
        return {"FINISHED"}


CLASSES = (LLB_OT_preview_build, LLB_OT_preview_clear, LLB_OT_view_audience, LLB_OT_refresh_library)
