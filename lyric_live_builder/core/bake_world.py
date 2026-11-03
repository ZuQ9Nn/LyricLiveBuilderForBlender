"""Plan.world / emitters / events -> dome, far object and emitter nodes with tracks (design §8.2, §5.7).

The dome shader holds two background slots (A, B). A transition writes the incoming slot while it
is hidden, flips `next` to it and runs `progress`; the shader shows B with weight
w = m(q) if next else 1 - m(q), q = p if next else 1 - p (m = the transition's mask, 0..1).
So progress only ever ramps between 0 and 1 and nothing jumps when a transition starts."""
import numpy as np

from . import color, model, xform
from .model import MeshSource, Node, Track
from .parts import backgrounds as bgs
from .parts import particles as pts

DOME = "dome"
FAR_DISTANCE = 50.0
SLOT_PARAMS = ("mode", "top", "horizon", "bottom", "ink", "bands", "pattern", "pscale", "image")


def _const(node, prop, keys):
    """keys: [(t, tuple)] -> constant track (first key moved to 0)."""
    keys = sorted(keys, key=lambda k: k[0])
    t = np.array([0.0] + [k[0] for k in keys[1:]], dtype=np.float32)
    v = np.array([k[1] for k in keys], dtype=np.float32).reshape(len(keys), -1)
    return Track(node, prop, "constant", t, v)


def _linear(node, prop, keys):
    keys = sorted(keys, key=lambda k: k[0])
    t = np.array([k[0] for k in keys], dtype=np.float64)
    v = np.array([k[1] for k in keys], dtype=np.float64).reshape(len(keys), -1)
    t, idx = np.unique(np.round(t, 4), return_index=True)      # keys ≥ 0.1 ms apart (see bake.py)
    return Track(node, prop, "linear", t.astype(np.float32), v[idx].astype(np.float32))


def _bumps(bumps, base):
    """Piecewise-linear sum of bumps [(t0, t_peak, t1, amp)] on top of base -> [(t, value)]."""
    if not bumps:
        return [(0.0, base)]
    times = sorted({0.0} | {x for b in bumps for x in b[:3]})
    out = []
    for t in times:
        v = base
        for t0, tp, t1, amp in bumps:
            if t0 <= t <= t1:
                v += amp * ((t - t0) / max(tp - t0, 1e-6) if t < tp else (t1 - t) / max(t1 - tp, 1e-6))
        out.append((t, v))
    return out


def dome(plan, guides=()):
    """The dome node and its tracks."""
    node = Node(DOME, "Dome", "", "background", "dome", mesh=DOME, material="dome", loc=(0.0, 0.0, model.EYE_HEIGHT))
    first = bgs.slot_values(plan.world[0]["spec"])
    slots = {"A": [(0.0, first)], "B": [(0.0, first)]}
    nxt, prog, trans, flash_col = [(0.0, (0.0,))], [(0.0, 0.0)], [(0.0, (0.0,))], [(0.0, (1.0, 1.0, 1.0))]
    flashes = []
    visible = "A"
    for w in plan.world[1:]:
        t, dur = w["t"], max(w["dur"], 0.05)
        tr = bgs.TRANSITIONS[w["transition"]]
        incoming = "B" if visible == "A" else "A"
        slots[incoming].append((t, bgs.slot_values(w["spec"])))
        nxt.append((t, (1.0 if incoming == "B" else 0.0,)))
        p0, p1 = (0.0, 1.0) if incoming == "B" else (1.0, 0.0)
        prog += [(t, p0), (t + dur, p1)]
        trans.append((t, (float(tr["type"]),)))
        if tr["flash"]:
            flash_col.append((t, color.linear(tr["flash"])))
            flashes.append((t, t + dur / 2, t + dur, 0.95))
        visible = incoming
    for ev in plan.events:
        if ev["type"] == "flash":
            flash_col.append((ev["t"] - 0.05, color.linear(ev["color"])))
            flashes.append((ev["t"] - 0.05, ev["t"] + 0.06, ev["t"] + ev["dur"], ev["amp"]))
    pulses = [(e["t"], e["t"] + 0.03, e["t"] + e["dur"], e["amp"]) for e in plan.events if e["type"] == "pulse"]
    tracks = [_const(DOME, f"dome:{p}{s}", [(t, v[p]) for t, v in slots[s]]) for s in "AB" for p in SLOT_PARAMS]
    tracks += [_const(DOME, "dome:next", nxt), _linear(DOME, "dome:progress", prog), _const(DOME, "dome:trans", trans),
               _const(DOME, "dome:flash_color", _dedupe(flash_col)),
               _linear(DOME, "dome:flash", [(t, min(1.0, v)) for t, v in _bumps(flashes, 0.0)]),
               _linear(DOME, "dome:bright", _bumps(pulses, 1.0))]
    cue_dir = [(0.0, (0.0, 1.0, 0.0))] + [(g["t_on"], tuple(g["to"])) for g in guides if "dome" in g["kinds"]]
    cue = [(g["t_on"], g["t_hit"], g["t_hit"] + 0.8, 1.0) for g in guides if "dome" in g["kinds"]]
    tracks += [_const(DOME, "dome:cue_dir", _dedupe(cue_dir)), _linear(DOME, "dome:cue_amount", _bumps(cue, 0.0))]
    return node, tracks


def _dedupe(keys):
    """Constant keys: later keys at the same time win."""
    out = {}
    for t, v in sorted(keys, key=lambda k: k[0]):
        out[round(t, 4)] = v
    return sorted(out.items())


def far_objects(plan):
    """Far objects of every background, fading with the transitions that bring and remove them."""
    nodes, tracks, meshes = [], [], {}
    for k, w in enumerate(plan.world):
        t_in, d_in = w["t"], w["dur"]
        nxt = plan.world[k + 1] if k + 1 < len(plan.world) else None
        t_out, d_out = (nxt["t"], nxt["dur"]) if nxt else (plan.duration + 1.0, 0.0)
        for j, f in enumerate(w["spec"]["far"]):
            nid = f"far{k:02d}_{j}"
            key = f"far:{f['kind']}"
            meshes.setdefault(key, MeshSource(key, "far", {"kind": f["kind"]}))
            if f["kind"] in ("moon", "sun"):
                az, el = np.radians(f["az"]), np.radians(f["el"])
                loc = tuple(np.array([0.0, 0.0, model.EYE_HEIGHT]) + FAR_DISTANCE * xform.direction(az, el))
                rot, scale = tuple(xform.facing(az, el)), (f["size"],) * 3
            else:
                loc, rot, scale = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
            rgb = color.linear(f["color"])
            nodes.append(Node(nid, f"Far_{f['kind']}", "", "background", "far", mesh=key, material="far",
                              loc=loc, rot=rot, scale=scale, color=rgb + (1.0,), default_active=False))
            on, off = t_in, t_out + d_out
            act = [(0.0, (0.0,)), (on, (1.0,)), (off, (0.0,))] if on > 0 else [(0.0, (1.0,)), (off, (0.0,))]
            tracks.append(_const(nid, "active", act))
            alpha = [(t_in, 0.0 if d_in else 1.0), (t_in + d_in, 1.0), (t_out, 1.0), (t_out + max(d_out, 0.01), 0.0)]
            tracks.append(_linear(nid, "color", [(t, rgb + (a,)) for t, a in alpha]))
    return nodes, tracks, meshes


def emitters(plan):
    """One node per particle emitter; the spec travels with the baked scene (preview / export)."""
    nodes, tracks, specs = [], [], []
    for k, spec in enumerate(plan.emitters):
        nid = f"emit{k:03d}"
        p = spec["preset"]
        tail = spec["end"] + max(spec["fade_out"], 0.0)
        on = spec["start"]
        nodes.append(Node(nid, f"Particles_{spec['key']}", "", "particles", "emitter",
                          material="particle3d" if p["shape"] in pts.SHAPES_3D else "particle", default_active=False))
        act = [(0.0, (0.0,)), (on, (1.0,)), (tail, (0.0,))] if on > 0 else [(0.0, (1.0,)), (tail, (0.0,))]
        tracks.append(_const(nid, "active", act))
        env = [(spec["start"], 0.0), (spec["start"] + spec["fade_in"], 1.0), (spec["end"], 1.0), (tail, 0.0)]
        tracks.append(_linear(nid, "color", [(t, (1.0, 1.0, 1.0, a)) for t, a in env]))
        rate = [(t, p.get("rate", 0.0) * v) for t, v in (spec["intensity"] or [(spec["start"], 1.0)])]
        tracks.append(_linear(nid, "emit_rate", rate + [(spec["end"], rate[-1][1]), (spec["end"] + 0.01, 0.0)]))
        specs.append({"node": nid, "spec": spec})
    return nodes, tracks, specs
