"""The world around the text: themes, backgrounds and transitions, particles, flashes (design §5.5 1, 4–6).

Each stage has its own random stream (seed × stage × index), so re-rolling one stage
("change only this") leaves the others alone."""
import math

import numpy as np

from . import color, model, moods, styles, synonyms, themes, xform
from .parts import backgrounds as bgs
from .parts import particles as pts
from .rng import Rng, h

STAGE_THEME, STAGE_TEXT, STAGE_PARTICLES, STAGE_BACKGROUND, STAGE_GIMMICK = 1, 2, 3, 4, 5
LYRIC_PARTICLES = "lyrics"             # a line's particles picked from its words
FLASH_GAP = 0.4                      # strong flashes at least this far apart (≤ 3 per second, spec §7.5)
STRONG = 0.3                         # flash amount that counts as a strong flash


def stage_seed(settings, seed, stage):
    """The seed of one stage; re-rolling a stage only changes its own seed."""
    k = settings.stage_offsets.get(stage, 0)
    return seed if k == 0 else h(seed, 1000 + stage, k)


def _ok(settings, kind, key):
    return key not in settings.disabled.get(kind, ())


def _wpick(rng, cands):
    cands = [(k, w) for k, w in cands if w > 0]
    return rng.wpick(cands) if cands else None


# ---------------- sections: theme, background, palette ----------------

def pick_themes(sections, seed, settings):
    tseed = stage_seed(settings, seed, STAGE_THEME)
    out, by_kind = [], {}
    for i, sec in enumerate(sections):
        rng = Rng(h(tseed, STAGE_THEME, i + 1))
        if sec.theme in themes.THEMES:
            key = sec.theme
        elif sec.kind in by_kind and rng.chance(0.7):
            key = by_kind[sec.kind]              # same kind, same theme: the chorus is recognisable
        else:
            prev = out[-1] if out else None
            key = _wpick(rng, [(k, moods.favours(settings.mood, t["tags"]) * (1.6 if sec.kind in t["kinds"] else 1.0)
                                * (0.3 if k == prev else 1.0))
                               for k, t in themes.THEMES.items() if _ok(settings, "theme", k)]) or themes.ORDER[0]
        by_kind.setdefault(sec.kind, key)
        out.append(key)
    return out


def _transition(rng, settings, wanted=""):
    if wanted in bgs.TRANSITIONS:
        return wanted
    pref = (moods.MOODS.get(settings.mood) or {}).get("transitions")
    return _wpick(rng, [(k, (2.0 if pref and k in pref else 1.0)) for k in bgs.TRANSITION_ORDER
                        if _ok(settings, "transition", k)]) or "crossfade"


def _background_ok(settings, key):
    return _ok(settings, "background", key) and (settings.panorama or not bgs.needs_image(key))


def plan_world(sections, lines, seed, settings, style):
    """Background changes over the song and the section plans (theme, palette at the section start).
    lines: LineInputs (for per-line background overrides)."""
    theme_keys = pick_themes(sections, seed, settings)
    bseed = stage_seed(settings, seed, STAGE_BACKGROUND)
    switch = 0.25 + 0.75 * settings.fx_value("world_switch")
    world, plans, current = [], [], None
    for i, (sec, tk) in enumerate(zip(sections, theme_keys)):
        rng = Rng(h(bseed, STAGE_BACKGROUND, i + 1))
        theme = themes.THEMES[tk]
        if sec.background and (settings.panorama or not bgs.needs_image(sec.background)):
            key = sec.background
        elif current and current["key"] in theme["backgrounds"] and not rng.chance(switch):
            key = current["key"]                 # same family and a quiet switch setting: stay
        else:
            cands = [b for b in theme["backgrounds"] if _background_ok(settings, b)] or [bgs.DEFAULT]
            key = _wpick(rng, [(b, (2.0 if k == 0 else 1.0) * (0.25 if current and b == current["key"] else 1.0))
                               for k, b in enumerate(cands)])
        trans = _transition(rng, settings, sec.transition)
        if current is None:
            current = bgs.resolve(key, style)
            world.append({"t": 0.0, "dur": 0.0, "spec": current, "transition": ""})
        elif key != current["key"]:
            current = bgs.resolve(key, style)
            dur = bgs.TRANSITIONS[trans]["dur"]
            world.append({"t": max(0.0, sec.start - dur / 2), "dur": dur, "spec": current, "transition": trans})
        plans.append(model.SectionPlan(index=i, kind=sec.kind, start=sec.start, end=sec.end, theme=tk,
                                       background=current, particles=[], palette={}))
    # per-line background overrides start with the line
    for ln in lines:
        if ln.background in bgs.PRESETS and (settings.panorama or not bgs.needs_image(ln.background)):
            rng = Rng(h(bseed, STAGE_BACKGROUND, 1000 + ln.index))
            trans = _transition(rng, settings, ln.transition)
            world.append({"t": ln.start, "dur": bgs.TRANSITIONS[trans]["dur"],
                          "spec": bgs.resolve(ln.background, style), "transition": trans})
    world.sort(key=lambda w: w["t"])
    _space_out(world)
    for sp in plans:
        sp.background = active_background(world, sp.start + 0.01)
        sp.palette = styles.palette(style, bgs.backdrop(sp.background), settings.accent or None)
    return plans, world


def _space_out(world):
    """Transitions may not overlap: a later one waits for the earlier one to finish."""
    for a, b in zip(world, world[1:]):
        if b["t"] < a["t"] + a["dur"]:
            b["t"] = a["t"] + a["dur"]


def active_background(world, t):
    cur = world[0]["spec"]
    for w in world:
        if w["t"] <= t:
            cur = w["spec"]
    return cur


def line_colors(world, style, accent, t):
    """Linear text colours for a line starting at t (read against the background active then)."""
    pal = styles.palette(style, bgs.backdrop(active_background(world, t + 0.01)), accent or None)
    return {"fg": color.linear(pal["fg"]), "accent": color.linear(pal["accent"])}


# ---------------- particles ----------------

def _intensity(settings, start, end):
    """Emission over the section from the song's loudness (louder = more), as (t, value) keys."""
    if settings.energy is None or len(settings.energy) == 0:
        return []
    e = np.asarray(settings.energy, dtype=np.float64)
    rate = settings.energy_rate
    ts = np.arange(start, end + 1e-6, 1.0)
    vals = []
    for t in ts:
        a, b = int(max(0, (t - 1.0) * rate)), int(min(len(e), (t + 1.0) * rate))
        vals.append(float(e[a:b].mean()) if b > a else 0.5)
    return [(float(t), round(0.45 + 0.55 * v, 3)) for t, v in zip(ts, vals)]


def _bursts(rng, preset, start, end):
    b = preset["burst"]
    out, t = [], start + 0.5
    while b.get("interval") and t < end - 0.5:
        az, el, r = math.radians(rng.range(-60, 60)), math.radians(rng.range(12, 32)), rng.range(15, 24)
        out.append({"t": round(t, 3), "origin": [float(x) for x in pts.EYE + r * xform.direction(az, el)]})
        t += rng.range(*b["interval"])
    return out


def emitter(key, start, end, seed, palette, settings, bursts=None, intensity=None):
    p = pts.scale(pts.PRESETS[key], settings.fx_value("particles"))
    p.pop("name", None)
    p.pop("tags", None)
    if p["emitter"] == "burst" and bursts is None:
        bursts = _bursts(Rng(seed), p, start, end)
    spec = {"key": key, "preset": p, "start": start, "end": end, "seed": seed, "intensity": intensity or [],
            "colors": [color.linear(palette.get(r, "#FFFFFF")) for r in p["colors"]], "bursts": bursts or [],
            "fade_in": 0.8, "fade_out": 1.0}
    spec["count"] = pts.continuous_count(p)
    spec["pool"] = pts.burst_capacity(p, spec["bursts"])
    return spec


def plan_particles(section_plans, line_plans, seed, settings):
    pseed = stage_seed(settings, seed, STAGE_PARTICLES)
    amount = settings.fx_value("particles")
    n_presets = 1 if amount < 0.35 else 2 if amount < 0.75 else 3
    out = []
    for sp in section_plans:
        rng = Rng(h(pseed, STAGE_PARTICLES, sp.index + 1))
        cands = [k for k in themes.THEMES[sp.theme]["particles"] if _ok(settings, "particle", k)]
        chosen = []
        for _ in range(min(n_presets, len(cands))):
            k = _wpick(rng, [(c, moods.favours(settings.mood, pts.PRESETS[c]["tags"]) * (1.5 if j == 0 else 1.0))
                             for j, c in enumerate(cands) if c not in chosen])
            if k:
                chosen.append(k)
        sp.particles = chosen
        inten = _intensity(settings, sp.start, sp.end)
        for k, key in enumerate(chosen):
            out.append(emitter(key, sp.start, sp.end, h(pseed, STAGE_PARTICLES, sp.index + 1, k + 1), sp.palette,
                               settings, intensity=inten))
    for lp in line_plans:
        sp = next((s for s in section_plans if s.start <= lp.start < s.end), section_plans[-1])
        hit = lp.start + 0.05                       # after the text appears (spec §7.6)
        origin = [float(x) for x in pts.EYE + model.DISTANCE[lp.distance] *
                  xform.direction(*(lp.anchor if not lp.glide else (0.0, 0.0)))]
        lseed = h(pseed, STAGE_PARTICLES, 5000 + lp.index)
        key = lp.particle
        if key == LYRIC_PARTICLES:              # the first word of the line that names a preset (none: automatic)
            key = next((k for k in synonyms.particles(lp.text) if _ok(settings, "particle", k)), "")
        if key in pts.PRESETS:
            p = pts.PRESETS[key]
            bursts = [{"t": hit, "origin": origin}] if p["emitter"] == "burst" else None
            out.append(emitter(key, lp.start, lp.end, lseed, sp.palette, settings, bursts=bursts))
        elif lp.impact or (lp.emphasis and Rng(lseed).chance(0.3 * settings.fx_value("decor"))):
            out.append(emitter("sparkle_burst", lp.start, lp.end, lseed, sp.palette, settings,
                               bursts=[{"t": hit, "origin": origin}]))
    return out


# ---------------- events: flashes and beat pulses ----------------

def plan_events(section_plans, line_plans, world, settings):
    events = []
    mood = moods.MOODS.get(settings.mood) or {}
    if settings.fx_value("flash"):
        for lp in line_plans:
            if lp.impact:
                events.append({"type": "flash", "t": lp.start + 0.05, "amp": 0.45, "dur": 0.5, "color": "#FFFFFF"})
        for sp in section_plans[1:]:
            if sp.kind == "chorus":
                events.append({"type": "flash", "t": sp.start, "amp": 0.35, "dur": 0.6, "color": "#FFFFFF"})
    # strong flashes of transitions count too; keep them FLASH_GAP apart (transitions win)
    fixed = [w["t"] + w["dur"] / 2 for w in world if bgs.TRANSITIONS.get(w["transition"], {}).get("flash")]
    kept, last = [], -1e9
    for ev in sorted(events, key=lambda e: e["t"]):
        if any(abs(ev["t"] - f) < FLASH_GAP for f in fixed) or ev["t"] - last < FLASH_GAP:
            continue
        kept.append(ev)
        last = ev["t"]
    if mood.get("pulse") and settings.beats is not None:
        for sp in section_plans:
            if sp.kind != "chorus":
                continue
            for t in settings.beats:
                if sp.start <= t < sp.end:
                    kept.append({"type": "pulse", "t": float(t), "amp": 0.06, "dur": 0.3, "color": ""})
    return sorted(kept, key=lambda e: e["t"])
