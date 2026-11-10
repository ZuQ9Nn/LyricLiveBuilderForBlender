"""Glue between the scene properties and the planner: おまかせ state, settings, locks, preview build."""
import json
import os
import time

import bpy

from .. import prefs
from ..core import audio, bake, color, gimmick_shapes, model, omakase, planner, registry, synonyms, themes, world
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
    out += [("theme", k, themes.THEMES[k]["name"]) for k in themes.ORDER]
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
                            user_words=synonyms.parse_user(p.gimmick_words) if p else {})


def make_plan(proj, snap=None):
    """snap: the trial's saved state (Before); None = the settings now."""
    sync_parts(proj)
    st = snap["state"] if snap else None
    return planner.plan(project.line_inputs(proj, snap), project.section_inputs(proj, snap), proj.duration,
                        st["seed"] if st else proj.seed, bpm=proj.bpm, settings=settings(proj, st))


_summary = {"key": None, "value": None}


def section_summary(proj):
    """world.section_summary for the panel, reused while its inputs stay the same (a draw must stay cheap)."""
    from ..core.model import LineInput
    auto = lambda v: "" if v == AUTO else v
    lines = [(ln.start, ln.end, ln.section_index, auto(ln.background), auto(ln.transition)) for ln in proj.lines]
    secs = project.section_inputs(proj)
    key = json.dumps([state(proj), [list(map(str, (s.start, s.end, s.kind, s.theme, s.background, s.transition)))
                                    for s in secs], lines, proj.duration, proj.panorama_path], sort_keys=True)
    if key != _summary["key"]:
        ins = [LineInput(index=i, text="", start=a, end=b, section_index=k, background=bg, transition=tr)
               for i, (a, b, k, bg, tr) in enumerate(lines)]
        _summary["value"] = world.section_summary(secs, ins, proj.seed, settings(proj)) if secs else []
        _summary["key"] = key
    return _summary["value"]


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

LINE_LOCK_FIELDS = ("layout", "enter", "hold", "exit", "distance_layer", "persist", "gimmick", "gimmick_show")


def lock_line(proj, index, plan=None):
    """Fill the line's automatic fields with what the planner chose now, so later rolls keep them."""
    ln = proj.lines[index]
    plan = plan or make_plan(proj)
    lp = next(x for x in plan.lines if x.index == index)
    chosen = {"layout": lp.layout, "enter": lp.enter, "hold": lp.hold, "exit": lp.exit,
              "distance_layer": lp.distance, "persist": "section" if lp.persist else "next"}
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
    ln.lock_cuts = json.dumps([{"layout": c.layout, "enter": c.enter, "hold": c.hold, "exit": c.exit, "distance": c.distance}
                               for c in lp.cuts or ()])
    ln.locked = True


def unlock(item):
    for f in json.loads(item.lock_frozen or "[]"):
        setattr(item, f, AUTO)
    item.lock_frozen = ""
    if hasattr(item, "lock_cuts"):                   # lines only, sections have no cuts
        item.lock_cuts = ""
    item.locked = False


def lock_section(proj, index, plan=None):
    sec = proj.sections[index]
    plan = plan or make_plan(proj)
    sp = plan.section_plans[index]
    trans = next((w["transition"] for w in plan.world if w["transition"] and abs(w["t"] + w["dur"] / 2 - sp.start) < 1.0),
                 "")
    chosen = {"theme": sp.theme, "background": sp.background["key"], "transition": trans or AUTO}
    frozen = []
    for f, v in chosen.items():
        if getattr(sec, f) == AUTO and v != AUTO:
            setattr(sec, f, v)
            frozen.append(f)
    sec.lock_frozen = json.dumps(frozen)
    sec.locked = True


def random():
    """A fresh stream for おまかせ: each press is a new proposal (the result is then fixed by its seed)."""
    from ..core.rng import Rng
    return Rng(int(time.time_ns() % 4294967296))
