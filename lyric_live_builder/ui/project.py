"""Glue between the scene properties (props.py) and core/: re-parse, time and section the lyrics."""
import json
import math
import os

import bpy

from ..core import audio, lyrics, sections, timing
from ..props import FONT_ROLES
from ..text import fontinfo

SONG_STRIP = "LLB_Song"
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
    old = [(ln.text, ln.tap_time, ln.use_manual, ln.manual_start) for ln in proj.lines]
    match = lyrics.match_lines([o[0] for o in old], [ln.text for ln in parsed.lines])
    while len(proj.lines) > len(parsed.lines):
        proj.lines.remove(len(proj.lines) - 1)
    while len(proj.lines) < len(parsed.lines):
        proj.lines.add()
    manual, taps = {}, {}
    for i, ln in enumerate(proj.lines):
        if i in match:
            _, ln.tap_time, ln.use_manual, ln.manual_start = old[match[i]]
        else:
            ln.tap_time, ln.use_manual, ln.manual_start = -1.0, False, 0.0
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
    # a hand-set kind stays while its section still starts at the same time
    user_kinds = {round(x.start, 2): x.kind for x in proj.sections if x.user_kind}
    proj.sections.clear()
    for s in secs:
        item = proj.sections.add()
        key = round(s.start, 2)
        item.kind, item.label, item.start, item.end = user_kinds.get(key, s.kind), s.label, s.start, s.end
        item.user_kind = key in user_kinds
    if any(match.get(i) != i for i in range(len(proj.lines))) or len(old) != len(proj.lines):
        # line numbers moved: markers are named after them, so place them again
        for m in [m for m in scene.timeline_markers if _marker_line(m) is not None]:
            scene.timeline_markers.remove(m)
        set_line_markers(scene, [i for i, ln in enumerate(proj.lines) if ln.tap_time >= 0])
    else:
        prune_markers(scene, len(proj.lines))
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
