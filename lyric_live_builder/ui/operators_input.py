"""Operators for the inputs: lyrics, song, markers."""
import os

import bpy
from bpy.app.translations import pgettext_iface as iface_
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

from . import project

LYRICS_TEXT = "LLB_Lyrics"
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


class LLB_OT_open_lyrics(bpy.types.Operator):
    bl_idname = "llb.open_lyrics"
    bl_label = "Open Lyrics"
    bl_description = "Create the lyrics text if needed and open it in the Text Editor"

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


CLASSES = (LLB_OT_open_lyrics, LLB_OT_refresh, LLB_OT_load_audio, LLB_OT_analyze_audio,
           LLB_OT_import_markers)
