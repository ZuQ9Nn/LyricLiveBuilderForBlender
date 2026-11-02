"""S0-08: tap latency measurement (prototype).

Run this script inside Blender (Text Editor > Run Script). It adds a sidebar tab "LLB試作"
with a "遅延の測定" button: a 120 BPM click track plays and the user taps T on each click.
Each tap stores time.perf_counter(); a frame_change_post handler pairs frames with the same
clock, and the median of (wall - song time) over all frames maps taps to song time (this removes
the one-frame jitter of AUDIO_SYNC). Key repeats are ignored, taps more than OUTLIER_MS from a
click are reported as outliers, and the latency is the median of the remaining offsets.
"""
import os
import statistics
import time
import wave

import bpy
import numpy as np

BPM = 120.0
CLICKS = 24          # 12 s; the first 4 clicks are a count-in and are ignored
FPS = 60
OUTLIER_MS = 150.0
WAV_NAME = "click_120bpm.wav"


def click_wav_path():
    base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else bpy.app.tempdir
    return os.path.join(base, WAV_NAME)


def ensure_click_track(scene):
    path = click_wav_path()
    if not os.path.exists(path):
        sr = 48000
        n = int(sr * (CLICKS * 60.0 / BPM + 1.0))
        pcm = np.zeros(n, dtype=np.float32)
        tone = np.sin(2 * np.pi * 1500 * np.arange(int(sr * 0.02)) / sr) * np.linspace(1, 0, int(sr * 0.02))
        for i in range(CLICKS):
            s = int(i * 60.0 / BPM * sr)
            pcm[s:s + tone.size] += tone * 0.8
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((pcm * 32767).astype("<i2").tobytes())
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = int((CLICKS * 60.0 / BPM + 1.0) * FPS)
    scene.sync_mode = "AUDIO_SYNC"
    se = scene.sequence_editor or scene.sequence_editor_create()
    strips = se.strips if hasattr(se, "strips") else se.sequences
    if not any(s.name == "LLB_click" for s in strips):
        strips.new_sound("LLB_click", path, channel=1, frame_start=1)


_frame_clock = []


def _on_frame(scene, _depsgraph=None):
    _frame_clock.append((scene.frame_current, time.perf_counter()))


def _wall_to_song_offset(scene):
    """Median of (wall clock - song time) over the recorded frames."""
    fps = scene.render.fps / scene.render.fps_base
    return statistics.median(t - (f - scene.frame_start) / fps for f, t in _frame_clock)


class LLB_OT_proto_tap_latency(bpy.types.Operator):
    bl_idname = "llb_proto.tap_latency"
    bl_label = "遅延の測定"
    bl_description = "クリック音に合わせて T を押してください（Esc で中止）"

    def invoke(self, context, event):
        scene = context.scene
        ensure_click_track(scene)
        self.taps = []
        _frame_clock.clear()
        if _on_frame not in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.append(_on_frame)
        scene.frame_set(scene.frame_start)
        bpy.ops.screen.animation_play()
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "クリック音に合わせて T を押してください")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        scene = context.scene
        if event.type == "T" and event.value == "PRESS" and not event.is_repeat:
            self.taps.append(time.perf_counter())
            return {"RUNNING_MODAL"}
        done = scene.frame_current >= scene.frame_end - 1 or not context.screen.is_animation_playing
        if event.type == "ESC" or done:
            if context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=True)
            bpy.app.handlers.frame_change_post.remove(_on_frame)
            self._finish(scene)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def _finish(self, scene):
        if not _frame_clock:
            self.report({"WARNING"}, "再生のフレームを記録できませんでした")
            return
        beat = 60.0 / BPM
        c = _wall_to_song_offset(scene)
        raw, offsets = [], []
        for t in self.taps:
            song = t - c
            k = round(song / beat)
            if 4 <= k < CLICKS:
                off = (song - k * beat) * 1000
                raw.append(round(off, 1))
                if abs(off) <= OUTLIER_MS:
                    offsets.append(off)
        scene["llb_latency_raw"] = raw
        if len(offsets) < 8:
            self.report({"WARNING"}, f"有効なタップが少なすぎます（{len(offsets)} 回）")
            return
        med = statistics.median(offsets)
        mad = statistics.median(abs(o - med) for o in offsets)
        runs = list(scene.get("llb_latency_runs", []))
        runs.append(round(med, 1))
        scene["llb_latency_runs"] = runs
        self.report({"INFO"}, f"遅延 {med:.1f} ms（ばらつき MAD {mad:.1f} ms、有効 {len(offsets)} 回、外れ {len(raw) - len(offsets)} 回）")


class LLB_PT_proto(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LLB試作"
    bl_label = "S0-08 タップの遅延"

    def draw(self, context):
        col = self.layout.column()
        col.operator(LLB_OT_proto_tap_latency.bl_idname)
        runs = context.scene.get("llb_latency_runs", [])
        for i, r in enumerate(runs):
            col.label(text=f"{i + 1} 回目: {r} ms")
        if len(runs) >= 2:
            col.label(text=f"回ごとの差: {max(runs) - min(runs):.1f} ms")


def register():
    for c in (LLB_OT_proto_tap_latency, LLB_PT_proto):
        old = getattr(bpy.types, c.__name__, None)
        if old:                       # re-running the text block replaces the old version
            bpy.utils.unregister_class(old)
        bpy.utils.register_class(c)


if __name__ == "__main__":
    register()
