"""Joining static objects and folding colour-only materials into one palette material."""
import bmesh
import bpy

PALETTE = "MO_Palette"
COLOR_ATTR = "mo_color"


def join(objects, name="Merged"):
    """One new mesh object holding the given mesh objects in world space (the originals are kept)."""
    bm = bmesh.new()
    materials = []
    for ob in objects:
        if ob.type != "MESH":
            continue
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        tmp.transform(ob.matrix_world)
        remap = []
        for m in ob.data.materials:
            if m not in materials:
                materials.append(m)
            remap.append(materials.index(m))
        for f in tmp.faces:
            f.material_index = remap[f.material_index] if remap else 0
        me_tmp = bpy.data.meshes.new("mo_tmp")
        tmp.to_mesh(me_tmp)
        tmp.free()
        bm.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in materials:
        me.materials.append(m)
    return bpy.data.objects.new(name, me)


def base_color(mat):
    """The colour a simple material shows: Principled / Emission colour, else the viewport colour."""
    if mat is None:
        return (0.8, 0.8, 0.8, 1.0)
    if mat.use_nodes and mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                return tuple(n.inputs["Base Color"].default_value)
            if n.type == "EMISSION":
                return tuple(n.inputs["Color"].default_value)
    return tuple(mat.diffuse_color)


def palette_material():
    mat = bpy.data.materials.get(PALETTE)
    if mat is None:
        mat = bpy.data.materials.new(PALETTE)
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_type = "GEOMETRY"
        attr.attribute_name = COLOR_ATTR
        nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def paint_and_assign(ob, mat):
    """Write each face's material colour into a colour attribute, then use the one palette material."""
    me = ob.data
    colors = [base_color(m) for m in me.materials] or [(0.8, 0.8, 0.8, 1.0)]
    attr = me.color_attributes.get(COLOR_ATTR) or me.color_attributes.new(COLOR_ATTR, "BYTE_COLOR", "CORNER")
    for poly in me.polygons:
        c = colors[min(poly.material_index, len(colors) - 1)]
        for li in poly.loop_indices:
            attr.data[li].color = c
    me.materials.clear()
    me.materials.append(mat)
    return colors
