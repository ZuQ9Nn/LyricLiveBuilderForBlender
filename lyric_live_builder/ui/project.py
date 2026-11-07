"""Glue between the scene properties (props.py) and core/: re-parse, time and section the lyrics."""
import json
import math
import os

import bpy

from ..core import audio, lyrics, sections, timing
from ..props import FONT_ROLES
from ..text import fontinfo

SONG_STRIP = "LLB_Song"
# per-line settings made by the user; they follow their line when the lyrics are edited
LINE_DEFAULTS = {"tap_time": -1.0, "use_manual": False, "manual_start": 0.0, "is_3d": False, "depth": 0.15,
                 "bevel": "0.015", "layout": "AUTO", "enter": "AUTO", "hold": "AUTO", "exit": "AUTO",
                 "distance_layer": "AUTO", "cuts": "AUTO", "persist": "AUTO", "guide": "AUTO", "gimmick": "AUTO", "gimmick_show": "AUTO",
                 "gimmick_word": "", "particle": "AUTO",
                 "background": "AUTO", "transition": "AUTO", "locked": False, "lock_frozen": "", "lock_cuts": "", "seed_offset": 0}
SECTION_USER_FIELDS = ("theme", "background", "transition", "locked", "lock_frozen")
LINE_USER_FIELDS = tuple(LINE_DEFAULTS)
_busy = False
_audio_cache = {}          # abs path -> (mtime, AudioInfo)


def fps(scene):
    return scene.render.fps / scene.render.fps_base


def lyrics_source(proj):
    return proj.lyrics_text.as_string() if proj.lyrics_text else ""


# ---- audio ----

def analyze_audio(path):
    """Decode with Audaspace and analyze; cached per file. Raises on unreadable files."""
    import aud
    key = os.path.abspath(path)
    mtime = os.path.getmtime(key)
    hit = _audio_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    sound = aud.Sound(key)
    info = audio.analyze(sound.data(), int(sound.specs[0]))
    _audio_cache[key] = (mtime, info)
    return info


def audio_info(proj):
    """AudioInfo of the project's song, or None when there is none or it cannot be read."""
    path = bpy.path.abspath(proj.audio_path) if proj.audio_path else ""
    if not path or not os.path.isfile(path):
        return None
    try:
        return analyze_audio(path)
    except Exception:
        return None


def place_song(scene, path, duration):
    """Put the song on a free VSE channel at the scene start and fit the scene length to it."""
    se = scene.sequence_editor or scene.sequence_editor_create()
    for s in [s for s in se.strips if s.name.startswith(SONG_STRIP)]:
        se.strips.remove(s)
    used = {s.channel for s in se.strips}
    channel = next(c for c in range(1, 129) if c not in used)
    strip = se.strips.new_sound(SONG_STRIP, path, channel, scene.frame_start)
    strip.name = SONG_STRIP
    scene.frame_end = scene.frame_start + max(1, math.ceil(duration * fps(scene))) - 1
    scene.sync_mode = "AUDIO_SYNC"
    return strip


# ---- fonts ----

def font_status(proj, role):
    """(FontInfo or None, error message or None) for a role's file."""
    fp = proj.font(role).filepath
    if not fp:
        return None, None
    path = bpy.path.abspath(fp)
    if not os.path.isfile(path):
        return None, "File not found"
    try:
        return fontinfo.load(path), None
    except (OSError, ValueError):
        return None, "Not a TrueType / OpenType font"


def resolved_font_role(proj, role):
    """The role itself when it has a file, else body (unassigned roles use the body font)."""
    return role if proj.font(role).filepath else "body"


def lyric_chars(proj):
    """All characters shown on stage (line text and annotations)."""
    p = lyrics.parse(lyrics_source(proj))
    return "".join(ln.text + (ln.note or "") for ln in p.lines)


def missing_chars(proj, role):
    info, _ = font_status(proj, role)
    return info.missing(lyric_chars(proj)) if info else []


def has_any_font(proj):
    return any(proj.font(r).filepath for r in FONT_ROLES)


# ---- lines / timing / sections ----

def is_busy():
    return _busy


def recompute(scene):
    """Re-parse the lyrics and rebuild lines and sections, keeping taps and manual times by index."""
    global _busy
    if _busy:
        return
    _busy = True
    try:
        _recompute(scene)
    finally:
        _busy = False


def _recompute(scene):
    proj = scene.llb
    parsed = lyrics.parse(lyrics_source(proj))
    old = [(ln.text, {f: getattr(ln, f) for f in LINE_USER_FIELDS}) for ln in proj.lines]
    match = lyrics.match_lines([o[0] for o in old], [ln.text for ln in parsed.lines])
    while len(proj.lines) > len(parsed.lines):
        proj.lines.remove(len(proj.lines) - 1)
    while len(proj.lines) < len(parsed.lines):
        proj.lines.add()
    manual, taps = {}, {}
    for i, ln in enumerate(proj.lines):
        values = old[match[i]][1] if i in match else LINE_DEFAULTS
        for f, v in values.items():
            setattr(ln, f, v)
        if ln.use_manual:
            manual[i] = ln.manual_start
        if ln.tap_time >= 0:
            taps[i] = ln.tap_time
    info = audio_info(proj)
    tm = timing.compute(parsed.lines, bpm=proj.bpm, manual=manual, taps=taps,
                        audio_duration=info.duration if info else None)
    if parsed.headings:
        secs = sections.from_headings(parsed, tm)
    else:
        secs = sections.estimate(parsed, tm, bpm=proj.bpm,
                                 energy=info.energy if info else None,
                                 energy_rate=info.energy_rate if info else audio.RATE)
    proj.sections_from_headings = bool(parsed.headings)
    proj.duration = tm.duration
    for i, (ln, src) in enumerate(zip(proj.lines, parsed.lines)):
        ln.index = i
        ln.text = src.text
        ln.start, ln.end, ln.source = tm.starts[i], tm.ends[i], tm.sources[i]
        ln.section_index = sections.section_of(secs, tm.starts[i])
        ln.char_times = json.dumps([round(t, 4) for t in timing.char_times(src.text, tm.starts[i], tm.ends[i])])
    # a hand-set kind (and theme, background, lock) stays while its section still starts at the same time
    user_kinds = {round(x.start, 2): x.kind for x in proj.sections if x.user_kind}
    user_sets = {round(x.start, 2): {f: getattr(x, f) for f in SECTION_USER_FIELDS} for x in proj.sections}
    proj.sections.clear()
    for s in secs:
        item = proj.sections.add()
        key = round(s.start, 2)
        item.kind, item.label, item.start, item.end = user_kinds.get(key, s.kind), s.label, s.start, s.end
        item.user_kind = key in user_kinds
        for f, v in user_sets.get(key, {}).items():
            setattr(item, f, v)
    if any(match.get(i) != i for i in range(len(proj.lines))) or len(old) != len(proj.lines):
        # line numbers moved: markers are named after them, so place them again
        for m in [m for m in scene.timeline_markers if _marker_line(m) is not None]:
            scene.timeline_markers.remove(m)
        set_line_markers(scene, [i for i, ln in enumerate(proj.lines) if ln.tap_time >= 0])
    else:
        prune_markers(scene, len(proj.lines))
    from . import planning
    planning.sync_parts(proj)
    proj.line_active = min(proj.line_active, max(0, len(proj.lines) - 1))
    proj.section_active = min(proj.section_active, max(0, len(proj.sections) - 1))


# ---- markers ----

MARKER_PREFIX = "LLB:"


def marker_name(i):
    return f"{MARKER_PREFIX}{i + 1}"


def set_line_markers(scene, indices):
    """(Re)place one timeline marker per tapped line at its tap time."""
    proj = scene.llb
    wanted = {marker_name(i) for i in indices}
    for m in [m for m in scene.timeline_markers if m.name in wanted]:
        scene.timeline_markers.remove(m)
    for i in indices:
        t = proj.lines[i].tap_time
        if t >= 0:
            m = scene.timeline_markers.new(marker_name(i), frame=scene.frame_start + round(t * fps(scene)))
            m.select = False          # so moving one marker with G does not drag all of them


def _marker_line(m):
    """0-based line index of an LLB marker, or None."""
    if not m.name.startswith(MARKER_PREFIX):
        return None
    try:
        return int(m.name[len(MARKER_PREFIX):]) - 1
    except ValueError:
        return None


def prune_markers(scene, n_lines):
    """Remove LLB markers of lines that no longer exist (the lyrics got shorter)."""
    for m in [m for m in scene.timeline_markers if (_marker_line(m) or 0) >= n_lines]:
        scene.timeline_markers.remove(m)


def import_markers(scene):
    """Moved markers -> tap times. A marker still on its tap's frame keeps the sub-frame tap time."""
    proj = scene.llb
    changed = 0
    for m in scene.timeline_markers:
        i = _marker_line(m)
        if i is None or not 0 <= i < len(proj.lines):
            continue
        ln = proj.lines[i]
        rel = m.frame - scene.frame_start
        if ln.tap_time >= 0 and round(ln.tap_time * fps(scene)) == rel:
            continue
        ln.tap_time = max(0.0, rel / fps(scene))
        changed += 1
    if changed:
        recompute(scene)
    return changed


# ---- preview inputs ----

def font_paths(proj, role):
    """Font files to try for a role, in fallback order (the role, then body, then the rest)."""
    order = [role, "body"] + [r for r in FONT_ROLES if r not in (role, "body")]
    out = []
    for r in order:
        fp = proj.font(r).filepath
        if fp:
            p = bpy.path.abspath(fp)
            if p not in out and os.path.isfile(p):
                out.append(p)
    return out


class _Metrics:
    """Advances of a role, taking each character from the first font that has it."""

    def __init__(self, infos):
        self.infos = infos

    def _info(self, ch):
        for info in self.infos:
            if info.has_char(ch):
                return info
        return self.infos[0]

    def advance_em(self, ch):
        return self._info(ch).advance_em(ch)

    def vadvance_em(self, ch):
        return self._info(ch).vadvance_em(ch)


def metrics(proj):
    cache = {}

    def get(role):
        if role not in cache:
            infos = []
            for p in font_paths(proj, role):
                try:
                    infos.append(fontinfo.load(p))
                except (OSError, ValueError):
                    pass
            if not infos:
                raise ValueError("no usable font")
            cache[role] = _Metrics(infos)
        return cache[role]
    return get


class _Saved:
    """An item's properties, with the values saved for the trial's Before taking their place."""

    def __init__(self, item, saved):
        self._item, self._saved = item, saved or {}

    def __getattr__(self, name):
        return self._saved[name] if name in self._saved else getattr(self._item, name)


def _saved(items, saved, same):
    """saved[i] for the items it still belongs to (same text / same count), else nothing."""
    return [_Saved(x, saved[i] if saved and i < len(saved) and same(x, saved[i]) else None) for i, x in enumerate(items)]


def section_inputs(proj, snap=None):
    """snap: the trial's saved state (ui/trial.py); its values replace the section settings."""
    from ..core.model import SectionInput
    auto = lambda v: "" if v == "AUTO" else v
    secs = _saved(proj.sections, snap and snap["sections"], lambda x, s: len(snap["sections"]) == len(proj.sections))
    return [SectionInput(s.start, s.end, s.kind, auto(s.theme), auto(s.background), auto(s.transition)) for s in secs]


def line_inputs(proj, snap=None):
    """Scene lines -> core LineInputs (notation flags re-read from the lyrics).
    snap: the trial's saved state; its values replace the settings of lines whose text is unchanged."""
    from ..core.model import LineInput
    parsed = lyrics.parse(lyrics_source(proj)).lines
    out = []
    for i, ln in enumerate(_saved(proj.lines, snap and snap["lines"], lambda x, s: x.text == s["text"])):
        src = parsed[i] if i < len(parsed) else None
        auto = lambda v: "" if v == "AUTO" else v
        out.append(LineInput(
            index=i, text=ln.text, start=ln.start, end=ln.end, section_index=ln.section_index,
            char_times=json.loads(ln.char_times) if ln.char_times else None,
            emph_words=list(src.emph) if src else [], impact=bool(src and src.impact),
            chunks=list(src.manual) if src and src.manual else None,
            is_3d=ln.is_3d, depth=ln.depth, bevel=float(ln.bevel), layout=auto(ln.layout), enter=auto(ln.enter),
            hold=auto(ln.hold), exit=auto(ln.exit), distance=auto(ln.distance_layer), persist=auto(ln.persist),
            particle=auto(ln.particle), background=auto(ln.background), transition=auto(ln.transition),
            guide=auto(ln.guide), gimmick=auto(ln.gimmick), gimmick_show=auto(ln.gimmick_show),
            gimmick_word=ln.gimmick_word, seed_offset=ln.seed_offset,
            cuts=int(auto(ln.cuts) or 0), cut_specs=json.loads(ln.lock_cuts) if ln.lock_cuts else None))
    return out
