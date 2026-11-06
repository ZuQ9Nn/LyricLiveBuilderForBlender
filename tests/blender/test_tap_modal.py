"""Tap Sync / Measure Latency modal operators driven by simulated key events (GUI Blender).

  blender --factory-startup --enable-event-simulate tests/manual/check_phase1.blend
          --python tests/blender/test_tap_modal.py -- <result file>

Opens a window for ~30 s and plays clicks; it never saves the file or the preferences.
"""
import os
import statistics
import sys
import time
import traceback

import bpy

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)
OUT = sys.argv[sys.argv.index("--") + 1]
bpy.context.preferences.use_preferences_save = False

import lyric_live_builder as llb                   # noqa: E402
from lyric_live_builder.ui import project         # noqa: E402

TAPS = [1.0, 2.5, 4.25, 6.0]                       # seconds after Tap Sync starts; the 4th is undone
log = []
failures = []
pressed = []                                       # wall clock of each simulated T


def check(cond, msg):
    log.append(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def finish():
    log.append("RESULT " + ("PASS" if not failures else f"FAIL {failures}"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n")
    os._exit(0 if not failures else 1)


def ctx():
    win = bpy.context.window_manager.windows[0]
    area = max((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == "WINDOW")
    return win, area, region


def press(key):
    if key == "T":
        pressed.append(time.perf_counter())
    win = bpy.context.window_manager.windows[0]
    win.event_simulate(type=key, value="PRESS")
    win.event_simulate(type=key, value="RELEASE")


class FrameClock:
    """The test's own (frame, wall clock) samples, independent of the operators' handler."""

    def __init__(self):
        self.samples = []
        self.last = None

    def sample(self):
        """Record when a new frame is first seen (polled every 5 ms), like frame_change_post."""
        scene = bpy.context.scene
        f = scene.frame_current
        if f > scene.frame_start and (self.last is None or f > self.last):
            self.samples.append(time.perf_counter() - (f - scene.frame_start) / project.fps(scene))
        self.last = f if self.last is None else max(self.last, f)

    def start(self):
        return statistics.median(self.samples)

    def wait(self, until=None, seconds=None):
        """Generator: sample frames while waiting for a wall clock time or a duration."""
        until = until if until is not None else time.perf_counter() + seconds
        while time.perf_counter() < until:
            self.sample()
            yield min(0.005, max(0.0, until - time.perf_counter()))

    def wait_playing(self, settle=1.0):
        """Generator: wait until playback moves (starting the audio can take seconds the first
        time a sound file is read), then sample for a while; returns the scene start wall time."""
        scene = bpy.context.scene
        t = time.perf_counter()
        for _ in range(2000):
            if scene.frame_current > scene.frame_start:
                break
            yield 0.005
        log.append(f"     playback started after {time.perf_counter() - t:.2f} s (playing={bpy.context.screen.is_animation_playing}, frame={scene.frame_current})")
        yield from self.wait(seconds=settle)
        return self.start()


def script():
    """Generator: yields seconds to wait; runs inside a timer."""
    llb.register()
    scene = bpy.context.scene
    proj = scene.llb
    txt = bpy.data.texts.new("LLB_Lyrics")
    with open(os.path.join(ROOT, "tests", "manual", "lyrics_sample.txt"), encoding="utf-8") as f:
        txt.write(f.read())
    proj.lyrics_text = txt
    win, area, region = ctx()
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.refresh()
        bpy.ops.llb.load_audio(filepath=os.path.join(ROOT, "tests", "manual", "click_120bpm.wav"))
    yield 1.0

    # ---- Tap Sync ----
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
    clock = FrameClock()
    t0 = yield from clock.wait_playing(settle=0.5)
    for t in TAPS:
        yield from clock.wait(until=t0 + t)
        press("T")
    yield 0.3
    check(len([m for m in scene.timeline_markers if m.name.endswith("*")]) == 4, "a live marker per tap")
    press("BACK_SPACE")
    yield 0.3
    press("ESC")
    yield 0.5
    taps = [ln.tap_time for ln in proj.lines]
    check(all(t >= 0 for t in taps[:3]) and all(t < 0 for t in taps[3:]), f"3 taps kept after one undo {taps[:5]}")
    # compare with when the keys were really sent (the timer itself can run late)
    gaps = [b - a for a, b in zip(taps, taps[1:3])]
    want = [b - a for a, b in zip(pressed, pressed[1:3])]
    check(all(abs(g - w) < 0.025 for g, w in zip(gaps, want)), f"tap spacing matches within 25 ms {gaps} vs {want}")
    check(abs(taps[0] - TAPS[0]) < 0.3, f"first tap near its playback time ({taps[0]:.3f} s)")
    names = sorted(m.name for m in scene.timeline_markers)
    check(names == ["LLB:1", "LLB:2", "LLB:3"], f"final markers {names}")
    check([ln.source for ln in proj.lines[:4]] == ["tap", "tap", "tap", "auto"], "tapped lines use the tap times")
    check(not bpy.context.screen.is_animation_playing, "playback stopped")
    yield 0.5

    # ---- Measure Latency ----
    # a strip whose name differs only in case (left by the phase 0 prototype) must not break the cleanup
    scene.sequence_editor.strips.new_sound("LLB_click", os.path.join(ROOT, "tests", "manual", "click_120bpm.wav"), 5, 1).mute = True
    frame_end, strips, frame_now = scene.frame_end, len(scene.sequence_editor.strips), scene.frame_current
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.measure_latency("INVOKE_DEFAULT")
    clock = FrameClock()
    t0 = yield from clock.wait_playing(settle=1.0)
    first = len(pressed)
    for k in range(4, 20):
        yield from clock.wait(until=t0 + k * 0.5 + 0.04)          # ~40 ms after each click
        press("T")
    while bpy.context.screen.is_animation_playing:             # the click track ends by itself
        yield from clock.wait(seconds=0.1)
    check(scene.frame_current == frame_now, "measurement stopped at the end instead of looping")
    yield 0.5
    # what the keys really were against the test's own frame clock
    t0 = clock.start()
    offs = sorted((p - t0 - k * 0.5) * 1000 for k, p in zip(range(4, 20), pressed[first:]))
    want = statistics.median(offs)
    check(proj.latency_measured and abs(proj.tap_latency_ms - want) < 10,
          f"latency {proj.tap_latency_ms:.1f} ms matches the keys sent ({want:.1f} ms)")
    check(scene.frame_end == frame_end and len(scene.sequence_editor.strips) == strips
          and not scene.sequence_editor.strips[project.SONG_STRIP].mute, "scene restored after measuring")

    # ---- Tap Sync below normal speed ----
    fps = project.fps(scene)
    for speed in (0.5, 0.75):
        proj.tap_speed = str(speed)
        before = (scene.render.fps, scene.render.fps_base, scene.sync_mode, scene.frame_end)
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
        start = time.perf_counter()
        for wait in (1.0, 1.0, 1.5):
            yield wait
            press("T")
        walked = (scene.frame_current - scene.frame_start) / fps
        expected = (time.perf_counter() - start) * speed
        check(abs(walked - expected) < 0.25, f"{speed}x: the frame follows the song ({walked:.2f} s, expected {expected:.2f} s)")
        check(not bpy.context.screen.is_animation_playing, f"{speed}x: the scene itself does not play")
        keys = pressed[-3:]
        yield 0.3
        press("ESC")
        yield 0.5
        taps = [ln.tap_time for ln in proj.lines[:3]]
        gaps = [b - a for a, b in zip(taps, taps[1:])]
        want = [(b - a) * speed for a, b in zip(keys, keys[1:])]
        check(all(abs(g - w) < 0.02 for g, w in zip(gaps, want)), f"{speed}x: taps are stored in song time {gaps} vs {want}")
        first = (keys[0] - start - proj.tap_latency_ms / 1000.0) * speed
        check(abs(taps[0] - first) < 0.06, f"{speed}x: first tap {taps[0]:.3f} s, expected {first:.3f} s (latency scaled)")
        check((scene.render.fps, scene.render.fps_base, scene.sync_mode, scene.frame_end) == before
              and scene.frame_current == scene.frame_start, f"{speed}x: the scene is left as it was")
    # the end of the song ends tapping by itself
    proj.tap_speed = "0.5"
    frame_end = scene.frame_end
    scene.frame_end = scene.frame_start + int(2.0 * fps)
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
    yield 1.0
    press("T")
    yield 4.0
    check(scene.frame_current == scene.frame_start and abs(proj.lines[0].tap_time - 0.5) < 0.15,
          f"tapping ends with the scene range ({proj.lines[0].tap_time:.3f} s)")
    scene.frame_end = frame_end
    # ---- changing the speed while tapping ----
    for start_speed, steps in (("0.5", ("1", "0.75")), ("1", ("0.5",))):
        proj.tap_speed = start_speed
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
        check(not bpy.ops.llb.tap_sync.poll() and not bpy.ops.llb.measure_latency.poll() and bpy.ops.llb.tap_stop.poll(),
              f"from {start_speed}x: tapping cannot be started twice, the stop button is there")
        t0 = time.perf_counter()
        marks = [(t0, float(start_speed))]                         # (wall, speed from then on)
        yield 1.0
        for speed in steps:
            press("T")                                             # a pair of taps on each side of the change
            yield 0.4
            press("T")
            proj.tap_speed = speed
            marks.append((time.perf_counter(), float(speed)))
            yield 1.0
        press("T")
        yield 0.4
        press("T")
        yield 0.3
        check(not bpy.context.screen.is_animation_playing, f"from {start_speed}x: the song goes on on the audio device")
        bpy.ops.llb.tap_stop()
        yield 0.5
        keys = pressed[-2 * len(marks):]
        taps = [ln.tap_time for ln in proj.lines[:len(keys)]]
        # inside one speed the taps are exact
        got = [taps[k + 1] - taps[k] for k in range(0, len(taps), 2)]
        want = [(keys[k + 1] - keys[k]) * m[1] for k, m in zip(range(0, len(keys), 2), marks)]
        check(all(abs(g - w) < 0.02 for g, w in zip(got, want)), f"from {start_speed}x: spacing at each speed {got} vs {want}")
        # across a change the song only loses the moment it takes to restart
        ideal = [sum(max(0.0, min(b, k) - a) * sp for (a, sp), b in zip(marks, [m[0] for m in marks[1:]] + [k]))
                 - proj.tap_latency_ms / 1000.0 * marks[i // 2][1] for i, k in enumerate(keys)]
        late = [ideal[i] - taps[i] for i in range(len(keys))]
        check(all(-0.05 < x < 0.2 * (i // 2) + 0.05 for i, x in enumerate(late)), f"from {start_speed}x: position kept across changes {late}")
        check(bpy.ops.llb.tap_sync.poll() and not bpy.ops.llb.tap_stop.poll() and scene.frame_current == scene.frame_start,
              f"from {start_speed}x: the stop button ends it")
    # undo reaches taps made before the change
    keep = proj.lines[1].tap_time
    proj.tap_speed = "1"
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
    yield 1.0
    press("T")
    proj.tap_speed = "0.5"
    yield 0.5
    press("T")
    yield 0.1
    press("BACK_SPACE")
    yield 0.1
    press("BACK_SPACE")
    yield 0.2
    press("T")
    yield 0.2
    press("ESC")
    yield 0.5
    check(proj.lines[1].tap_time == keep and proj.lines[0].tap_time < 0.5, f"undo reaches across a speed change and jumps back ({proj.lines[0].tap_time:.3f} s)")
    # ---- countdown ----
    proj.tap_speed, proj.tap_countdown = "1", True
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
    yield 0.3
    press("T")                                                 # too early: ignored
    yield 0.3
    check(not bpy.context.screen.is_animation_playing and bpy.ops.llb.tap_stop.poll(), "the song waits for the countdown")
    yield 1.8
    check(bpy.context.screen.is_animation_playing, "the song starts after the countdown")
    yield 0.8
    press("T")
    yield 0.2
    press("ESC")
    yield 0.5
    check(0.3 < proj.lines[0].tap_time < 1.3, f"a tap during the countdown does not count ({proj.lines[0].tap_time:.3f} s)")
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
    yield 0.3
    bpy.ops.llb.tap_stop()
    yield 0.3
    check(bpy.ops.llb.tap_sync.poll() and not bpy.context.screen.is_animation_playing, "the stop button ends the countdown")
    proj.tap_countdown = False

    # ---- tapping from a line ----
    for k, t in enumerate((1.0, 2.0, 3.0, 2.3, 5.0)):
        proj.lines[k].tap_time = t
    project.recompute(scene)
    lead = proj.lines[1].start + 0.01
    times_before = (proj.lines[0].tap_time, proj.lines[1].tap_time)
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.tap_sync("INVOKE_DEFAULT", first_line=2)
    start = time.perf_counter()
    yield 0.5
    press("T")
    key = pressed[-1]
    walked = (scene.frame_current - scene.frame_start) / fps
    check(abs(walked - (lead + 0.5)) < 0.2, f"playback starts just after the previous line ({walked:.2f} s)")
    yield 0.2
    press("ESC")
    yield 0.5
    t = proj.lines[2].tap_time
    check(abs(t - (lead + key - start - proj.tap_latency_ms / 1000.0)) < 0.12, f"the tap lands on the chosen line ({t:.3f} s)")
    check((proj.lines[0].tap_time, proj.lines[1].tap_time) == times_before, "earlier lines keep their times")
    check(proj.lines[3].tap_time < 0 and abs(proj.lines[4].tap_time - 5.0) < 1e-6, "a later tap that would now come first goes, the others stay")

    # ---- undo jumps back ----
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
    yield 4.0
    press("T")
    yield 0.3
    press("BACK_SPACE")
    yield 0.3
    walked = (scene.frame_current - scene.frame_start) / fps
    check(0.8 < walked < 2.2, f"undo jumps back about 3 s ({walked:.2f} s)")
    yield 0.7
    press("T")
    yield 0.2
    press("ESC")
    yield 0.5
    t = proj.lines[0].tap_time
    check(1.2 < t < 3.2, f"the line is tapped again ({t:.3f} s)")

    # no song to slow down: normal speed
    song_path, proj.audio_path = proj.audio_path, ""
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.llb.tap_sync("INVOKE_DEFAULT")
    yield 0.5
    check(bpy.context.screen.is_animation_playing, "without a song the scene plays at normal speed")
    press("ESC")
    yield 0.5
    proj.audio_path, proj.tap_speed = song_path, "1"
    finish()


def run():
    gen = script()

    def step():
        try:
            return next(gen)
        except StopIteration:
            finish()
        except Exception:
            log.append(traceback.format_exc())
            failures.append("exception")
            finish()
    bpy.app.timers.register(step, first_interval=2.0)


run()
