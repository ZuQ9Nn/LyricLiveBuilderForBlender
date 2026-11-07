"""Operators for the inputs: lyrics, song, markers."""
import os

import bpy
from bpy.app.translations import pgettext_iface as iface_
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

from ..core import lyrics
from . import project, tap_sync

LYRICS_TEXT = "LLB_Lyrics"
EDIT_FILE = "LLB_Lyrics.txt"
WATCH_EVERY = 0.5                    # seconds between looks at the file open in the external editor
LYRICS_TEMPLATE = """# Lyrics. One line per phrase. See "Notation" in the Lyrics panel.
[A]
"""


def _show_text(context, text):
    """Show text in an existing Text Editor, or in a new window."""
    for area in context.screen.areas:
        if area.type == "TEXT_EDITOR":
            area.spaces.active.text = text
            return
    bpy.ops.wm.window_new()
    win = context.window_manager.windows[-1]
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    area.type = "TEXT_EDITOR"
    area.spaces.active.text = text


def set_lyrics(scene, source):
    proj = scene.llb
    if proj.lyrics_text is None:
        proj.lyrics_text = bpy.data.texts.new(LYRICS_TEXT)
    proj.lyrics_text.from_string("\n".join(source.splitlines()))
    project.recompute(scene)


# ---- the file open in the external editor (Blender's Text Editor takes no IME input) ----

_watch = None


def _stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def _open_file(path):
    bpy.ops.wm.path_open(filepath=path)


def watching():
    return bpy.app.timers.is_registered(watch_tick)


def stop_watch():
    if watching():
        bpy.app.timers.unregister(watch_tick)


def watch_tick():
    """Take the file in once it has stopped changing: a save may still be going on at the first sight."""
    w = _watch
    scene = bpy.data.scenes.get(w["scene"])
    if scene is None:
        return None
    now = _stamp(w["path"])
    settled = now == w["last"]
    w["last"] = now
    if now is None or now == w["seen"] or not settled or tap_sync.tapping():
        return WATCH_EVERY
    try:
        with open(w["path"], "rb") as f:
            source = lyrics.decode_text(f.read())
    except OSError:                                  # the editor still holds it
        return WATCH_EVERY
    w["seen"] = now
    if source.strip():                               # an emptied file would drop every line and its tap
        set_lyrics(scene, source)
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    return WATCH_EVERY


class LLB_OT_edit_lyrics(bpy.types.Operator):
    bl_idname = "llb.edit_lyrics"
    bl_label = "Edit in External Editor"
    bl_description = ("Open the lyrics in your system's text editor, where Japanese can be typed. "
                      "Saving there updates them here")

    def execute(self, context):
        global _watch
        path = os.path.join(bpy.app.tempdir, EDIT_FILE)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:      # the BOM tells any editor it is UTF-8
            f.write(project.lyrics_source(context.scene.llb) or LYRICS_TEMPLATE)
        now = _stamp(path)
        _watch = {"path": path, "scene": context.scene.name, "seen": now, "last": now}
        if not watching():
            bpy.app.timers.register(watch_tick, first_interval=WATCH_EVERY)
        try:
            _open_file(path)
        except (RuntimeError, OSError) as e:
            self.report({"ERROR"}, iface_("Could not open a text editor ({})").format(e))
            return {"CANCELLED"}
        return {"FINISHED"}


class LLB_OT_paste_lyrics(bpy.types.Operator):
    bl_idname = "llb.paste_lyrics"
    bl_label = "Paste from Clipboard"
    bl_description = "Replace the lyrics with the text copied to the clipboard"
    bl_options = {"UNDO"}

    def invoke(self, context, event):
        if len(context.scene.llb.lines):
            return context.window_manager.invoke_confirm(self, event, title=iface_("Replace the Lyrics?"),
                                                         message=iface_("The current lyrics are replaced"))
        return self.execute(context)

    def execute(self, context):
        source = context.window_manager.clipboard
        if not source.strip():
            self.report({"WARNING"}, iface_("The clipboard has no text"))
            return {"CANCELLED"}
        set_lyrics(context.scene, source)
        proj = context.scene.llb
        self.report({"INFO"}, iface_("{} lines, {} sections").format(len(proj.lines), len(proj.sections)))
        return {"FINISHED"}


class LLB_OT_load_lyrics(bpy.types.Operator, ImportHelper):
    bl_idname = "llb.load_lyrics"
    bl_label = "Load Lyrics File"
    bl_description = "Replace the lyrics with a text or LRC file (UTF-8, UTF-16 or Shift_JIS)"
    bl_options = {"UNDO"}

    filter_glob: StringProperty(default="*.txt;*.lrc", options={"HIDDEN"})

    def execute(self, context):
        try:
            with open(self.filepath, "rb") as f:
                source = lyrics.decode_text(f.read())
        except OSError as e:
            self.report({"ERROR"}, iface_("Could not read the file ({})").format(e))
            return {"CANCELLED"}
        if not source.strip():
            self.report({"WARNING"}, iface_("The file has no text"))
            return {"CANCELLED"}
        set_lyrics(context.scene, source)
        proj = context.scene.llb
        self.report({"INFO"}, iface_("{} lines, {} sections").format(len(proj.lines), len(proj.sections)))
        return {"FINISHED"}


class LLB_OT_open_lyrics(bpy.types.Operator):
    bl_idname = "llb.open_lyrics"
    bl_label = "Open Lyrics"
    bl_description = "Create the lyrics text if needed and open it in Blender's Text Editor (no Japanese typing there; pasting works)"

    def execute(self, context):
        proj = context.scene.llb
        if proj.lyrics_text is None:
            text = bpy.data.texts.new(LYRICS_TEXT)
            text.write(LYRICS_TEMPLATE)
            proj.lyrics_text = text
        _show_text(context, proj.lyrics_text)
        return {"FINISHED"}


class LLB_OT_refresh(bpy.types.Operator):
    bl_idname = "llb.refresh"
    bl_label = "Read Lyrics"
    bl_description = "Read the lyrics again and update the lines and sections (taps and manual times are kept)"

    def execute(self, context):
        project.recompute(context.scene)
        proj = context.scene.llb
        self.report({"INFO"}, iface_("{} lines, {} sections").format(len(proj.lines), len(proj.sections)))
        return {"FINISHED"}


class LLB_OT_load_audio(bpy.types.Operator, ImportHelper):
    bl_idname = "llb.load_audio"
    bl_label = "Load Song"
    bl_description = "Place the song in the Sequencer, fit the scene length and detect the BPM"

    filter_glob: StringProperty(default="*.wav;*.mp3;*.ogg;*.flac;*.m4a;*.aac;*.opus", options={"HIDDEN"})

    def execute(self, context):
        scene = context.scene
        proj = scene.llb
        path = os.path.abspath(self.filepath)
        try:
            info = project.analyze_audio(path)
        except Exception as e:
            self.report({"ERROR"}, iface_("Could not read the song ({}). Use WAV, MP3, OGG, FLAC or M4A").format(e))
            return {"CANCELLED"}
        proj.audio_path = path
        proj.audio_duration = info.duration
        project.place_song(scene, path, info.duration)
        proj.beat_offset = float(info.beats[0]) if len(info.beats) else 0.0
        proj.bpm = info.bpm           # triggers recompute
        project.recompute(scene)
        self.report({"INFO"}, iface_("{:.1f} s, BPM {:.1f}").format(info.duration, info.bpm))
        return {"FINISHED"}


class LLB_OT_analyze_audio(bpy.types.Operator):
    bl_idname = "llb.analyze_audio"
    bl_label = "Detect BPM"
    bl_description = "Detect the BPM and first beat of the song again"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.llb.audio_path)

    def execute(self, context):
        proj = context.scene.llb
        info = project.audio_info(proj)
        if info is None:
            self.report({"ERROR"}, iface_("Could not read the song"))
            return {"CANCELLED"}
        proj.beat_offset = float(info.beats[0]) if len(info.beats) else 0.0
        proj.bpm = info.bpm
        return {"FINISHED"}


class LLB_OT_import_markers(bpy.types.Operator):
    bl_idname = "llb.import_markers"
    bl_label = "Import from Markers"
    bl_description = "Use the positions of the LLB timeline markers as the line start times"

    def execute(self, context):
        n = project.import_markers(context.scene)
        self.report({"INFO"}, iface_("{} lines updated").format(n))
        return {"FINISHED"}


CLASSES = (LLB_OT_edit_lyrics, LLB_OT_paste_lyrics, LLB_OT_load_lyrics, LLB_OT_open_lyrics, LLB_OT_refresh, LLB_OT_load_audio, LLB_OT_analyze_audio,
           LLB_OT_import_markers)
