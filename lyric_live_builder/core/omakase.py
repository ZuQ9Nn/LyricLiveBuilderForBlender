# おまかせ follows JIZURA's J.omakase (src/08b_omakase.js: mood first, then a style that suits
# it, effect strengths, frame stepping, a part subset and colours), MIT License,
# Copyright (c) 2026 hakoniwa. Extended with particles and transitions.
"""おまかせ and "change only this" (spec §6.1). A state is a JSON-friendly dict:
{mood, style, fx, disabled, accent, seed, stage_offsets}; lines, timing and locks live elsewhere."""
import math

from . import color, model, moods, registry, styles, world
from .parts import backgrounds as bgs
from .parts import particles as pts

TARGETS = ("style", "colors", "mood", "text", "particles", "background", "gimmicks")
STAGE_OF = {"text": world.STAGE_TEXT, "particles": world.STAGE_PARTICLES, "background": world.STAGE_BACKGROUND,
            "gimmicks": world.STAGE_GIMMICK}
MIN_ON = {"layout": 6, "enter": 5, "hold": 3, "exit": 5, "particle": 5, "transition": 3}
ALWAYS_ON = {"hold": ("still",), "enter": ("pop_sing",), "exit": ("fade",)}
BACKDROP = "#101018"                 # the accent is fitted against a typical dark dome


def _items(kind):
    """(key, mood tags) of everything the effects panel can switch, per kind."""
    if kind in ("layout", "enter", "hold", "exit"):
        return [(p.key, p.tags) for p in registry.parts(kind)]
    if kind == "particle":
        return [(k, pts.PRESETS[k]["tags"]) for k in pts.AMBIENT]
    if kind == "transition":
        return [(k, ()) for k in bgs.TRANSITION_ORDER]
    raise KeyError(kind)


def _pick(rnd, seq):
    return seq[math.floor(rnd() * len(seq)) % len(seq)]


def _subset(mood, rnd):
    """Kind -> keys turned off: what suits the mood, a sprinkle of the rest, a minimum count."""
    m = moods.MOODS[mood]
    disabled = {}
    for kind, minimum in MIN_ON.items():
        items = _items(kind)
        prefer = None if mood == "chaos" else {k for k, tags in items if mood in tags or
                                               (kind == "transition" and k in (m.get("transitions") or ()))}
        on = {k: (k in prefer or rnd() < 0.22) if prefer is not None else rnd() < 0.8 for k, _ in items}
        for k in ALWAYS_ON.get(kind, ()):
            on[k] = True
        offs = [k for k, v in on.items() if not v]
        while sum(on.values()) < min(minimum, len(items)) and offs:
            on[offs.pop(math.floor(rnd() * len(offs)) % len(offs))] = True
        disabled[kind] = sorted(k for k, v in on.items() if not v)
    return disabled


def _roll_mood(state, rnd):
    if state.get("mood") in moods.STICKY:
        mood = state["mood"]                     # chosen by the user: new proposals keep it
    else:
        mood = _pick(rnd, [k for k in moods.ORDER if k != state.get("mood") and k not in moods.STICKY])
    m = moods.MOODS[mood]
    fx = dict(model.FX_DEFAULTS)
    fx.update(state.get("fx") or {})
    for k, (lo, hi) in m["fx"].items():
        fx[k] = round(lo + (hi - lo) * rnd(), 2)
    fx["koma"] = _pick(rnd, m["koma"])
    fx["flash"] = rnd() < m["flash"]
    return mood, fx, _subset(mood, rnd)


def _roll_style(mood, current, rnd):
    fits = [k for k in styles.ORDER if mood in styles.STYLES[k].get("moods", (mood,))]   # horror styles: horror only
    suits = list((moods.MOODS[mood].get("styles") or ()))
    pool = suits if suits and rnd() < 0.72 else fits
    pool = [k for k in pool if k != current] or [k for k in fits if k != current]
    return _pick(rnd, pool)


def _roll_accent(rnd):
    return color.random_palette(BACKDROP, rnd)["accent"] if rnd() < 0.38 else ""


def omakase(state, rnd):
    """A whole new proposal (the lines' own settings and locks are not part of the state)."""
    mood, fx, disabled = _roll_mood(state, rnd)
    return {"mood": mood, "style": _roll_style(mood, state.get("style"), rnd), "fx": fx, "disabled": disabled,
            "accent": _roll_accent(rnd), "seed": math.floor(rnd() * 1e9), "stage_offsets": {}}


def reroll(state, target, rnd):
    """Change only one aspect of the current proposal."""
    out = dict(state)
    if target == "style":
        out["style"] = _roll_style(state.get("mood") or moods.DEFAULT, state.get("style"), rnd)
    elif target == "colors":
        out["accent"] = "" if state.get("accent") and rnd() < 0.4 else color.random_palette(BACKDROP, rnd)["accent"]
    elif target == "mood":
        out["mood"], out["fx"], out["disabled"] = _roll_mood(state, rnd)
    else:
        offsets = dict(state.get("stage_offsets") or {})
        key = str(STAGE_OF[target])
        offsets[key] = offsets.get(key, 0) + 1
        out["stage_offsets"] = offsets
    return out


def settings(state, **extra):
    """State -> model.Settings (stage offsets back to int keys)."""
    return model.Settings(mood=state.get("mood", ""), style=state.get("style", ""), fx=dict(state.get("fx") or {}),
                          disabled={k: set(v) for k, v in (state.get("disabled") or {}).items()},
                          stage_offsets={int(k): v for k, v in (state.get("stage_offsets") or {}).items()},
                          accent=state.get("accent", ""), **extra)
