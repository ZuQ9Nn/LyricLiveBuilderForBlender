"""Sidebar panel when mesh_optimizer is installed on its own (3D Viewport > N > Mesh Optimizer)."""
import bpy
from bpy.props import FloatProperty, IntProperty, PointerProperty

from . import api


class MO_Settings(bpy.types.PropertyGroup):
    resolution: IntProperty(name="Curve Resolution", default=4, min=1, max=24,
                            description="Text curve resolution before meshing (6 normal, 4 for mobile)")
    angle: FloatProperty(name="Dissolve Angle", default=1.0, min=0.1, max=api.MAX_ANGLE,
                         description="Limited dissolve angle in degrees (above 3° Mincho letters lose shape)")
    depth: FloatProperty(name="Thickness", default=0.0, min=0.0, soft_max=1.0, unit="LENGTH",
                         description="Extrude the cleaned letters (0 = flat)")
    ratio: FloatProperty(name="Keep Ratio", default=0.5, min=0.01, max=1.0, subtype="FACTOR",
                         description="Share of triangles kept by Decimate")


def _settings(context):
    return context.scene.mesh_optimizer


class MO_OT_clean_text(bpy.types.Operator):
    bl_idname = "mesh_optimizer.clean_text"
    bl_label = "Clean Up Text"
    bl_description = "Turn the selected text objects into clean meshes (holes kept); meshes are cleaned in place"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type in ("FONT", "MESH") for o in context.selected_objects)

    def execute(self, context):
        st = _settings(context)
        before = after = broken = 0
        for ob in [o for o in context.selected_objects if o.type in ("FONT", "MESH")]:
            if ob.type == "FONT":
                api.optimize_text_curve(ob, resolution=st.resolution)
                dg = context.evaluated_depsgraph_get()
                me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
                new = bpy.data.objects.new(ob.name + "_mesh", me)
                new.matrix_world = ob.matrix_world
                for c in ob.users_collection:
                    c.objects.link(new)
                ob.hide_set(True)
                ob.hide_render = True
                new.select_set(True)
                context.view_layer.objects.active = new
            else:
                me = ob.data
            rep = api.retopo_flat_text_mesh(me, dissolve_angle_deg=st.angle, depth=st.depth)
            before, after = before + rep.tris_before, after + rep.tris_after
            broken += 0 if rep.holes_kept else 1
        self.report({"WARNING" if broken else "INFO"},
                    bpy.app.translations.pgettext_iface("Triangles {} -> {}").format(before, after)
                    + (bpy.app.translations.pgettext_iface(", {} with changed holes").format(broken) if broken else ""))
        return {"FINISHED"}


class MO_OT_decimate(bpy.types.Operator):
    bl_idname = "mesh_optimizer.decimate"
    bl_label = "Reduce Polygons"
    bl_description = "Dissolve flat areas, then collapse the selected meshes to the kept ratio"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        st = _settings(context)
        total = sum(api.decimate(o.data, ratio=st.ratio) for o in context.selected_objects if o.type == "MESH")
        self.report({"INFO"}, bpy.app.translations.pgettext_iface("Triangles left: {}").format(total))
        return {"FINISHED"}


class MO_OT_merge(bpy.types.Operator):
    bl_idname = "mesh_optimizer.merge"
    bl_label = "Merge Static Objects"
    bl_description = "Join the selected meshes (one object per material); the originals are hidden"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return sum(1 for o in context.selected_objects if o.type == "MESH") > 1

    def execute(self, context):
        sel = [o for o in context.selected_objects if o.type == "MESH"]
        for new in api.merge_static_objects(sel):
            context.collection.objects.link(new)
        for o in sel:
            o.hide_set(True)
            o.hide_render = True
        return {"FINISHED"}


class MO_OT_palette(bpy.types.Operator):
    bl_idname = "mesh_optimizer.palette"
    bl_label = "One Palette Material"
    bl_description = "Replace colour-only materials of the selected meshes with one material and a colour attribute"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        try:
            res = api.bake_palette_material(context.selected_objects)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, bpy.app.translations.pgettext_iface("{} colours in one material").format(len(res.colors)))
        return {"FINISHED"}


class MO_PT_panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mesh Optimizer"
    bl_label = "Mesh Optimizer"

    def draw(self, context):
        st = _settings(context)
        col = self.layout.column()
        col.prop(st, "resolution")
        col.prop(st, "angle")
        col.prop(st, "depth")
        col.operator("mesh_optimizer.clean_text", icon="OUTLINER_OB_FONT")
        col.separator()
        col.prop(st, "ratio", slider=True)
        col.operator("mesh_optimizer.decimate", icon="MOD_DECIM")
        col.operator("mesh_optimizer.merge", icon="AUTOMERGE_ON")
        col.operator("mesh_optimizer.palette", icon="COLOR")


CLASSES = (MO_Settings, MO_OT_clean_text, MO_OT_decimate, MO_OT_merge, MO_OT_palette, MO_PT_panel)

JA = {
    "Mesh Optimizer": "メッシュ最適化", "Curve Resolution": "曲線の解像度", "Dissolve Angle": "溶解の角度",
    "Thickness": "厚み", "Keep Ratio": "残す割合", "Clean Up Text": "文字を整理", "Reduce Polygons": "ポリゴンを減らす",
    "Merge Static Objects": "動かない物体を結合", "One Palette Material": "マテリアルを 1 つにまとめる",
    "Text curve resolution before meshing (6 normal, 4 for mobile)": "メッシュにする前の文字の曲線の解像度（通常 6、モバイル 4）",
    "Limited dissolve angle in degrees (above 3° Mincho letters lose shape)": "限定的溶解の角度（3° を超えると明朝体の形が崩れる）",
    "Extrude the cleaned letters (0 = flat)": "整理した文字に厚みを付ける（0 = 平ら）",
    "Share of triangles kept by Decimate": "減面で残す三角形の割合",
    "Turn the selected text objects into clean meshes (holes kept); meshes are cleaned in place": "選んだテキストを、穴を保ったまま整理したメッシュにします（メッシュはそのまま整理します）",
    "Dissolve flat areas, then collapse the selected meshes to the kept ratio": "平らな部分を溶解し、選んだメッシュを残す割合まで減らします",
    "Join the selected meshes (one object per material); the originals are hidden": "選んだメッシュを結合します（マテリアルごとに 1 つ）。元の物体は隠します",
    "Replace colour-only materials of the selected meshes with one material and a colour attribute": "色だけが違うマテリアルを、1 つのマテリアルと色の属性に置き換えます",
    "Triangles {} -> {}": "三角形 {} → {}", ", {} with changed holes": "、穴の数が変わったもの {}",
    "Triangles left: {}": "残った三角形：{}", "{} colours in one material": "{} 色を 1 つのマテリアルに",
}


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.mesh_optimizer = PointerProperty(type=MO_Settings)
    ja = {(ctx, k): v for k, v in JA.items() for ctx in ("*", "Operator")}
    bpy.app.translations.register(__package__, {"ja_JP": ja})


def unregister():
    bpy.app.translations.unregister(__package__)
    del bpy.types.Scene.mesh_optimizer
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
