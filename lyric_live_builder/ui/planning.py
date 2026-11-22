"""Glue between the scene properties and the planner: おまかせ state, settings, locks, preview build."""
import json
import os
import time

import bpy

from .. import prefs
from ..core import audio, bake, color, gimmick_shapes, model, omakase, planner, registry, synonyms, world
from ..core.parts import backgrounds as bgs
from ..core.parts import gimmicks
from ..core.parts import particles as pts
from ..preview import gimmick_assets
from ..preview import scene as preview_scene
from . import project

AUTO = "AUTO"
HISTORY_MAX = 30
FX_FLOATS = ("motion", "particles", "decor", "density", "world_switch", "guide", "gimmick")


# ---------------- parts switched in the effects panel ----------------

def part_catalog():
    """(kind, key, label) of everything that can be switched off."""
    out = []
    for kind in ("layout", "enter", "hold", "exit"):
        out += [(kind, p.key, p.name) for p in registry.parts(kind)]
    out += [("particle", k, pts.PRESETS[k]["name"]) for k in pts.AMBIENT]
    out += [("background", k, bgs.PRESETS[k]["name"]) for k in bgs.ORDER]
    out += [("transition", k, bgs.TRANSITIONS[k]["name"]) for k in bgs.TRANSITION_ORDER]
    out += [("gimmick", k, v[0]) for k, v in gimmick_shapes.SHAPES.items()]
    out += [("show", k, gimmicks.SHOWS[k]["name"]) for k in gimmicks.SHOW_ORDER]
    return out


def sync_parts(proj):
    cat = part_catalog()
    if [(p.kind, p.key) for p in proj.parts] == [(k, key) for k, key, _ in cat]:
        return
    was = {(p.kind, p.key): p.enabled for p in proj.parts}
    proj.parts.clear()
    for kind, key, label in cat:
        item = proj.parts.add()
        item.kind, item.key, item.label = kind, key, label
        item.enabled = was.get((kind, key), True)


def disabled(proj):
    out = {}
    for p in proj.parts:
        if not p.enabled:
            out.setdefault(p.kind, []).append(p.key)
    return out


# ---------------- おまかせ state <-> properties ----------------

def state(proj):
    fx = {k: round(getattr(proj.fx, k), 3) for k in FX_FLOATS}
    fx["koma"] = int(proj.fx.koma)
    fx["flash"] = bool(proj.fx.flash)
    fx["spectrum"] = proj.fx.spectrum
    accent = color.to_hex(*(c * 255 for c in proj.accent)) if proj.use_accent else ""
    offsets = {str(k): v for k, v in enumerate(proj.stage_offsets) if v}
    return {"mood": proj.mood, "style": proj.style, "fx": fx, "disabled": disabled(proj), "accent": accent,
            "seed": proj.seed, "stage_offsets": offsets}


def apply_state(proj, st):
    proj.mood, proj.style = st["mood"], st["style"]
    for k in FX_FLOATS:
        if k in st["fx"]:
            setattr(proj.fx, k, st["fx"][k])
    proj.fx.koma = str(int(st["fx"].get("koma", 0)))
    proj.fx.flash = bool(st["fx"].get("flash", True))
    proj.fx.spectrum = st["fx"].get("spectrum", model.FX_DEFAULTS["spectrum"])
    proj.use_accent = bool(st["accent"])
    if st["accent"]:
        proj.accent = tuple(v / 255 for v in color.rgb(st["accent"]))
    proj.seed = int(st["seed"])
    offsets = [0] * len(proj.stage_offsets)
    for k, v in (st.get("stage_offsets") or {}).items():
        offsets[int(k)] = v
    proj.stage_offsets = offsets
    sync_parts(proj)
    off = st.get("disabled") or {}
    for p in proj.parts:
        p.enabled = p.key not in off.get(p.kind, ())


def push_history(proj, st):
    """Drop the proposals after the current one, add this one, keep the last HISTORY_MAX."""
    while len(proj.history) > proj.history_index + 1:
        proj.history.remove(len(proj.history) - 1)
    item = proj.history.add()
    item.data = json.dumps(st, sort_keys=True)
    while len(proj.history) > HISTORY_MAX:
        proj.history.remove(0)
    proj.history_index = len(proj.history) - 1


def history_state(proj, index):
    return json.loads(proj.history[index].data)


# ---------------- plan ----------------

def settings(proj, st=None):
    info = project.audio_info(proj)
    beats = audio.beat_grid(proj.bpm, proj.beat_offset, proj.duration) if proj.bpm > 0 else (info.beats if info else None)
    pano = bool(proj.panorama_path) and os.path.isfile(bpy.path.abspath(proj.panorama_path))
    p = prefs.get(bpy.context)
    return omakase.settings(st or state(proj), energy=info.energy if info else None,
                            energy_rate=info.energy_rate if info else 50.0, beats=beats, panorama=pano,
                            spectrum=info.spectrum if info else None, user_assets=gimmick_assets.assets(),
                            user_words=synonyms.parse_user(p.gimmick_words) if p else {},
                            **project.song_card(proj))


def make_plan(proj, snap=None):
    """snap: the trial's saved state (Before); None = the settings now."""
    sync_parts(proj)
    st = snap["state"] if snap else None
    return planner.plan(project.line_inputs(proj, snap), project.section_inputs(proj, snap), proj.duration,
                        st["seed"] if st else proj.seed, bpm=proj.bpm, settings=settings(proj, st))


_summary = {"key": None, "value": None}


def _summaries(proj):
    """(world.section_summary, world.line_summary) for the panels, reused while their inputs stay the same
    (a draw must stay cheap)."""
    secs = project.section_inputs(proj)
    key = json.dumps([state(proj), [list(map(str, (s.start, s.end, s.kind, s.particle, s.particle2, s.background, s.transition)))
                                    for s in secs],
                      [(ln.start, ln.end, ln.section_index, ln.background, ln.transition, ln.particle, ln.text)
                       for ln in proj.lines], project.lyrics_source(proj), proj.duration, proj.panorama_path],
                     sort_keys=True)
    if key != _summary["key"]:
        if secs:
            ins, st = project.line_inputs(proj), settings(proj)
            _summary["value"] = (world.section_summary(secs, ins, proj.seed, st),
                                 world.line_summary(secs, ins, proj.seed, st))
        else:
            _summary["value"] = ([], [])
        _summary["key"] = key
    return _summary["value"]


def section_summary(proj):
    return _summaries(proj)[0]


def line_summary(proj):
    return _summaries(proj)[1]


def build_preview(context):
    """Plan, bake and build the preview. Returns (characters, seconds); raises ValueError on bad input."""
    from . import trial
    scene = context.scene
    proj = scene.llb
    if not project.has_any_font(proj):
        raise ValueError("Set at least the Body font")
    t0 = time.perf_counter()
    wm = context.window_manager
    wm.progress_begin(0, 3)
    try:
        plan = make_plan(proj)
        wm.progress_update(1)
        baked = bake.bake(plan, project.metrics(proj))
        wm.progress_update(2)
        obs = preview_scene.build(scene, baked, lambda role: project.font_paths(proj, role),
                                  panorama=proj.panorama_path)
    finally:
        wm.progress_end()
    trial.built(scene)
    n = sum(1 for nid, ob in obs.items() if nid.startswith("line") and ob.type == "MESH")
    return n, time.perf_counter() - t0


# ---------------- locks ----------------

LINE_LOCK_FIELDS = ("layout", "enter", "hold", "exit", "persist", "gimmick", "gimmick_show")


def lock_line(proj, index, plan=None):
    """Fill the line's automatic fields with what the planner chose now, so later rolls keep them."""
    ln = proj.lines[index]
    plan = plan or make_plan(proj)
    lp = next(x for x in plan.lines if x.index == index)
    chosen = {"layout": lp.layout, "enter": lp.enter, "hold": lp.hold, "exit": lp.exit,
              "persist": "section" if lp.persist else "next"}
    g = next((x for x in plan.gimmicks if x["line"] == index), None)
    if g is None:
        chosen.update(gimmick="none", gimmick_show=AUTO)
    else:                                                     # a user's tag is no item: it stays with the lyrics
        chosen.update(gimmick={"builtin": g["tag"], "emblem": "emblem"}.get(g["source"], AUTO), gimmick_show=g["show"])
    frozen = []
    for f in LINE_LOCK_FIELDS:
        if getattr(ln, f) == AUTO:
            setattr(ln, f, chosen[f])
            frozen.append(f)
    ln.lock_frozen = json.dumps(frozen)
    ln.lock_cuts = json.dumps(_cut_specs(lp))
    ln.locked = True


def _cut_specs(lp):
    """Each cut's parts and look seed, as LineInput.cut_specs takes them."""
    return [{"layout": c.layout, "enter": c.enter, "hold": c.hold, "exit": c.exit, "seed": int(c.seed)}
            for c in lp.cuts or ()]


# copy / paste of a line's effects (spec §6.2): what the planner chose, as fixed values
COPY_FIELDS = ("is_3d", "depth", "bevel", "layout", "enter", "hold", "exit", "cuts", "persist",
               "guide", "gimmick", "gimmick_show", "gimmick_word", "particle", "background", "transition")


def _chosen(proj, ln, lp, plan, st):
    """The line's effects with every automatic choice filled in with what the planner picks now."""
    index = lp.index
    fields = {f: getattr(ln, f) for f in COPY_FIELDS}
    fields.update(layout=lp.layout, enter=lp.enter, hold=lp.hold, exit=lp.exit,
                  persist="section" if lp.persist else "next", cuts=str(len(lp.cuts)) if lp.cuts else "1")
    g = next((x for x in plan.gimmicks if x["line"] == index), None)
    if g is None:
        fields.update(gimmick="none", gimmick_show=AUTO)
    elif g["source"] in ("builtin", "emblem"):             # a user's tag is no item: it stays with the lyrics
        fields.update(gimmick=g["tag"] if g["source"] == "builtin" else "emblem", gimmick_show=g["show"],
                      gimmick_word=g["word"] if g["source"] == "emblem" else ln.gimmick_word)
    if ln.particle == world.LYRIC_PARTICLES:                 # the preset its words picked (none: nothing added)
        fields["particle"] = next((k for k in synonyms.particles(ln.text) if world._ok(st, "particle", k)), AUTO)
    return fields


def copy_line(proj, index, plan=None):
    """The line's effects with every automatic choice filled in -> JSON for proj.line_clipboard."""
    ln = proj.lines[index]
    plan = plan or make_plan(proj)
    lp = next(x for x in plan.lines if x.index == index)
    return json.dumps({"line": index, "text": ln.text, "fields": _chosen(proj, ln, lp, plan, settings(proj)),
                       "look_seed": str(int(lp.seed)), "cuts": _cut_specs(lp)})


def _section_chosen(plan, index):
    sp = plan.section_plans[index]
    trans = next((w["transition"] for w in plan.world if w["transition"] and abs(w["t"] + w["dur"] / 2 - sp.start) < 1.0),
                 "")
    one, two = sp.picks
    return {"particle": one or AUTO, "particle2": two or AUTO, "background": sp.background["key"],
            "transition": trans or AUTO}


_chosen_cache = {"key": None, "value": ({}, [])}


def chosen(proj):
    """({line index: {field: value}}, [{field: value} per section]): what the planner picks now for the automatic
    fields, shown as "Planner's Choice (...)" (spec §6.2). Reused while the inputs stay the same (a draw must stay
    cheap). ponytail: the key leaves out the audio file and the add-on preferences; a change there shows on the
    next edit."""
    key = repr((state(proj), project.line_inputs(proj), project.section_inputs(proj), proj.duration, proj.bpm,
                proj.panorama_path))
    if key != _chosen_cache["key"]:
        _chosen_cache["key"] = key
        _chosen_cache["value"] = ({}, [])
        if proj.lines and proj.sections:
            plan, st = make_plan(proj), settings(proj)
            lines = {lp.index: _chosen(proj, proj.lines[lp.index], lp, plan, st) for lp in plan.lines
                     if 0 <= lp.index < len(proj.lines)}
            for lp in plan.lines:                            # a line's own background: the transition into it
                w = next((w for w in plan.world if w.get("line") == lp.index and w["transition"]), None)
                if w and lp.index in lines:
                    lines[lp.index]["transition"] = w["transition"]
            _chosen_cache["value"] = (lines, [_section_chosen(plan, i) for i in range(len(plan.section_plans))])
    return _chosen_cache["value"]


def paste_line(proj, index):
    """Write the copied effects into a line (not a locked one). They are plain settings from then on."""
    ln = proj.lines[index]
    data = json.loads(proj.line_clipboard)
    if ln.locked:
        raise ValueError("Unlock the line first")
    for f, v in data["fields"].items():
        if f not in ln.bl_rna.properties:
            continue                    # copied by an older version: a field now gone (distance layer)
        if f == "cuts" and v not in ln.bl_rna.properties[f].enum_items:
            v = AUTO                    # more parts than the menu (a long line cut for size): the same lyrics cut alike
        setattr(ln, f, v)
    ln.look_seed = data["look_seed"]
    ln.paste_cuts = json.dumps(data["cuts"]) if data["cuts"] else ""


def unlock(item):
    for f in json.loads(item.lock_frozen or "[]"):
        if f in item.bl_rna.properties:          # a lock from an older version may name a field now gone (theme)
            setattr(item, f, AUTO)
    item.lock_frozen = ""
    if hasattr(item, "lock_cuts"):                   # lines only, sections have no cuts
        item.lock_cuts = ""
    item.locked = False


def lock_section(proj, index, plan=None):
    sec = proj.sections[index]
    plan = plan or make_plan(proj)
    frozen = []
    for f, v in _section_chosen(plan, index).items():
        if getattr(sec, f) == AUTO and v != AUTO:
            setattr(sec, f, v)
            frozen.append(f)
    sec.lock_frozen = json.dumps(frozen)
    sec.locked = True


def random():
    """A fresh stream for おまかせ: each press is a new proposal (the result is then fixed by its seed)."""
    from ..core.rng import Rng
    return Rng(int(time.time_ns() % 4294967296))
