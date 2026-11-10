"""BakedScene -> manifest.json (design §9.2): nodes, materials, particle systems and per-section clips.

Clips are cut per section × category and are self-contained (design §10.5): a Timeline animation
track puts every property its playing clip does not animate back to the prefab's default, so each
clip carries every track of every node that is on stage at any time in its section."""
import json

import numpy as np

from . import convert, particles_unity

FORMAT, VERSION = "llb-manifest", 1
CATEGORIES = ("text", "particles", "background", "gimmicks")
CATEGORY_OF = {"guide": "text"}
DOME_PROPS = {"next": "_Next", "progress": "_Progress", "trans": "_Trans", "flash": "_Flash",
              "flash_color": "_FlashColor", "bright": "_Bright", "cue_dir": "_CueDir", "cue_amount": "_CueAmount"}
DOME_SLOT = {"mode": "_Mode", "top": "_Top", "horizon": "_Horizon", "bottom": "_Bottom", "ink": "_Ink",
             "bands": "_Bands", "pattern": "_Pattern", "pscale": "_PScale"}
COLOR_PROPS = ("_Top", "_Horizon", "_Bottom", "_Ink", "_FlashColor")
XYZ, XYZW, RGBA = ["x", "y", "z"], ["x", "y", "z", "w"], ["r", "g", "b", "a"]


def dome_property(param):
    """'topA' -> '_TopA'; None for parameters the Unity dome does not have (the image index)."""
    if param in DOME_PROPS:
        return DOME_PROPS[param]
    base, slot = param[:-1], param[-1]
    return DOME_SLOT[base] + slot if base in DOME_SLOT and slot in "AB" else None


def binding(node_kind, prop, values):
    """(type, attribute, fields, converted values) for one baked track, or None to skip it."""
    v = np.asarray(values, dtype=np.float64)
    if prop == "active":
        return "GameObject", "m_IsActive", [""], v[:, :1]
    if prop == "location":
        return "Transform", "m_LocalPosition", XYZ, convert.pos(v)
    if prop == "rotation":
        return "Transform", "m_LocalRotation", XYZW, convert.quat(v)
    if prop == "scale":
        return "Transform", "m_LocalScale", XYZ, convert.scale(v)
    if prop == "color" and node_kind == "glyph_tmp":
        return "TextMeshPro", "m_fontColor", RGBA, convert.rgba(v)
    if prop == "color":
        renderer = "ParticleSystemRenderer" if node_kind == "emitter" else "MeshRenderer"
        return renderer, "material._Color", RGBA, convert.rgba(v)
    if prop == "emit_rate":
        return "ParticleSystem", "EmissionModule.rateOverTime.scalar", [""], v[:, :1]
    if prop == "line_state":
        return "MeshRenderer", "material._LineState", XYZW, v[:, :4]
    if prop == "mask":                             # glyph coordinates already match Unity's (x, up): no conversion
        return "MeshRenderer", "material._Mask", [""], v[:, :1]
    if prop in ("mask_shape", "mask_box"):
        return "MeshRenderer", "material._" + ("MaskShape" if prop == "mask_shape" else "MaskBox"), XYZW, v[:, :4]
    if prop.startswith("dome:"):
        name = dome_property(prop[5:])
        if name is None:
            return None
        if name == "_CueDir":
            return "MeshRenderer", "material." + name, XYZ, convert.pos(v)
        if name in COLOR_PROPS or name[:-1] in COLOR_PROPS:
            return "MeshRenderer", "material." + name, RGBA[:3], convert.srgb(v)
        return "MeshRenderer", "material." + name, [""], v[:, :1]
    raise KeyError(prop)


# ---------------- nodes and materials ----------------

def _hex(rgba):
    return "".join(f"{int(round(x * 255)):02x}" for x in rgba)


class Builder:
    def __init__(self, baked, mobile=False, particle_ratio=1.0, tmp_fonts=None):
        self.baked = baked
        self.tmp_fonts = tmp_fonts or {}                  # glyph mesh key -> font key (TextMesh Pro letters)
        self.mobile = mobile
        self.ratio = particle_ratio if mobile else 1.0
        self.nodes, self.ids, self.materials = [], {}, {}
        self.extra_tracks = []                          # (node id, kind, prop, interp, times, values)
        self.kind_of = {}
        self.names = {}                                   # parent id -> names taken

    def material(self, shader, color=None, params=None, key=None):
        rgba = [float(x) for x in convert.rgba(color)] if color is not None else [1.0, 1.0, 1.0, 1.0]
        key = key or (f"{shader}_{_hex(rgba)}" if color is not None else shader)
        if key not in self.materials:
            self.materials[key] = {"key": key, "shader": shader, "color": rgba, "params": params or []}
        return key

    def _unique(self, name, parent):
        """Animation paths are names: siblings must differ (a line may hold the same character twice)."""
        name = (name or "node").replace("/", "／")
        taken = self.names.setdefault(parent, set())
        out, k = name, 1
        while out in taken:
            k += 1
            out = f"{name}_{k}"
        taken.add(out)
        return out

    def add(self, nid, name, parent, category, kind, mesh="", material="", p=(0, 0, 0), r=(1, 0, 0, 0),
            s=(1, 1, 1), active=True, particles=""):
        name = self._unique(name, self.ids.get(parent, -1))
        self.ids[nid] = len(self.nodes)
        self.kind_of[nid] = kind
        self.nodes.append({"id": len(self.nodes), "name": name, "parent": self.ids.get(parent, -1), "tmp": "", "tmpFont": "",
                           "category": CATEGORY_OF.get(category, category), "kind": kind, "mesh": mesh,
                           "material": material, "p": [float(x) for x in convert.pos(p)],
                           "r": [float(x) for x in convert.quat(r)], "s": [float(x) for x in convert.scale(s)],
                           "active": bool(active), "particles": particles})

    def build_nodes(self, dome_params):
        specs = {e["node"]: e["spec"] for e in self.baked.emitters}
        tracks = {}
        for tr in self.baked.tracks:
            tracks.setdefault(tr.node, []).append(tr)
        for n in self.baked.nodes:
            mat = ""
            if n.kind == "glyph" and n.mesh in self.tmp_fonts:
                self.add(n.id, n.name, n.parent, n.category, "glyph_tmp", "", "", n.loc, n.rot, n.scale, n.default_active)
                node = self.nodes[-1]
                node["tmp"], node["tmpFont"] = self.baked.meshes[n.mesh].args["char"], self.tmp_fonts[n.mesh]
                if not any(t.prop == "color" for t in tracks.get(n.id, [])):
                    self.extra_tracks.append((n.id, "color", "constant", np.array([0.0]), np.array([list(n.color)])))
                continue
            if n.material in ("text", "gimmick") and self.mobile:
                # one text material (a palette, design §11): every letter then carries its colour curve
                mat = self.material(n.material)
                if not any(t.prop == "color" for t in tracks.get(n.id, [])):
                    self.extra_tracks.append((n.id, "color", "constant", np.array([0.0]), np.array([list(n.color)])))
            elif n.material in ("text", "gimmick"):
                mat = self.material(n.material, n.color[:3] + (1.0,))
            elif n.material == "text_line":
                mat = self.material("text_vc")
            elif n.material == "far":
                mat = self.material("far", n.color[:3] + (1.0,))
            elif n.material == "glow":
                mat = self.material("glow")
            elif n.material == "line_fx":
                mat = self.material("line_fx")
            elif n.material == "dome":
                mat = self.material("dome", params=dome_params)
            if n.kind != "emitter":
                self.add(n.id, n.name, n.parent, n.category, n.kind, n.mesh, mat, n.loc, n.rot, n.scale, n.default_active)
                continue
            spec = specs[n.id]
            if spec["preset"]["emitter"] == "lines":         # a mesh and its own material (design §8.1)
                mat = self.material("line", params=particles_unity.line_params(spec["preset"]), key=f"line_{spec['key']}")
                self.add(n.id, n.name, n.parent, n.category, "lines", particles_unity.line_key(n.id), mat,
                         active=n.default_active)
                continue
            if spec["preset"]["emitter"] == "burst":
                self.add(n.id, n.name, n.parent, n.category, "emitter_group", active=n.default_active)
                for k, ev in enumerate(spec["bursts"]):
                    d, origin, span = particles_unity.burst(spec, ev, self.ratio)
                    cid = f"{n.id}_b{k}"
                    self.add(cid, f"Burst_{k:02d}", n.id, n.category, "particle_system", p=convert.pos(origin),
                             active=False, particles=json.dumps(d))
                    t = np.array([0.0, ev["t"], ev["t"] + span + 0.1])
                    self.extra_tracks.append((cid, "active", "constant", t, np.array([[0.0], [1.0], [0.0]])))
                continue
            systems = particles_unity.continuous(spec, self.ratio)
            if len(systems) == 1:
                self.add(n.id, n.name, n.parent, n.category, "emitter", active=n.default_active,
                         particles=json.dumps(systems[0]))
                continue
            self.add(n.id, n.name, n.parent, n.category, "emitter_group", active=n.default_active)
            share = 1.0 / len(systems)
            for k, d in enumerate(systems):
                cid = f"{n.id}_s{k}"
                self.add(cid, f"System_{k}", n.id, n.category, "emitter", particles=json.dumps(d))
                for tr in tracks.get(n.id, []):
                    if tr.prop in ("color", "emit_rate"):
                        vals = tr.values * (share if tr.prop == "emit_rate" else 1.0)
                        self.extra_tracks.append((cid, tr.prop, tr.interp, tr.times, vals))


# ---------------- clips ----------------

def _value_at(times, values, interp, t):
    if interp == "constant":
        k = max(int(np.searchsorted(times, t, side="right")) - 1, 0)
        return values[k]
    return np.array([np.interp(t, times, values[:, c]) for c in range(values.shape[1])])


def _window(times, values, interp, s0, s1):
    """Keys of a track inside [s0, s1], with exact values at both ends, times from 0."""
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64).reshape(len(times), -1)
    inside = (times > s0 + 1e-6) & (times < s1 - 1e-6)
    t = np.concatenate([[s0], times[inside]])
    v = np.concatenate([[_value_at(times, values, interp, s0)], values[inside]])
    if interp != "constant":
        t = np.append(t, s1)
        v = np.vstack([v, _value_at(times, values, interp, s1)])
    return np.round(t - s0, 4), v


def _on_stage(active, default, s0, s1):
    """Is the node shown at any time in [s0, s1)?"""
    if active is None:
        return default
    times, values = np.asarray(active[0]), np.asarray(active[1])[:, 0]
    if _value_at(times, values[:, None], "constant", s0)[0] > 0.5:
        return True
    inside = (times >= s0) & (times < s1)
    return bool((values[inside] > 0.5).any())


def clips(builder, sections):
    by_node = {}
    for tr in builder.baked.tracks:
        if tr.node in builder.ids:
            by_node.setdefault(tr.node, []).append((tr.prop, tr.interp, tr.times, tr.values))
    for nid, prop, interp, times, values in builder.extra_tracks:
        by_node.setdefault(nid, []).append((prop, interp, times, values))
    out = []
    for si, (s0, s1) in enumerate(sections):
        per_cat = {c: [] for c in CATEGORIES}
        for nid, trs in by_node.items():
            node = builder.nodes[builder.ids[nid]]
            active = next(((t, v) for p, _, t, v in trs if p == "active"), None)
            if not _on_stage(active, node["active"], s0, s1):
                continue
            kind = builder.kind_of[nid]
            for prop, interp, times, values in trs:
                if kind == "emitter_group" and prop in ("color", "emit_rate"):
                    continue                            # carried by the systems below the group
                if prop == "emit_rate":
                    values = np.asarray(values) * builder.ratio
                b = binding(kind, prop, values)
                if b is None:
                    continue
                typ, attr, fields, conv = b
                t, v = _window(times, conv, interp, s0, s1)
                per_cat[node["category"]].append({
                    "node": node["id"], "type": typ, "attr": attr, "fields": fields,
                    "interp": 1 if interp == "constant" else 0,
                    "times": [float(x) for x in t], "values": [round(float(x), 5) for x in v.reshape(-1)]})
        for cat in CATEGORIES:
            out.append({"section": si, "category": cat, "curves": per_cat[cat]})
    return out


def guides(builder):
    """Gaze-guide events for the Udon version (design §10.7), the line's position in Unity space."""
    return [{"node": builder.ids[g["node"]], "tOn": float(g["t_on"]), "tHit": float(g["t_hit"]),
             "target": [float(x) for x in convert.pos(g["target"])], "motes": g["motes"]}
            for g in builder.baked.guides if g.get("node") in builder.ids]


def build(baked, plan, sections, mesh_entries, song, options, dome_params, fonts=None, tmp_fonts=None):
    """sections: [{index, label, kind, start, end}]; fonts: [{key, file, chars}] for TextMesh Pro;
    tmp_fonts: {glyph mesh key: font key}. Returns the manifest dict."""
    b = Builder(baked, bool(options.get("mobile")), float(options.get("particleRatio", 1.0)), tmp_fonts)
    b.build_nodes(dome_params)
    return {
        "format": FORMAT, "version": VERSION, "generator": options.pop("generator", ""),
        "song": song, "options": options, "sections": sections, "meshes": mesh_entries,
        "materials": list(b.materials.values()), "nodes": b.nodes, "fonts": fonts or [], "guides": guides(b),
        "clips": clips(b, [(s["start"], s["end"]) for s in sections]),
    }
