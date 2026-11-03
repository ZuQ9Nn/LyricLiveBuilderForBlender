"""Shared helpers of the Blender integration tests."""
import ast
import glob
import os
import sys
import wave

import bpy
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

failures = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def font_arg():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--font" in argv:
        return argv[argv.index("--font") + 1]
    for p in (r"C:\Windows\Fonts\BIZ-UDGothicR.ttc", r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msgothic.ttc"):
        if os.path.isfile(p):
            return p
    raise SystemExit("pass a Japanese font with -- --font <path>")


def text_objects():
    """{node id: object} of the lyric glyphs and line groups in the preview."""
    root = bpy.data.collections.get("LyricLive")
    return {ob["llb_node"]: ob for ob in root.all_objects if "llb_node" in ob and ob["llb_node"].startswith("line")}


def setup(lyrics_text, font):
    scene = bpy.context.scene
    proj = scene.llb
    text = proj.lyrics_text or bpy.data.texts.new("LLB_Lyrics")
    text.from_string(lyrics_text)
    proj.lyrics_text = text
    proj.font_body.filepath = font
    bpy.ops.llb.refresh()
    return scene, proj


def prefs_cls():
    from lyric_live_builder.prefs import LLBPreferences
    return LLBPreferences


def translation_checks():
    from lyric_live_builder import i18n, props, ui
    from lyric_live_builder.i18n import ja_JP
    msgids = set()
    for cls in ui.CLASSES + props.CLASSES + (prefs_cls(),):
        for attr in ("bl_label", "bl_description"):
            v = getattr(cls, attr, "")
            if v:
                msgids.add(v)
    for cls in props.CLASSES + (prefs_cls(),):            # only our own property groups
        for prop in cls.bl_rna.properties:
            if prop.identifier in ("rna_type", "name") or prop.name == prop.identifier:
                continue                                  # unnamed internal properties are not shown
            msgids.update(x for x in (prop.name, prop.description) if x)
            for item in getattr(prop, "enum_items", []):
                msgids.update(x for x in (item.name, item.description) if x)
    # literal strings shown through text= / labels() / iface_() in the UI modules
    for path in glob.glob(os.path.join(ROOT, "lyric_live_builder", "ui", "*.py")):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = getattr(node.func, "id", getattr(node.func, "attr", ""))
                args = list(node.args)
                if fn in ("iface_", "labels") and args:
                    a = args[0] if fn == "iface_" else (args[1] if len(args) > 1 else None)
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        msgids.add(a.value)
                for kw in node.keywords:
                    if kw.arg == "text" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        msgids.add(kw.value.value)
                    if kw.arg == "text" and isinstance(kw.value, ast.IfExp):
                        for b in (kw.value.body, kw.value.orelse):
                            if isinstance(b, ast.Constant):
                                msgids.add(b.value)
    from lyric_live_builder.ui import panels
    msgids.update(m for _, m in panels.NOTATION)
    msgids.update(panels.ROLE_LABELS.values())
    msgids = {m for m in msgids if m and sum(c.isalpha() for c in m) >= 2 and not m[0].isdigit()
              and m not in ("BPM", "LRC")}
    missing = sorted(m for m in msgids if m not in ja_JP.MESSAGES)
    check(not missing, f"every UI message has a Japanese translation {missing}")
    bpy.context.preferences.view.language = "ja_JP"
    bpy.context.preferences.view.use_translate_interface = True
    clash = [k for k, v in ja_JP.MESSAGES.items() if bpy.app.translations.pgettext_iface(k) != v]
    check(not clash, f"no message is overridden by Blender's own translation {clash}")
    bpy.context.preferences.view.language = "en_US"


def song(path, seconds=70.0, sr=22050):
    t = np.arange(int(sr * seconds)) / sr
    x = (np.sin(2 * np.pi * 440 * t) * 0.2 * (1 + 0.8 * (np.sin(t * 0.4) > 0))).astype(np.float32)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())
