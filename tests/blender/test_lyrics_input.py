"""Lyric input: external editor, clipboard, file (GUI Blender: timers and the clipboard need a window).

  blender --factory-startup --python tests/blender/test_lyrics_input.py -- <result file>
"""
import os
import sys
import time
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, HERE]
OUT = sys.argv[sys.argv.index("--") + 1]

import lyric_live_builder as llb                                     # noqa: E402
from lyric_live_builder.ui import operators_input as oi              # noqa: E402
from lyric_live_builder.ui import tap_sync                           # noqa: E402

log, failures = [], []


def check(ok, msg):
    log.append(("OK   " if ok else "FAIL ") + msg)
    if not ok:
        failures.append(msg)


def finish():
    log.append("RESULT " + ("PASS" if not failures else f"FAIL {failures}"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    bpy.app.timers.register(quit_blender, first_interval=0.2)


def quit_blender():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        bpy.ops.wm.quit_blender()


def texts(proj):
    return [ln.text for ln in proj.lines]


def save(path, text, encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(text)


def steps():
    scene = bpy.context.scene
    proj = scene.llb
    wm = bpy.context.window_manager
    win = wm.windows[0]
    ops = bpy.context.temp_override(window=win)

    # ---- clipboard ----
    wm.clipboard = "夜明けの色を覚えてる\r\n光の粒を集めて\r\n"
    with ops:
        r = bpy.ops.llb.paste_lyrics("EXEC_DEFAULT")
    check(r == {"FINISHED"} and texts(proj) == ["夜明けの色を覚えてる", "光の粒を集めて"], "Japanese pasted from the clipboard")
    check("\r" not in proj.lyrics_text.as_string(), "Windows line ends are dropped")
    wm.clipboard = "  \n"
    with ops:
        r = bpy.ops.llb.paste_lyrics("EXEC_DEFAULT")
    check(r == {"CANCELLED"} and len(proj.lines) == 2, "an empty clipboard changes nothing")

    # ---- file ----
    folder = bpy.app.tempdir
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "cp932"):
        path = os.path.join(folder, f"lyrics_{encoding}.txt")
        save(path, f"[サビ]\n{encoding}の歌詞です\n二行目\n", encoding)
        with ops:
            r = bpy.ops.llb.load_lyrics("EXEC_DEFAULT", filepath=path)
        check(r == {"FINISHED"} and texts(proj) == [f"{encoding}の歌詞です", "二行目"], f"file in {encoding}")

    # ---- external editor ----
    opened = []
    oi._open_file = opened.append
    proj.lines[1].tap_time = 12.5
    with ops:
        r = bpy.ops.llb.edit_lyrics()
    path = opened[0] if opened else ""
    check(r == {"FINISHED"} and oi.watching(), "the file is opened and watched")
    with open(path, "rb") as f:
        check(f.read().decode("utf-8-sig") == proj.lyrics_text.as_string(), "the file holds the current lyrics")
    yield 1.2
    check(texts(proj) == ["cp932の歌詞です", "二行目"], "no save, no change")

    # a save still going on is not read
    for k in range(1, 8):
        save(path, "新しい最初の行\n二行目\n" + "".join(f"追加{i}\n" for i in range(k)))
        check(len(proj.lines) == 2, f"still writing ({k})")
        yield 0.2
    yield 1.4
    check(texts(proj)[:2] == ["新しい最初の行", "二行目"] and len(proj.lines) == 9, "the finished save is taken in")
    check(proj.lines[1].tap_time == 12.5, "the tap stays with its line")
    check(proj.lyrics_text.as_string().startswith("新しい最初の行"), "the Blender text follows")

    # Shift_JIS save, emptied file, tapping
    save(path, "シフトJISの行\n二行目\n", "cp932")
    yield 1.6
    check(texts(proj) == ["シフトJISの行", "二行目"], "a Shift_JIS save is read")
    save(path, "")
    yield 1.6
    check(len(proj.lines) == 2, "an emptied file is ignored")
    idle, tap_sync.tapping = tap_sync.tapping, lambda: True
    save(path, "タップの間の保存\n")
    yield 1.6
    check(len(proj.lines) == 2, "nothing changes while tapping")
    tap_sync.tapping = idle
    yield 1.6
    check(texts(proj) == ["タップの間の保存"], "the save is taken in after tapping")

    # ---- the confirmation exists in both Blender versions ----
    win, area, region = next((win, a, next(r for r in a.regions if r.type == "WINDOW"))
                             for a in win.screen.areas if a.type == "VIEW_3D")
    with bpy.context.temp_override(window=win, area=area, region=region):
        r = bpy.ops.llb.paste_lyrics("INVOKE_DEFAULT")
    check(bool(r), f"Paste asks first when there are lyrics {r}")
    llb.unregister()
    check(not bpy.app.timers.is_registered(oi.watch_tick), "unregistering stops the watch")
    finish()


def run():
    try:
        delay = next(GEN)
    except StopIteration:
        return None
    except Exception:
        log.append(traceback.format_exc())
        failures.append("exception")
        finish()
        return None
    return delay


llb.register()
GEN = steps()
bpy.app.timers.register(run, first_interval=1.0)
