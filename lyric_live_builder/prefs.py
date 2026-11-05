import bpy
from bpy.props import FloatProperty, StringProperty


class LLBPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    tap_latency_ms: FloatProperty(
        name="Tap Latency (ms)",
        description="Last measured tap latency. Used by files that have not measured their own",
        default=0.0, soft_min=-200.0, soft_max=300.0,
    )

    unity_path: StringProperty(
        name="Unity Editor Path", subtype="FILE_PATH",
        description="Unity.exe to use for every file (empty = find Unity 2022.3.22f1 automatically)",
    )

    asset_library: StringProperty(
        name="Asset Library",
        description="The Blender asset library holding your stage objects. Tag them with words (cat, moon): "
                    "a tag found in the lyrics brings that object on stage",
    )

    gimmick_words: StringProperty(
        name="Extra Keywords",
        description="More words for a tag, for example: cat=mike,tama; fox=kitsune",
    )

    library_status: StringProperty(description="Result of the last library refresh")

    def draw(self, context):
        self.layout.prop(self, "tap_latency_ms")
        self.layout.prop(self, "unity_path")
        col = self.layout.column()
        col.prop_search(self, "asset_library", context.preferences.filepaths, "asset_libraries")
        row = col.row()
        row.operator("llb.refresh_library", icon="FILE_REFRESH")
        row.label(text=self.library_status, translate=False)
        col.prop(self, "gimmick_words")


def get(context):
    """The add-on preferences, or None when the package is not enabled as an add-on (tests)."""
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def register():
    bpy.utils.register_class(LLBPreferences)


def unregister():
    bpy.utils.unregister_class(LLBPreferences)
