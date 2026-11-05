"""Tap Sync and tap latency measurement (modal operators).

Taps store time.perf_counter(); a frame_change_post handler pairs played frames with the same
clock, and the median of (wall - song time) maps taps to song time. This removes the one-frame
jitter of AUDIO_SYNC playback and gives sub-frame precision (prototype S0-08).

Below normal speed the scene does not play at all (it has no playback speed): _SlowClock plays the
song stretched, pitch kept, straight on the audio device and moves the frame along with it. Changing
the speed while tapping restarts the song from its current place, also on _SlowClock (even at 1×).
"""
import os
import statistics
import time
import wave

import aud
import bpy
import numpy as np
from bpy.app.translations import pgettext_iface as iface_

from .. import prefs
from ..core.timing import LATENCY_BPM, LATENCY_COUNT_IN, LATENCY_TAPS, tap_latency
from . import project
from .overlay import Overlay

CLICK_STRIP = "LLB_Click"
_current = None                  # the running Tap Sync or Measure Latency: only one at a time


def tapping():
    return isinstance(_current, LLB_OT_tap_sync)


def _redraw(context):
    for area in context.screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()


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


class _SlowClock:
    """Tap Sync on the audio device. The handle's position runs in real time whatever the stretch, so
    the song's own time is offset + position × speed. Same interface as _Clock, plus tick() on timer events."""

    def __init__(self, path, speed, volume, offset=0.0):
        self.path, self.speed, self.volume, self.offset = path, speed, volume, offset
        self.pairs = []
        self.done = False
        self.timer = None
        self.handle = None

    def start(self, context):
        sound = aud.Sound(self.path)
        if self.offset > 0.0:
            sound = sound.limit(self.offset, 1e6)         # to the end of the file
        # always stretched, even at 1×: a limited sound alone reports a wrong position (-44739 s)
        sound = sound.timeStretchPitchScale(1.0 / self.speed, 1.0, aud.STRETCHER_QUALITY_HIGH, False)
        self.started = time.perf_counter()
        self.handle = aud.Device().play(sound)
        self.handle.volume = self.volume
        self.timer = context.window_manager.event_timer_add(0.05, window=context.window)

    def stop(self, context):
        if self.handle.status:
            self.handle.stop()
        context.window_manager.event_timer_remove(self.timer)
        self.timer = None

    def tick(self, scene):
        if not self.handle.status:
            return
        position = self.handle.position
        if position > 0.0:                                # still 0 until the device starts it
            self.pairs.append((time.perf_counter(), position))
        frame = scene.frame_start + int((self.offset + position * self.speed) * project.fps(scene))
        if frame >= scene.frame_end:
            self.done = True
        scene.frame_set(min(frame, scene.frame_end))

    def ended(self, context):
        return self.done or not self.handle.status

    def song_times(self, scene, walls):
        c = statistics.median(t - p for t, p in self.pairs) if self.pairs else self.started
        return [self.offset + (w - c) * self.speed for w in walls]


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
        return _current is None and len(context.scene.llb.lines) > 0

    def invoke(self, context, event):
        global _current
        # the frame clock has a bias of up to one frame; it cancels only at the measuring frame rate
        proj, f = context.scene.llb, project.fps(context.scene)
        if proj.latency_measured and proj.latency_fps > 0 and abs(proj.latency_fps - f) > 0.01:
            self.report({"WARNING"}, iface_("Latency was measured at {:g} fps, the scene is {:g} fps. Measure it again")
                        .format(proj.latency_fps, f))
        scene, self.speed = context.scene, float(proj.tap_speed)
        path = bpy.path.abspath(proj.audio_path) if proj.audio_path else ""
        self.path = path if os.path.isfile(path) else ""       # no song: no speeds to change to
        if self.speed < 1.0 and not self.path:
            self.report({"WARNING"}, iface_("There is no song to slow down: Tap Sync runs at normal speed"))
            self.speed = 1.0
        self.taps = []                                         # wall clock, on the current clock
        self.song = []                                         # song time, settled when a clock ends
        self.stop_asked = False
        if self.speed < 1.0:
            _stop(context)
            scene.frame_set(scene.frame_start)
            self._slow_clock(context, 0.0)
        else:
            self.clock = _Clock()
            self.clock.start(context)
            _play(context)
        _current = self
        _redraw(context)
        context.window_manager.modal_handler_add(self)
        self.overlay = Overlay(lambda: self._guide(bpy.context))
        self.overlay.start()
        self._status(context)
        return {"RUNNING_MODAL"}

    def _slow_clock(self, context, offset):
        scene = context.scene
        strip = scene.sequence_editor.strips.get(project.SONG_STRIP) if scene.sequence_editor else None
        self.clock = _SlowClock(self.path, self.speed, scene.audio_volume * (strip.volume if strip else 1.0), offset)
        self.clock.start(context)

    def _settle(self, context):
        """The taps of the clock ending now -> song times. A delay in real time is shorter in song time."""
        times = self.clock.song_times(context.scene, self.taps) or []
        shift = latency_ms(context) / 1000.0 * self.speed
        self.song += [max(0.0, t - shift) for t in times]
        self.taps = []

    def _change_speed(self, context, speed):
        """Go on from the same place in the song at the new speed."""
        now = self.clock.song_times(context.scene, [time.perf_counter()])
        if now is None:
            return                                             # just started: the next timer event tries again
        self._settle(context)
        self.clock.stop(context)
        _stop(context)
        self.speed = speed
        self._slow_clock(context, now[0])
        self._status(context)

    def _guide(self, context):
        lines = context.scene.llb.lines
        k = len(self.song) + len(self.taps)
        nxt = lines[k].text if k < len(lines) else iface_("All lines recorded (Esc)")
        speed = f"  {self.speed:g}×" if self.speed < 1.0 else ""
        return [(iface_("Tap Sync  next line {} / {}").format(min(k + 1, len(lines)), len(lines)) + speed, 14),
                (nxt, 26),
                (iface_("T: line start   Backspace: undo   Esc: finish"), 12)]

    def _status(self, context):
        context.workspace.status_text_set("   ".join(t for t, _ in self._guide(context)))

    def modal(self, context, event):
        scene = context.scene
        direct = isinstance(self.clock, _SlowClock)
        if self.stop_asked:
            self._finish(context)
            return {"FINISHED"}
        if event.type == "TIMER":
            wanted = float(scene.llb.tap_speed)
            if self.path and wanted != self.speed:
                self._change_speed(context, wanted)
            elif direct:
                self.clock.tick(scene)
        elif direct and event.type == "SPACE":
            return {"RUNNING_MODAL"}                      # scene playback would start the song a second time
        tapped = len(self.song) + len(self.taps)
        if event.value == "PRESS" and not event.is_repeat:
            if event.type == "T" and tapped < len(scene.llb.lines):
                self.taps.append(time.perf_counter())
                scene.timeline_markers.new(project.marker_name(tapped) + "*", frame=scene.frame_current)
                self._status(context)
                return {"RUNNING_MODAL"}
            if event.type == "BACK_SPACE" and tapped:
                name = project.marker_name(tapped - 1) + "*"
                (self.taps or self.song).pop()
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
        global _current
        _current = None
        scene = context.scene
        direct = isinstance(self.clock, _SlowClock)
        _stop(context)
        self.clock.stop(context)
        if direct:
            scene.frame_set(scene.frame_start)
        self.overlay.stop()
        context.workspace.status_text_set(None)
        for m in [m for m in scene.timeline_markers if m.name.startswith(project.MARKER_PREFIX) and m.name.endswith("*")]:
            scene.timeline_markers.remove(m)
        _redraw(context)
        self._settle(context)
        if not self.song:
            self.report({"WARNING"}, iface_("No taps were recorded"))
            return
        lines = scene.llb.lines
        for i, t in enumerate(self.song):
            lines[i].tap_time = t
        project.set_line_markers(scene, range(len(self.song)))
        project.recompute(scene)
        self.report({"INFO"}, iface_("Recorded {} lines").format(len(self.song)))

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


class LLB_OT_tap_stop(bpy.types.Operator):
    bl_idname = "llb.tap_stop"
    bl_label = "Finish Tapping"
    bl_description = "End Tap Sync and keep the taps so far (the same as Esc)"

    @classmethod
    def poll(cls, context):
        return tapping()

    def execute(self, context):
        _current.stop_asked = True                        # the modal finishes on its next timer event
        return {"FINISHED"}


class LLB_OT_measure_latency(bpy.types.Operator):
    bl_idname = "llb.measure_latency"
    bl_label = "Measure Latency"
    bl_description = "Press T on each click (16 clicks after a 4-click count-in) to measure the tap delay"

    @classmethod
    def poll(cls, context):
        return _current is None

    def invoke(self, context, event):
        global _current
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
        _current = self
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
        global _current
        _current = None
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


CLASSES = (LLB_OT_tap_sync, LLB_OT_tap_stop, LLB_OT_measure_latency)
