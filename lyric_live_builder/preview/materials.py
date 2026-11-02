"""Preview materials: one shared unlit text material driven by the object colour and alpha."""
import bpy

TEXT = "LLB_Text"


def text_material():
    mat = bpy.data.materials.get(TEXT)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(TEXT)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    info = nt.nodes.new("ShaderNodeObjectInfo")
    # faces turned away from the view (the sides of 3D letters) get darker
    facing = nt.nodes.new("ShaderNodeLayerWeight")
    facing.inputs["Blend"].default_value = 0.5
    shade = nt.nodes.new("ShaderNodeMix")
    shade.data_type = "RGBA"
    shade.blend_type = "MULTIPLY"
    shade.inputs["B"].default_value = (0.35, 0.35, 0.4, 1.0)
    emit = nt.nodes.new("ShaderNodeEmission")
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(facing.outputs["Facing"], shade.inputs["Factor"])
    nt.links.new(info.outputs["Color"], shade.inputs["A"])
    nt.links.new(shade.outputs["Result"], emit.inputs["Color"])
    nt.links.new(info.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(clear.outputs["BSDF"], mix.inputs[1])
    nt.links.new(emit.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    for k, n in enumerate((info, facing, shade, emit, clear, mix, out)):
        n.location = (k * 200, 0)
    mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = False
    return mat
