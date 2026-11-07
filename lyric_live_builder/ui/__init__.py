import bpy

from . import lists, operators_export, operators_input, operators_omakase, operators_preview, panels, tap_sync

CLASSES = (operators_input.CLASSES + operators_preview.CLASSES + operators_omakase.CLASSES + operators_export.CLASSES
           + tap_sync.CLASSES + lists.CLASSES + panels.CLASSES)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    from ..preview import particles
    particles.register()


def unregister():
    operators_input.stop_watch()
    from ..preview import particles
    particles.unregister()
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
