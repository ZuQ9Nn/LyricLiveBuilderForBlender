import bpy

from . import ja_JP

# Labels are looked up with the default context and operator labels with "Operator"
_CONTEXTS = ("*", "Operator")


def _build():
    return {"ja_JP": {(ctx, k): v for k, v in ja_JP.MESSAGES.items() for ctx in _CONTEXTS}}


def register():
    bpy.app.translations.register(__package__, _build())


def unregister():
    bpy.app.translations.unregister(__package__)
