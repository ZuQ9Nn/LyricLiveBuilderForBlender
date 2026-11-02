"""LyricLive Builder: lyric motion, particles and stage for VRChat ParticleLive worlds.

Nothing here imports bpy at module level, so core/ and text/fontinfo.py can be
imported (and unit tested) without Blender.
"""
_modules = ()


def register():
    global _modules
    from . import i18n, prefs, props, ui
    _modules = (i18n, prefs, props, ui)
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()
