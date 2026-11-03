"""Text retopology (design §11.2, prototype S0-09): merge close vertices, dissolve coplanar faces
(limited dissolve keeps every hole and stroke), then re-triangulate with BEAUTY."""
import math

import bmesh


def outline_loops(bm):
    """Number of closed boundary loops (outer contours + holes) of a flat mesh."""
    adj = {}
    for e in bm.edges:
        if len(e.link_faces) == 1:
            a, b = e.verts
            adj.setdefault(a.index, []).append(b.index)
            adj.setdefault(b.index, []).append(a.index)
    seen, loops = set(), 0
    for start in adj:
        if start in seen:
            continue
        loops += 1
        stack = [start]
        while stack:
            v = stack.pop()
            if v not in seen:
                seen.add(v)
                stack.extend(adj[v])
    return loops


def area(bm):
    return sum(f.calc_area() for f in bm.faces)


def clean(bm, angle_deg=1.0, merge_dist=1e-5):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)
    angle = math.radians(max(angle_deg, 0.01))
    bmesh.ops.dissolve_limit(bm, angle_limit=angle, use_dissolve_boundaries=False, verts=bm.verts, edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.verts.index_update()
    bm.edges.index_update()


def extrude(bm, depth):
    """Give a flat mesh thickness behind its faces (the side walls stay unsplit)."""
    if not bm.faces or depth <= 0:
        return
    bm.faces.ensure_lookup_table()
    n = bm.faces[0].normal.copy()
    geom = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))["geom"]
    moved = [g for g in geom if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=-n * depth)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
