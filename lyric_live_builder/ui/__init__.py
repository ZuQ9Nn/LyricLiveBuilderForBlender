import bpy

from . import operators_input, panels, tap_sync

CLASSES = operators_input.CLASSES + tap_sync.CLASSES + panels.CLASSES


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
