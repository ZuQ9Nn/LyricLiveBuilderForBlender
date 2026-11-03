"""The LyricLive preview collection: (re)build from a BakedScene, audience camera."""
import math

import bpy

from ..core import model
from . import animation, objects, particles

ROOT = "LyricLive"
TEXT = "LLB_Text"
CAMERA = "LLB_Camera"
CAMERA_OBJECT = "LLB_AudienceCamera"
CATEGORY_COLLECTIONS = {"text": TEXT, "background": "LLB_Background", "particles": "LLB_Particles",
                        "guide": "LLB_Guide", "gimmicks": "LLB_Gimmicks"}


def _collection(name, parent):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in parent.children:
        parent.children.link(coll)
    return coll


def clear(scene):
    """Remove the preview objects and their actions (shared glyph and built-in meshes stay for reuse)."""
    root = bpy.data.collections.get(ROOT)
    if root is None:
        return 0
    obs = [ob for ob in root.all_objects if ob.name != CAMERA_OBJECT]
    for ob in obs:
        act = ob.animation_data.action if ob.animation_data else None
        data = ob.data if ob.type == "MESH" and particles.PROP in ob.data else None
        bpy.data.objects.remove(ob)
        if act is not None and act.users == 0:
            bpy.data.actions.remove(act)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
    particles._cache.clear()
    from . import materials
    animation.clear_dome(bpy.data.materials.get(materials.DOME))
    return len(obs)


def audience_camera(scene, coll):
    ob = bpy.data.objects.get(CAMERA_OBJECT)
    if ob is None:
        cam = bpy.data.cameras.new(CAMERA_OBJECT)
        ob = bpy.data.objects.new(CAMERA_OBJECT, cam)
    if ob.name not in coll.objects:
        coll.objects.link(ob)
    ob.location = (0.0, 0.0, model.EYE_HEIGHT)
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = (math.pi / 2, 0.0, 0.0)          # looks along +Y, the front
    ob.data.lens_unit = "FOV"
    ob.data.angle = math.radians(90)
    ob.data.clip_start = 0.05
    ob.data.clip_end = 500.0
    scene.camera = ob
    return ob


def build(scene, baked, font_paths, resolution=6, panorama=""):
    clear(scene)
    root = _collection(ROOT, scene.collection)
    cams = _collection(CAMERA, root)
    audience_camera(scene, cams)
    colls = {cat: _collection(name, root) for cat, name in CATEGORY_COLLECTIONS.items()}
    obs = objects.build(baked, colls, font_paths, resolution, panorama)
    by_node = {}
    for tr in baked.tracks:
        by_node.setdefault(tr.node, []).append(tr)
    fps = scene.render.fps / scene.render.fps_base
    for nid, ob in obs.items():
        animation.apply(ob, by_node.get(nid, []), fps, scene.frame_start)
    particles.update_scene(scene)
    return obs
