"""Polygon reduction: planar dissolve, then (if asked) collapse with Blender's Decimate modifier."""
import math

import bmesh
import bpy


def planar(mesh, angle_deg=2.0):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(angle_deg), verts=bm.verts, edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.to_mesh(mesh)
    bm.free()


def collapse(mesh, ratio):
    """Apply a Collapse decimation to the mesh data through a temporary object."""
    ob = bpy.data.objects.new("mo_tmp", mesh)
    bpy.context.scene.collection.objects.link(ob)
    try:
        mod = ob.modifiers.new("mo_decimate", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = max(0.01, min(1.0, ratio))
        dg = bpy.context.evaluated_depsgraph_get()
        result = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    finally:
        bpy.data.objects.remove(ob)
    bm = bmesh.new()
    bm.from_mesh(result)
    bm.to_mesh(mesh)
    bm.free()
    bpy.data.meshes.remove(result)


def triangles(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)
