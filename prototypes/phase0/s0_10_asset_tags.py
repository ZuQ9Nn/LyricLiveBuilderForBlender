"""S0-10: reading asset tags from .blend files in an asset library.

make_library(path): writes a .blend with 100 tagged mesh assets (test data).
index(paths): links objects with assets_only=True, reads asset_data.tags, then removes the
library and any orphan data it brought in. Returns the index, the time and leftover counts.
"""
import time
import bpy

TAGS = ["star", "moon", "heart", "cloud", "flower", "cat", "door", "key", "clock", "umbrella"]


def make_library(path):
    for i in range(100):
        me = bpy.data.meshes.new(f"asset_mesh_{i:03d}")
        me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        ob = bpy.data.objects.new(f"asset_{i:03d}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.asset_mark()
        ob.asset_data.tags.new(TAGS[i % len(TAGS)])
        ob.asset_data.tags.new(f"group{i % 3}")
    bpy.ops.wm.save_as_mainfile(filepath=path)


def _counts():
    return {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials), "libraries": len(bpy.data.libraries)}


def index(paths):
    before = _counts()
    t0 = time.perf_counter()
    entries = []
    for path in paths:
        with bpy.data.libraries.load(path, link=True, assets_only=True) as (src, dst):
            dst.objects = list(src.objects)
        lib = None
        for ob in dst.objects:
            if ob is None:
                continue
            lib = ob.library
            tags = [t.name for t in ob.asset_data.tags] if ob.asset_data else []
            entries.append({"file": path, "name": ob.name, "tags": tags})
        if lib is not None:
            bpy.data.libraries.remove(lib)
    elapsed = time.perf_counter() - t0
    # No orphans_purge: it would also delete the user's own unused data-blocks.
    # Removing the library already removes everything that was linked from it.
    return {"entries": len(entries), "sample": entries[:2], "seconds": round(elapsed, 3),
            "before": before, "after": _counts()}
