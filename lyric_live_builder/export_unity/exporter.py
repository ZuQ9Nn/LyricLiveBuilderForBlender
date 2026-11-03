"""Writes one song into a Unity project (design §9.1): manifest, meshes, textures, audio, the
build scripts (Editor/, Runtime/) and the marker that tells Unity to build."""
import json
import os
import re
import shutil

import bpy
import numpy as np

from ..core import atlas, meshes
from ..core.parts import particles as pts
from ..text import glyphs
from . import manifest, meshbin

MARKER = "_llb_build.pending"          # not "_pending.llb": the phase 0 prototype in the test project watches that
TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")
GENERATOR = "LyricLiveBuilderForBlender"


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip().strip(".")
    return re.sub(r"\s+", "_", name) or "Song"


def song_folder(project, name):
    return os.path.join(project, "Assets", "LyricLive", "Songs", safe_name(name))


def _template_version(folder):
    try:
        with open(os.path.join(folder, "version.txt"), encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def install_templates(project):
    """Copy Editor/ and Runtime/ when the project's copy is missing or older. Returns copied folder names."""
    copied = []
    for part in ("Editor", "Runtime"):
        src = os.path.join(TEMPLATES, part)
        dst = os.path.join(project, "Assets", "LyricLive", part)
        if _template_version(dst) >= _template_version(src):
            continue
        if os.path.isdir(dst):
            for root, _, files in os.walk(src):            # overwrite ours, keep anything the user added
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), src)
                    os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
                    shutil.copy2(os.path.join(root, f), os.path.join(dst, rel))
        else:
            shutil.copytree(src, dst)
        copied.append(part)
    return copied


def _glyph_arrays(me):
    v = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", v)
    return v.reshape(-1, 3), [tuple(p.vertices) for p in me.polygons]


def pack_meshes(baked, font_paths, resolution=6):
    """All meshes the nodes and particle systems use -> meshbin.Pack."""
    pack = meshbin.Pack()
    keys = dict(baked.meshes)
    for e in baked.emitters:
        shape = e["spec"]["preset"]["shape"]
        if shape in pts.SHAPES_3D:
            keys.setdefault(f"shape:{shape}", None)
    for key, src in keys.items():
        if src is not None and src.kind in ("glyph2d", "glyph3d"):
            a = src.args
            path = glyphs.font_for_char(font_paths(a["role"]), a["char"])
            if path is None:
                continue                                 # no font has it: the node stays empty
            me = glyphs.glyph_mesh(path, a["char"], src.kind == "glyph3d", a["depth"], a["bevel"], resolution)
            v, f = _glyph_arrays(me)
            pack.add(key, meshbin.encode(v, f, flat=src.kind == "glyph3d"))
        else:
            v, f = meshes.build(key)
            pack.add(key, meshbin.encode(v, f, flat=key.startswith("shape:")))
    return pack


def dome_params(baked):
    """Initial dome material values (the clips set them again from time 0)."""
    out = []
    for tr in baked.tracks:
        if tr.node == "dome" and tr.prop.startswith("dome:"):
            b = manifest.binding("dome", tr.prop, tr.values[:1])
            if b:
                out.append({"name": b[1].split(".", 1)[1], "values": [float(x) for x in b[3][0]]})
    return out


def export(project, name, baked, plan, sections, font_paths, audio_path="", panorama_path="", title="",
           options=None, version=""):
    """Write the song folder. Returns its path. The caller has checked for overwrites."""
    folder = song_folder(project, name)
    gen = os.path.join(folder, "Generated")
    os.makedirs(folder, exist_ok=True)
    for sub in ("textures", "audio"):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    pack = pack_meshes(baked, font_paths)
    with open(os.path.join(folder, "meshes.bin"), "wb") as f:
        f.write(pack.bytes())
    with open(os.path.join(folder, "textures", "particles_atlas.png"), "wb") as f:
        f.write(atlas.png_bytes(atlas.draw(1024)))
    audio = ""
    if audio_path and os.path.isfile(audio_path):
        audio = "audio/" + safe_name(os.path.basename(audio_path))
        shutil.copy2(audio_path, os.path.join(folder, audio))
    pano = ""
    if panorama_path and os.path.isfile(panorama_path):
        pano = "textures/panorama" + os.path.splitext(panorama_path)[1].lower()
        shutil.copy2(panorama_path, os.path.join(folder, pano))
    opts = {"materialMode": "VRCHAT", "panorama": pano, "generator": f"{GENERATOR} {version}"}
    opts.update(options or {})
    song = {"title": title or name, "artist": "", "audio": audio, "duration": float(plan.duration),
            "bpm": float(plan.bpm or 0.0)}
    doc = manifest.build(baked, plan, sections, pack.entries, song, opts, dome_params(baked))
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    install_templates(project)
    with open(os.path.join(folder, MARKER), "w", encoding="utf-8") as f:
        f.write(name)                                    # written last: Unity builds when it sees this
    return folder, os.path.isdir(gen)
