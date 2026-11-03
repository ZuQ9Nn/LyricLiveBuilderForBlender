"""Public functions of mesh_optimizer (design §11.1). The LyricLive add-on calls only these; the
package never imports the add-on, so it can also be installed on its own (ui.py)."""
from dataclasses import dataclass, field

import bmesh

from . import decimate as _decimate
from . import merge as _merge
from . import retopo as _retopo

MAX_ANGLE = 3.0                      # above this, Mincho faces lose shape (S0-09: up to 8 % area error at 5°)
DEFAULTS = {"normal": {"resolution": 6, "angle": 1.0}, "mobile": {"resolution": 4, "angle": 1.0}}
LIMITS = {"flat": 300, "solid": 1000}            # triangles per letter on mobile (spec §10.3)


@dataclass
class RetopoReport:
    tris_before: int
    tris_after: int
    loops_before: int
    loops_after: int
    area_error: float                # relative change of the face area

    @property
    def holes_kept(self):
        return self.loops_after == self.loops_before


@dataclass
class FitReport:
    resolution: int                  # curve resolution finally used
    tris: int
    holes_kept: bool
    area_error: float
    decimated: bool                  # still over the limit at the lowest resolution: collapsed


@dataclass
class PaletteResult:
    material: object
    colors: list = field(default_factory=list)


def optimize_text_curve(curve_obj, *, resolution=4):
    """Lower a text object's curve resolution before it becomes a mesh (fewer outline vertices)."""
    curve_obj.data.resolution_u = max(1, int(resolution))


def retopo_flat_text_mesh(mesh, *, dissolve_angle_deg=1.0, merge_dist=1e-5, depth=0.0):
    """Clean a text mesh in place (flat or extruded): fewer, better shaped triangles, holes intact.
    depth > 0 extrudes a flat mesh afterwards, so the sides are not split by the old triangulation."""
    angle = min(float(dissolve_angle_deg), MAX_ANGLE)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()
    before = (len(bm.calc_loop_triangles()), _retopo.outline_loops(bm), _retopo.area(bm))
    _retopo.clean(bm, angle, merge_dist)
    after_loops, after_area = _retopo.outline_loops(bm), _retopo.area(bm)
    if depth > 0:
        _retopo.extrude(bm, depth)
    tris = len(bm.calc_loop_triangles())
    bm.to_mesh(mesh)
    bm.free()
    err = abs(after_area - before[2]) / before[2] if before[2] else 0.0
    return RetopoReport(before[0], tris, before[1], after_loops, err)


def fit_text_mesh(make_mesh, *, max_tris, resolutions=(4, 3, 2), dissolve_angle_deg=1.0, depth=0.0):
    """A letter under a triangle budget: clean it at each resolution in turn (complex kanji in a Mincho
    face need fewer outline points), and collapse it only if the lowest resolution is still over.
    make_mesh(resolution) -> a new mesh. Returns (mesh, FitReport); the meshes not kept are removed."""
    import bpy
    me = rep = None
    for res in resolutions:
        if me is not None:
            bpy.data.meshes.remove(me)
        me = make_mesh(res)
        rep = retopo_flat_text_mesh(me, dissolve_angle_deg=dissolve_angle_deg, depth=depth)
        if rep.tris_after <= max_tris:
            return me, FitReport(res, rep.tris_after, rep.holes_kept, rep.area_error, False)
    tris = decimate(me, target_tris=max_tris, planar_angle_deg=dissolve_angle_deg)
    holes = rep.holes_kept
    if depth <= 0:                                        # a collapse may close a hole: look again
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.edges.ensure_lookup_table()
        holes = _retopo.outline_loops(bm) == rep.loops_before
        bm.free()
    return me, FitReport(resolutions[-1], tris, holes, rep.area_error, True)


def extrude_flat_mesh(mesh, *, depth, bevel=0.0):
    """Thickness for a flat mesh, behind its faces (bevel is not supported: mobile text has none)."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    _retopo.extrude(bm, depth)
    bm.to_mesh(mesh)
    bm.free()


def decimate(mesh, *, ratio=None, target_tris=None, planar_angle_deg=2.0):
    """Planar dissolve, then Collapse down to a ratio or a triangle count. Returns the triangles left."""
    _decimate.planar(mesh, planar_angle_deg)
    tris = _decimate.triangles(mesh)
    if target_tris and tris > target_tris:
        ratio = target_tris / tris
    if ratio and ratio < 1.0:
        _decimate.collapse(mesh, ratio)
    return _decimate.triangles(mesh)


def merge_static_objects(objects, *, by_material=True):
    """Join objects that never move apart. Returns the new objects (one per first material when
    by_material, else one); the originals are left for the caller."""
    obs = [o for o in objects if o.type == "MESH"]
    if not by_material:
        return [_merge.join(obs)] if obs else []
    groups = {}
    for o in obs:
        key = o.data.materials[0].name if o.data.materials and o.data.materials[0] else ""
        groups.setdefault(key, []).append(o)
    return [_merge.join(g, name=f"Merged_{k or 'NoMaterial'}") for k, g in groups.items()]


def bake_palette_material(objects, *, max_colors=64):
    """Replace colour-only materials with one material reading a per-face colour attribute."""
    obs = [o for o in objects if o.type == "MESH"]
    colors = {tuple(round(c, 4) for c in _merge.base_color(m)) for o in obs for m in o.data.materials}
    if len(colors) > max_colors:
        raise ValueError(f"{len(colors)} colours, more than {max_colors}")
    mat = _merge.palette_material()
    for o in obs:
        _merge.paint_and_assign(o, mat)
    return PaletteResult(mat, sorted(colors))
