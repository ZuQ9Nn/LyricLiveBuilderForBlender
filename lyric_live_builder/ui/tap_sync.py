"""Tap Sync and tap latency measurement (modal operators).

Taps store time.perf_counter(); a frame_change_post handler pairs played frames with the same
clock, and the median of (wall - song time) maps taps to song time. This removes the one-frame
jitter of AUDIO_SYNC playback and gives sub-frame precision (prototype S0-08).
"""
import os
import statistics
import time
import wave

import bpy
import numpy as np
from bpy.app.translations import pgettext_iface as iface_

from .. import prefs
from ..core.timing import LATENCY_BPM, LATENCY_COUNT_IN, LATENCY_TAPS, tap_latency
from . import project
from .overlay import Overlay

CLICK_STRIP = "LLB_Click"


class _Clock:
    """Pairs played frames with the wall clock and notices the end of playback. Playback loops,
    and a modal only runs on events, so a timer keeps it polling and a jump back to the start
    counts as the end (otherwise frames of a second pass would spoil the mapping)."""

    def __init__(self):
        self.pairs = []
        self.done = False
        self.timer = None

    def _on_frame(self, scene, _depsgraph=None):
        if self.done:
            return
        if self.pairs and scene.frame_current < self.pairs[-1][0]:
            self.done = True                       # wrapped around
            return
        # the audio clock ticks in buffers of about one frame: a repeated frame is a frame late, and
        # with enough of them the median below would be too
        if not self.pairs or scene.frame_current != self.pairs[-1][0]:
            self.pairs.append((scene.frame_current, time.perf_counter()))
        if scene.frame_current >= scene.frame_end:
            self.done = True

    def start(self, context):
        self.pairs.clear()
        self.done = False
        bpy.app.handlers.frame_change_post.append(self._on_frame)
        self.timer = context.window_manager.event_timer_add(0.05, window=context.window)

    def stop(self, context):
        if self._on_frame in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(self._on_frame)
        if self.timer:
            context.window_manager.event_timer_remove(self.timer)
            self.timer = None

    def ended(self, context):
        return self.done or not context.screen.is_animation_playing

    def song_times(self, scene, walls):
        """Wall clock stamps -> seconds from the scene start (None without recorded frames)."""
        if not self.pairs:
            return None
        f = project.fps(scene)
        c = statistics.median(t - (fr - scene.frame_start) / f for fr, t in self.pairs)
        return [w - c for w in walls]


def latency_ms(context):
    proj = context.scene.llb
    if proj.latency_measured:
        return proj.tap_latency_ms
    p = prefs.get(context)
    return p.tap_latency_ms if p else 0.0


def _play(context):
    scene = context.scene
    scene.frame_set(scene.frame_start)
    if not context.screen.is_animation_playing:
        bpy.ops.screen.animation_play()


def _stop(context):
    if context.screen.is_animation_playing:
        bpy.ops.screen.animation_cancel(restore_frame=True)


class LLB_OT_tap_sync(bpy.types.Operator):
    bl_idname = "llb.tap_sync"
    bl_label = "Tap Sync"
    bl_description = "Play the song and press T where each line starts (Backspace: undo, Esc: finish)"

    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.lines) > 0

    def invoke(self, context, event):
        # the frame clock has a bias of up to one frame; it cancels only at the measuring frame rate
        proj, f = context.scene.llb, project.fps(context.scene)
        if proj.latency_measured and proj.latency_fps > 0 and abs(proj.latency_fps - f) > 0.01:
            self.report({"WARNING"}, iface_("Latency was measured at {:g} fps, the scene is {:g} fps. Measure it again")
                        .format(proj.latency_fps, f))
        self.clock = _Clock()
        self.taps = []
        self.clock.start(context)
        _play(context)
        context.window_manager.modal_handler_add(self)
        self.overlay = Overlay(lambda: self._guide(bpy.context))
        self.overlay.start()
        self._status(context)
        return {"RUNNING_MODAL"}

    def _guide(self, context):
        lines = context.scene.llb.lines
        k = len(self.taps)
        nxt = lines[k].text if k < len(lines) else iface_("All lines recorded (Esc)")
        return [(iface_("Tap Sync  next line {} / {}").format(min(k + 1, len(lines)), len(lines)), 14),
                (nxt, 26),
                (iface_("T: line start   Backspace: undo   Esc: finish"), 12)]

    def _status(self, context):
        context.workspace.status_text_set("   ".join(t for t, _ in self._guide(context)))

    def modal(self, context, event):
        scene = context.scene
        if event.value == "PRESS" and not event.is_repeat:
            if event.type == "T" and len(self.taps) < len(scene.llb.lines):
                self.taps.append(time.perf_counter())
                scene.timeline_markers.new(project.marker_name(len(self.taps) - 1) + "*", frame=scene.frame_current)
                self._status(context)
                return {"RUNNING_MODAL"}
            if event.type == "BACK_SPACE" and self.taps:
                name = project.marker_name(len(self.taps) - 1) + "*"
                self.taps.pop()
                m = scene.timeline_markers.get(name)
                if m:
                    scene.timeline_markers.remove(m)
                self._status(context)
                return {"RUNNING_MODAL"}
        ended = self.clock.ended(context)
        if (event.type == "ESC" and event.value == "PRESS") or ended:
            self._finish(context)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def _finish(self, context):
        scene = context.scene
        _stop(context)
        self.clock.stop(context)
        self.overlay.stop()
        context.workspace.status_text_set(None)
        for m in [m for m in scene.timeline_markers if m.name.startswith(project.MARKER_PREFIX) and m.name.endswith("*")]:
            scene.timeline_markers.remove(m)
        times = self.clock.song_times(scene, self.taps)
        if not times:
            self.report({"WARNING"}, iface_("No taps were recorded"))
            return
        shift = latency_ms(context) / 1000.0
        lines = scene.llb.lines
        for i, t in enumerate(times):
            lines[i].tap_time = max(0.0, t - shift)
        project.set_line_markers(scene, range(len(times)))
        project.recompute(scene)
        self.report({"INFO"}, iface_("Recorded {} lines").format(len(times)))

    def cancel(self, context):
        self._finish(context)


def _click_wav(path, n_clicks, bpm=LATENCY_BPM, sr=48000):
    tone_n = int(sr * 0.02)
    tone = np.sin(2 * np.pi * 1500 * np.arange(tone_n) / sr) * np.linspace(1, 0, tone_n)
    pcm = np.zeros(int(sr * (n_clicks * 60.0 / bpm + 1.0)), dtype=np.float32)
    for i in range(n_clicks):
        s = int(i * 60.0 / bpm * sr)
        pcm[s:s + tone_n] += tone * (0.9 if i < LATENCY_COUNT_IN else 0.7)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())


class LLB_OT_measure_latency(bpy.types.Operator):
    bl_idname = "llb.measure_latency"
    bl_label = "Measure Latency"
    bl_description = "Press T on each click (16 clicks after a 4-click count-in) to measure the tap delay"

    def invoke(self, context, event):
        scene = context.scene
        n = LATENCY_COUNT_IN + LATENCY_TAPS
        path = os.path.join(bpy.app.tempdir, "llb_click_120bpm.wav")
        _click_wav(path, n)
        se = scene.sequence_editor or scene.sequence_editor_create()
        for s in [s for s in se.strips if s.name.startswith(CLICK_STRIP)]:
            se.strips.remove(s)                    # left over by an interrupted measurement
        self.saved = (scene.frame_start, scene.frame_end, scene.frame_current, scene.sync_mode,
                      {s.name: s.mute for s in se.strips})
        self.clip_name = None
        self.clock = _Clock()
        self.taps = []
        try:
            for s in se.strips:
                s.mute = True
            used = {s.channel for s in se.strips}
            channel = next(c for c in range(1, 129) if c not in used)
            # strip names are unique ignoring case, so keep the name Blender actually gave it
            self.clip_name = se.strips.new_sound(CLICK_STRIP, path, channel, scene.frame_start).name
            scene.frame_end = scene.frame_start + int((n * 60.0 / LATENCY_BPM + 0.5) * project.fps(scene))
            scene.sync_mode = "AUDIO_SYNC"
            self.clock.start(context)
            _play(context)
        except Exception as e:
            self._restore(context)
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        context.window_manager.modal_handler_add(self)
        self.overlay = Overlay(lambda: self._guide(bpy.context))
        self.overlay.start()
        context.workspace.status_text_set(iface_("Measure Latency  T: on each click   Esc: cancel"))
        return {"RUNNING_MODAL"}

    def _guide(self, context):
        scene = context.scene
        clicks = int((scene.frame_current - scene.frame_start) / project.fps(scene) / (60.0 / LATENCY_BPM)) + 1
        if clicks <= LATENCY_COUNT_IN:
            now = iface_("Count-in {} / {}: just listen").format(clicks, LATENCY_COUNT_IN)
        else:
            now = iface_("Press T on each click  ({} / {})").format(len(self.taps), LATENCY_TAPS)
        return [(iface_("Measure Latency"), 14), (now, 26),
                (iface_("Ends by itself after the clicks. Esc: cancel"), 12)]

    def modal(self, context, event):
        scene = context.scene
        if event.type == "T" and event.value == "PRESS" and not event.is_repeat:
            self.taps.append(time.perf_counter())
            return {"RUNNING_MODAL"}
        ended = self.clock.ended(context)
        if (event.type == "ESC" and event.value == "PRESS") or ended:
            self._finish(context, cancelled=not ended)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def _restore(self, context):
        scene = context.scene
        _stop(context)
        self.clock.stop(context)
        if getattr(self, "overlay", None):
            self.overlay.stop()
        context.workspace.status_text_set(None)
        se = scene.sequence_editor
        clip = se.strips.get(self.clip_name) if self.clip_name else None
        if clip:
            se.strips.remove(clip)
        start, end, cur, sync, mutes = self.saved
        for s in se.strips:
            if s.name in mutes:
                s.mute = mutes[s.name]
        scene.frame_start, scene.frame_end, scene.sync_mode = start, end, sync
        scene.frame_set(cur)

    def _finish(self, context, cancelled):
        scene = context.scene
        times = self.clock.song_times(scene, self.taps)
        self._restore(context)
        if cancelled:
            return
        res = tap_latency(times or [])
        if res is None:
            self.report({"WARNING"}, iface_("Too few taps on the clicks. Try again"))
            return
        med, mad, ok, out = res
        proj = scene.llb
        proj.tap_latency_ms = round(med, 1)
        proj.latency_fps = project.fps(scene)
        p = prefs.get(context)
        if p:
            p.tap_latency_ms = proj.tap_latency_ms
        self.report({"INFO"}, iface_("Latency {:.1f} ms (spread {:.1f} ms, {} taps, {} outliers)").format(med, mad, ok, out))

    def cancel(self, context):
        self._restore(context)


CLASSES = (LLB_OT_tap_sync, LLB_OT_measure_latency)
