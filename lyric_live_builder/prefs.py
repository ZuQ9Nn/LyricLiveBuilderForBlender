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

    def draw(self, context):
        self.layout.prop(self, "tap_latency_ms")
        self.layout.prop(self, "unity_path")


def get(context):
    """The add-on preferences, or None when the package is not enabled as an add-on (tests)."""
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def register():
    bpy.utils.register_class(LLBPreferences)


def unregister():
    bpy.utils.unregister_class(LLBPreferences)
