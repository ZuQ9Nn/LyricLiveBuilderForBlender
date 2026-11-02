"""Builds tests/manual/check_phase0.blend for the reviewer (run in background Blender).

  blender --background --factory-startup --python prototypes/phase0/build_check_blend.py

Contents: collection S0-01 (glyph spacing), S0-09 (retopo before/after) and the S0-08
script as a text block (Text Editor > Run Script adds the "LLB試作" sidebar tab).
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s0_01_glyph_metrics as s01   # noqa: E402
import s0_09_retopo as s09          # noqa: E402

RETOPO_RESOLUTION = 4               # S0-09 result: mobile default
RETOPO_ANGLE = 1.0


def main():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    root = bpy.data.collections.new("LLB_Phase0")
    bpy.context.scene.collection.children.link(root)
    s01.build_collection(root)
    s09.build_collection(root, RETOPO_RESOLUTION, RETOPO_ANGLE)
    with open(os.path.join(HERE, "s0_08_tap_latency.py"), encoding="utf-8") as f:
        txt = bpy.data.texts.new("s0_08_tap_latency.py")
        txt.write(f.read())
    out = os.path.normpath(os.path.join(HERE, "..", "..", "tests", "manual", "check_phase0.blend"))
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("SAVED", out)


main()
