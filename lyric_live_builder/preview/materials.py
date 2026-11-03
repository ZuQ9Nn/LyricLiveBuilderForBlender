"""Preview materials (design §12). Text, far objects, glows and 3D particles read the object colour
and alpha; the dome's parameters are Value / RGB nodes named llb_<param>, animated on its node
tree (EEVEE limits how many object attributes a material may read; Blender 5.0 drew the dome
black with ~25 of them); 2D particles read the atlas and a per-vertex colour."""
import bpy
import numpy as np

from ..core import atlas
from ..core.parts import backgrounds as bgs

TEXT = "LLB_Text"
FAR = "LLB_Far"
GLOW = "LLB_Glow"
DOME = "LLB_Dome"
DOME_SLOT = "LLB_DomeSlot"
DOME_COLORS = ("top", "horizon", "bottom", "ink", "flash_color", "cue_dir")      # RGB nodes; the rest are Value
PARTICLE_ADD = "LLB_ParticleAdd"
PARTICLE_ALPHA = "LLB_ParticleAlpha"
PARTICLE_3D = "LLB_Particle3D"
ATLAS = "LLB_ParticleAtlas"
COLOR_ATTR = "llb_col"


class _Tree:
    """Small helper to wire node trees: constants or sockets as inputs."""

    def __init__(self, tree):
        self.t = tree
        self.x = 0

    def node(self, kind, inputs=None, **props):
        n = self.t.nodes.new(kind)
        n.location = (self.x, 0)
        self.x += 30
        for k, v in props.items():
            setattr(n, k, v)
        for k, v in (inputs or {}).items():
            self.set(n.inputs[k], v)
        return n

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.t.links.new(v, sock)
        else:
            sock.default_value = v

    def math(self, op, a, b=0.0, c=0.0):
        n = self.node("ShaderNodeMath", operation=op)
        for k, v in enumerate((a, b, c)):
            self.set(n.inputs[k], v)
        return n.outputs[0]

    def vmath(self, op, a, b=(0.0, 0.0, 0.0), scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        if scale is not None:
            self.set(n.inputs["Scale"], scale)
        return n.outputs["Value" if op in ("DOT_PRODUCT", "LENGTH") else "Vector"]

    def mix(self, fac, a, b):
        n = self.node("ShaderNodeMix", data_type="RGBA")
        self.set(n.inputs["Factor"], fac)
        self.set(n.inputs["A"], a)
        self.set(n.inputs["B"], b)
        return n.outputs["Result"]

    def smooth(self, x, lo, hi):
        n = self.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        self.set(n.inputs["Value"], x)
        self.set(n.inputs["From Min"], lo)
        self.set(n.inputs["From Max"], hi)
        return n.outputs["Result"]

    def is_(self, x, k):
        return self.math("COMPARE", x, float(k), 0.5)

    def sep(self, v):
        return self.node("ShaderNodeSeparateXYZ", {"Vector": v}).outputs


def _new_material(name, method="BLENDED", version=1):
    """(material, tree helper) to build it, or (material, None) when it is already up to date."""
    mat = bpy.data.materials.get(name)
    if mat is not None and mat.get("llb_version", 1) == version:
        return mat, None
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat["llb_version"] = version
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    mat.surface_render_method = method
    mat.use_backface_culling = False
    return mat, _Tree(mat.node_tree)


def _output(t, shader):
    t.t.links.new(shader, t.node("ShaderNodeOutputMaterial").inputs["Surface"])


def _emit_alpha(t, rgb, alpha, additive):
    emit = t.node("ShaderNodeEmission", {"Color": rgb})
    clear = t.node("ShaderNodeBsdfTransparent")
    if additive:
        # transparent + emission scaled by alpha = additive blending
        t.set(emit.inputs["Strength"], alpha)
        add = t.node("ShaderNodeAddShader")
        t.t.links.new(clear.outputs[0], add.inputs[0])
        t.t.links.new(emit.outputs[0], add.inputs[1])
        return add.outputs[0]
    mix = t.node("ShaderNodeMixShader", {"Fac": alpha})
    t.t.links.new(clear.outputs[0], mix.inputs[1])
    t.t.links.new(emit.outputs[0], mix.inputs[2])
    return mix.outputs[0]


def text_material():
    mat, t = _new_material(TEXT)
    if t is None:
        return mat
    info = t.node("ShaderNodeObjectInfo")
    # faces turned away from the view (the sides of 3D letters) get darker
    facing = t.node("ShaderNodeLayerWeight", {"Blend": 0.5})
    shade = t.node("ShaderNodeMix", {"B": (0.35, 0.35, 0.4, 1.0)}, data_type="RGBA", blend_type="MULTIPLY")
    t.set(shade.inputs["Factor"], facing.outputs["Facing"])
    t.set(shade.inputs["A"], info.outputs["Color"])
    _output(t, _emit_alpha(t, shade.outputs["Result"], info.outputs["Alpha"], False))
    return mat


def far_material():
    # opaque (dithered) so it writes depth: blended objects are sorted by their origin, and the
    # mountain / city rings have theirs at the audience's feet, so they were drawn over the text
    mat, t = _new_material(FAR, method="DITHERED", version=2)
    if t is not None:
        info = t.node("ShaderNodeObjectInfo")
        _output(t, _emit_alpha(t, info.outputs["Color"], info.outputs["Alpha"], False))
    return mat


def glow_material():
    """Soft light orb: bright where the sphere faces the view, fading to its rim; additive."""
    mat, t = _new_material(GLOW)
    if t is not None:
        info = t.node("ShaderNodeObjectInfo")
        facing = t.node("ShaderNodeLayerWeight", {"Blend": 0.5})
        core = t.math("POWER", t.math("SUBTRACT", 1.0, facing.outputs["Facing"]), 2.5)
        alpha = t.math("MULTIPLY", core, info.outputs["Alpha"])
        _output(t, _emit_alpha(t, info.outputs["Color"], t.math("MULTIPLY", alpha, 0.9), True))
    return mat


def atlas_image():
    img = bpy.data.images.get(ATLAS)
    if img is None:
        a = atlas.draw(1024)[::-1]                        # Blender images start at the bottom row
        img = bpy.data.images.new(ATLAS, 1024, 1024, alpha=True, float_buffer=False)
        img.pixels.foreach_set(np.ascontiguousarray(a, dtype=np.float32).ravel())
        img.pack()
        img.use_fake_user = False
    return img


def particle_material(additive):
    mat, t = _new_material(PARTICLE_ADD if additive else PARTICLE_ALPHA)
    if t is not None:
        tex = t.node("ShaderNodeTexImage", interpolation="Linear")
        tex.image = atlas_image()
        col = t.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=COLOR_ATTR)
        alpha = t.math("MULTIPLY", tex.outputs["Alpha"], col.outputs["Alpha"])
        _output(t, _emit_alpha(t, col.outputs["Color"], alpha, additive))
    return mat


def particle3d_material():
    mat, t = _new_material(PARTICLE_3D)
    if t is not None:
        col = t.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=COLOR_ATTR)
        facing = t.node("ShaderNodeLayerWeight", {"Blend": 0.4})
        shade = t.node("ShaderNodeMix", {"B": (0.3, 0.3, 0.35, 1.0)}, data_type="RGBA", blend_type="MULTIPLY")
        t.set(shade.inputs["Factor"], facing.outputs["Facing"])
        t.set(shade.inputs["A"], col.outputs["Color"])
        _output(t, _emit_alpha(t, shade.outputs["Result"], col.outputs["Alpha"], False))
    return mat


# ---------------- dome ----------------

def _slot_group():
    """Shader group: one background slot evaluated in a view direction (design §8.2)."""
    ng = bpy.data.node_groups.get(DOME_SLOT)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(DOME_SLOT, "ShaderNodeTree")
    for name, kind in (("Dir", "NodeSocketVector"), ("Mode", "NodeSocketFloat"), ("Top", "NodeSocketColor"),
                       ("Horizon", "NodeSocketColor"), ("Bottom", "NodeSocketColor"), ("Ink", "NodeSocketColor"),
                       ("Bands", "NodeSocketFloat"), ("Pattern", "NodeSocketFloat"), ("PScale", "NodeSocketFloat"),
                       ("Image", "NodeSocketColor")):
        ng.interface.new_socket(name, in_out="INPUT", socket_type=kind)
    ng.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    t = _Tree(ng)
    gi = t.node("NodeGroupInput").outputs
    go = t.node("NodeGroupOutput")
    x, y, z = t.sep(gi["Dir"])
    up = t.math("GREATER_THAN", z, 0.0)
    tt = t.math("SQRT", t.math("ABSOLUTE", z))
    bands = t.math("MAXIMUM", gi["Bands"], 1.0)
    tq = t.math("DIVIDE", t.math("FLOOR", t.math("MULTIPLY", tt, bands)), t.math("MAXIMUM", t.math("SUBTRACT", bands, 1.0), 1.0))
    tt = t.math("ADD", t.math("MULTIPLY", tt, t.math("SUBTRACT", 1.0, t.is_(gi["Mode"], 2))),
                t.math("MULTIPLY", t.math("MINIMUM", tq, 1.0), t.is_(gi["Mode"], 2)))
    grad = t.mix(up, t.mix(tt, gi["Horizon"], gi["Bottom"]), t.mix(tt, gi["Horizon"], gi["Top"]))
    # patterns in latitude / longitude
    lat = t.math("ARCSINE", z)
    lon = t.math("ARCTAN2", x, y)
    fu = t.math("FRACT", t.math("MULTIPLY", t.math("DIVIDE", lon, 6.2832), gi["PScale"]))
    fv = t.math("FRACT", t.math("MULTIPLY", t.math("DIVIDE", lat, 3.1416), t.math("MULTIPLY", gi["PScale"], 0.5)))
    fr = t.math("FRACT", t.math("MULTIPLY", t.math("DIVIDE", t.math("ARCCOSINE", z), 3.1416), gi["PScale"]))

    def line(f, lo, hi):
        edge = t.math("MINIMUM", f, t.math("SUBTRACT", 1.0, f))
        return t.math("SUBTRACT", 1.0, t.smooth(edge, lo, hi))
    rings = line(fr, 0.04, 0.09)
    grid = t.math("MAXIMUM", line(fu, 0.02, 0.05), line(fv, 0.02, 0.05))
    cell = t.node("ShaderNodeCombineXYZ", {"X": t.math("SUBTRACT", fu, 0.5), "Y": t.math("SUBTRACT", fv, 0.5)}).outputs[0]
    dots = t.math("SUBTRACT", 1.0, t.smooth(t.vmath("LENGTH", cell), 0.18, 0.24))
    mask = t.math("ADD", t.math("ADD", t.math("MULTIPLY", rings, t.is_(gi["Pattern"], 0)),
                                t.math("MULTIPLY", grid, t.is_(gi["Pattern"], 1))),
                  t.math("MULTIPLY", dots, t.is_(gi["Pattern"], 2)))
    patterned = t.mix(t.math("MULTIPLY", mask, 0.85), grad, gi["Ink"])
    col = t.mix(t.math("ADD", t.is_(gi["Mode"], 1), t.is_(gi["Mode"], 2)), gi["Horizon"], grad)
    col = t.mix(t.is_(gi["Mode"], 3), col, patterned)
    col = t.mix(t.is_(gi["Mode"], 4), col, gi["Image"])
    ng.links.new(col, go.inputs["Color"])
    return ng


def dome_material(panorama_path=""):
    mat, t = _new_material(DOME, method="DITHERED", version=3)
    if t is None:
        _set_panorama(mat, panorama_path)
        return mat

    def attr(name):
        """The parameter's node (output 0); created once, animated by preview/animation.py."""
        n = t.t.nodes.get(f"llb_{name}")
        if n is None:
            is_color = name.rstrip("AB") in DOME_COLORS or name in DOME_COLORS
            n = t.node("ShaderNodeRGB" if is_color else "ShaderNodeValue", name=f"llb_{name}", label=name)
        return n
    coords = t.node("ShaderNodeTexCoord")
    d = t.vmath("NORMALIZE", coords.outputs["Object"])
    env = t.node("ShaderNodeTexEnvironment", {"Vector": d}, name="LLB_Panorama", label="Panorama")
    slots = {}
    for s in "AB":
        g = t.node("ShaderNodeGroup")
        g.node_tree = _slot_group()
        t.set(g.inputs["Dir"], d)
        for p, sock in (("mode", "Mode"), ("top", "Top"), ("horizon", "Horizon"), ("bottom", "Bottom"),
                        ("ink", "Ink"), ("bands", "Bands"), ("pattern", "Pattern"), ("pscale", "PScale")):
            a = attr(p + s)
            t.set(g.inputs[sock], a.outputs[0])
        t.set(g.inputs["Image"], env.outputs["Color"])
        slots[s] = g.outputs["Color"]
    x, y, z = t.sep(d)
    nxt, prog, kind = (attr(n).outputs[0] for n in ("next", "progress", "trans"))
    q = t.math("ADD", t.math("MULTIPLY", nxt, prog), t.math("MULTIPLY", t.math("SUBTRACT", 1.0, nxt),
                                                            t.math("SUBTRACT", 1.0, prog)))
    noise = t.node("ShaderNodeTexNoise", {"Vector": d, "Scale": 4.0, "Detail": 3.0}).outputs["Fac"]
    sweeps = [t.math("MULTIPLY", t.math("SUBTRACT", 1.0, z), 0.5), t.math("MULTIPLY", t.math("ADD", 1.0, z), 0.5),
              t.math("MULTIPLY", t.math("ADD", 1.0, x), 0.5), t.math("DIVIDE", t.math("ARCCOSINE", y), 3.1416),
              t.math("MINIMUM", t.math("MAXIMUM", t.math("DIVIDE", t.math("SUBTRACT", noise, 0.3), 0.4), 0.0), 1.0)]
    w = bgs.SOFTNESS
    edge = t.math("SUBTRACT", t.math("MULTIPLY", q, 1 + 2 * w), w)
    mask = t.math("MULTIPLY", q, t.is_(kind, 0))
    for k, s in enumerate(sweeps, start=1):
        shown = t.math("SUBTRACT", 1.0, t.smooth(s, t.math("SUBTRACT", edge, w), t.math("ADD", edge, w)))
        mask = t.math("ADD", mask, t.math("MULTIPLY", shown, t.is_(kind, k)))
    w_b = t.math("ADD", t.math("MULTIPLY", nxt, mask), t.math("MULTIPLY", t.math("SUBTRACT", 1.0, nxt),
                                                              t.math("SUBTRACT", 1.0, mask)))
    col = t.mix(w_b, slots["A"], slots["B"])
    col = t.mix(attr("flash").outputs[0], col, attr("flash_color").outputs[0])
    col = t.vmath("SCALE", col, scale=attr("bright").outputs[0])
    cue = t.math("POWER", t.math("MAXIMUM", t.vmath("DOT_PRODUCT", d, attr("cue_dir").outputs[0]), 0.0), 6.0)
    lift = t.math("MULTIPLY", t.math("MULTIPLY", cue, attr("cue_amount").outputs[0]), 0.12)
    warm = t.node("ShaderNodeCombineXYZ", {"X": lift, "Y": t.math("MULTIPLY", lift, 0.95),
                                          "Z": t.math("MULTIPLY", lift, 0.85)}).outputs[0]
    col = t.vmath("ADD", col, warm)
    emit = t.node("ShaderNodeEmission", {"Color": col})
    _output(t, emit.outputs[0])
    _set_panorama(mat, panorama_path)
    return mat


def _set_panorama(mat, path):
    node = mat.node_tree.nodes.get("LLB_Panorama")
    if node is None:
        return
    img = None
    if path:
        try:
            img = bpy.data.images.load(bpy.path.abspath(path), check_existing=True)
        except RuntimeError:
            img = None
    node.image = img
