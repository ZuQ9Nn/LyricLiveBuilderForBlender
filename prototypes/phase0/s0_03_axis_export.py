"""S0-03: LLBM mesh + coordinate conversion round trip, Blender side.

Builds an extruded "F" (asymmetric on every axis) with a red marker child, animates it
(move + yaw + pitch), writes meshes.bin + s003.json for Unity and renders viewer-camera
PNGs at t = 0, 1, 2 s for comparison with Unity.
"""
import json
import math
import os
import struct

import bpy
from mathutils import Euler

import convert_proto as cv

FPS = 30
DURATION = 2.0
TIMES = (0.0, 1.0, 2.0)


def _mat(name, rgba):
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


def build_scene(font_path):
    sc = bpy.context.scene
    sc.render.fps = FPS
    cu = bpy.data.curves.new("F", "FONT")
    cu.body, cu.font = "F", bpy.data.fonts.load(font_path)
    cu.size, cu.extrude, cu.align_x, cu.align_y = 1.2, 0.12, "CENTER", "CENTER"
    f = bpy.data.objects.new("F_body", cu)
    sc.collection.objects.link(f)
    f.data.materials.append(_mat("white", (0.9, 0.9, 0.9, 1)))
    f.rotation_mode = "QUATERNION"
    # marker: top-right corner, sticking out toward the viewer (local -Z of the text = after stand-up, -Y)
    bpy.ops.mesh.primitive_cube_add(size=0.18)
    mk = bpy.context.active_object
    mk.name = "F_marker"
    mk.parent = f
    mk.location = (0.35, 0.45, 0.2)
    mk.data.materials.append(_mat("red", (1, 0.05, 0.05, 1)))
    # animation: stand the letter up (+90 X), then over 2 s: move +X, yaw +90 (Z), pitch +30 (X)
    for i in range(int(DURATION * FPS) + 1):
        t = i / FPS
        u = t / DURATION
        f.location = (u * 1.0, 3.0, 1.5)
        q = Euler((0, 0, math.radians(90 * u)), "XYZ").to_quaternion()
        q = q @ Euler((math.radians(90 + 30 * u), 0, 0), "XYZ").to_quaternion()
        f.rotation_quaternion = q
        f.keyframe_insert("location", frame=i + 1)
        f.keyframe_insert("rotation_quaternion", frame=i + 1)
    cam = bpy.data.objects.new("viewer", bpy.data.cameras.new("viewer"))
    sc.collection.objects.link(cam)
    cam.location = (0, 0, 1.5)
    cam.rotation_euler = (math.radians(90), 0, 0)      # looks along +Y
    cam.data.sensor_fit = "VERTICAL"
    cam.data.angle = math.radians(60)                  # vertical FOV, same as the Unity camera
    sc.camera = cam
    return f, mk


def export(f, mk, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    dg = bpy.context.evaluated_depsgraph_get()
    blobs, meshes = [], []
    for ob in (f, mk):
        me = ob.evaluated_get(dg).to_mesh()
        data = cv.mesh_to_llbm(me)
        ob.evaluated_get(dg).to_mesh_clear()
        meshes.append({"key": ob.name, "offset": sum(len(b) for b in blobs), "length": len(data)})
        blobs.append(data)
    with open(os.path.join(out_dir, "meshes.bin"), "wb") as fh:
        fh.write(b"".join(blobs))
    sc = bpy.context.scene
    times, pos, rot = [], [], []
    for i in range(int(DURATION * FPS) + 1):
        sc.frame_set(i + 1)
        times.append(i / FPS)
        pos += cv.pos(tuple(f.location))
        rot += cv.quat(tuple(f.rotation_quaternion))
    mk_q = mk.matrix_basis.to_quaternion()
    doc = {
        "meshes": meshes,
        "nodes": [
            {"name": "F_body", "mesh": "F_body", "parent": "", "color": [0.9, 0.9, 0.9, 1],
             "p": list(cv.pos(tuple(f.location))), "r": list(cv.quat(tuple(f.rotation_quaternion))), "s": [1, 1, 1]},
            {"name": "F_marker", "mesh": "F_marker", "parent": "F_body", "color": [1, 0.05, 0.05, 1],
             "p": list(cv.pos(tuple(mk.location))), "r": list(cv.quat(tuple(mk_q))), "s": list(cv.scale(tuple(mk.scale)))},
        ],
        "clip": {"node": "F_body", "times": times, "pos": pos, "rot": rot},
        "camera": {"p": list(cv.pos((0, 0, 1.5))), "fov": 60},
        "sampleTimes": list(TIMES),
    }
    with open(os.path.join(out_dir, "s003.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)


def render(png_dir):
    os.makedirs(png_dir, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.color_type = "MATERIAL"
    sc.render.resolution_x, sc.render.resolution_y = 640, 480
    for t in TIMES:
        sc.frame_set(int(round(t * FPS)) + 1)
        sc.render.filepath = os.path.join(png_dir, f"s003_blender_t{t:.0f}.png")
        bpy.ops.render.render(write_still=True)
