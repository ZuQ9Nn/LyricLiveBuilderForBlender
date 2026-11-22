import bpy

from . import (details, lists, operators_export, operators_input, operators_omakase, operators_preview, panels,
               section_window, tap_sync, thumbnails, trial)

CLASSES = (operators_input.CLASSES + operators_preview.CLASSES + operators_omakase.CLASSES + operators_export.CLASSES
           + tap_sync.CLASSES + trial.CLASSES + details.CLASSES + section_window.CLASSES + thumbnails.CLASSES + lists.CLASSES + panels.CLASSES)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    from ..preview import particles
    particles.register()
    trial.register()
    details.register()


def unregister():
    operators_input.stop_watch()
    thumbnails.unregister()
    details.unregister()
    trial.unregister()
    from ..preview import particles
    particles.unregister()
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
