"""Rough budget of an export (design §11.4, spec §10.3): triangles on stage, particles alive, materials."""
import json

import numpy as np

from . import manifest, particles_unity

DEFAULT_LIMITS = {"letter_flat": 300, "letter_solid": 1000, "tris": 100_000, "particles": 3000, "materials": 16}


def _active_at(track, default, t):
    if track is None:
        return np.full(t.shape, bool(default))
    k = np.clip(np.searchsorted(track.times, t, side="right") - 1, 0, None)
    return track.values[k, 0] > 0.5


def check(baked, tris, mobile=True, particle_ratio=1.0, limits=None, step=0.5):
    """tris: {mesh key: triangles} (export_unity.exporter.pack_meshes). Returns {item: (value, limit, detail)}."""
    limits = dict(DEFAULT_LIMITS, **(limits or {}))
    particle_ratio = particle_ratio if mobile else 1.0
    t = np.arange(0.0, max(baked.duration, step), step)
    active = {tr.node: tr for tr in baked.tracks if tr.prop == "active"}
    nodes = {n.id: n for n in baked.nodes}

    def shown(nid):
        n, on = nodes[nid], None
        while n is not None:
            a = _active_at(active.get(n.id), n.default_active, t)
            on = a if on is None else on & a
            n = nodes.get(n.parent)
        return on

    on_stage = np.zeros(t.shape)
    for n in baked.nodes:
        if n.mesh in tris:
            on_stage += shown(n.id) * tris[n.mesh]
    alive = np.zeros(t.shape)
    for e in baked.emitters:
        spec = e["spec"]
        if spec["preset"]["emitter"] == "burst":
            b = spec["preset"]["burst"]
            span = b["life"][1] + (b["sub"]["life"] if b.get("sub") else 0.0)
            per = particles_unity.burst(spec, spec["bursts"][0], particle_ratio)[0]["burst"] if spec["bursts"] else 0
            per *= 1 + (b["sub"]["count"] if b.get("sub") else 0)
            for ev in spec["bursts"]:
                alive += ((t >= ev["t"]) & (t < ev["t"] + span)) * per
        else:
            cap = sum(d["max"] for d in particles_unity.continuous(spec, particle_ratio))
            alive += shown(e["node"]) * cap
    b = manifest.Builder(baked, mobile, particle_ratio)
    b.build_nodes([])
    combos = {(d["renderer"]["blend"], d["renderer"]["mode"] == "Mesh")
              for d in (json.loads(n["particles"]) for n in b.nodes if n["particles"])}
    letters = {"flat": 0, "solid": 0}
    for key, src in baked.meshes.items():
        if key in tris and src.kind in ("glyph2d", "glyph3d"):
            kind = "solid" if src.kind == "glyph3d" else "flat"
            letters[kind] = max(letters[kind], tris[key])
    i, j = int(on_stage.argmax()), int(alive.argmax())
    return {
        "letter_flat": (letters["flat"], limits["letter_flat"], ""),
        "letter_solid": (letters["solid"], limits["letter_solid"], ""),
        "tris": (int(on_stage[i]), limits["tris"], f"{t[i]:.1f}"),
        "particles": (int(alive[j]), limits["particles"], f"{t[j]:.1f}"),
        "materials": (len(b.materials) + len(combos), limits["materials"], ""),
    }

