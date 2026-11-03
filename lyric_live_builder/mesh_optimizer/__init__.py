"""Mesh Optimizer: cleaner text meshes, polygon reduction, merging and palette materials for
VRChat Quest / mobile (design §11). Independent of LyricLive Builder, which calls api.py; installed
on its own, register() adds the sidebar panel."""


def register():
    from . import ui
    ui.register()


def unregister():
    from . import ui
    ui.unregister()
