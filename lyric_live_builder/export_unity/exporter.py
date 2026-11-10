"""Writes one song into a Unity project (design §9.1): manifest, meshes, textures, audio, the
build scripts (Editor/, Runtime/) and the marker that tells Unity to build."""
import json
import os
import re
import shutil

import bpy
import numpy as np

from ..core import atlas, meshes
from ..core.parts import lines, particles as pts
from ..text import glyphs
from ..mesh_optimizer import api as mo
from ..preview import gimmick_assets
from . import convert, manifest, meshbin, particles_unity

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


def _letter(path, src, mobile):
    """(verts, faces, flat) of one cleaned letter (design §11.2): mobile lowers the curve resolution
    until the letter fits its triangle budget; 3D letters are then extruded without a bevel."""
    a = src.args
    solid = src.kind == "glyph3d"
    if mobile:
        def make(res):
            return glyphs.glyph_mesh(path, a["char"], False, 0.0, 0.0, res).copy()
        me, _ = mo.fit_text_mesh(make, max_tris=mo.LIMITS["solid" if solid else "flat"],
                                 depth=a["depth"] if solid else 0.0, **_mobile_args())
    else:
        def make(res):
            return glyphs.glyph_mesh(path, a["char"], solid, a["depth"], a["bevel"], res).copy()
        me, _ = mo.fit_text_mesh(make, max_tris=10 ** 9, resolutions=(mo.DEFAULTS["normal"]["resolution"],),
                                 dissolve_angle_deg=mo.DEFAULTS["normal"]["angle"])
    v, f = _glyph_arrays(me)
    bpy.data.meshes.remove(me)
    return v, f, solid


def _mobile_args():
    m = mo.DEFAULTS["mobile"]
    return {"resolutions": tuple(range(m["resolution"], 1, -1)), "dissolve_angle_deg": m["angle"]}


def _line(parts, letters):
    """One mesh of a still line in its group's space, letter colours per vertex (design §11.3)."""
    from ..core import xform
    verts, faces, cols, flat = [], [], [], False
    for key, loc, rot, em, rgb in parts:
        if key not in letters:
            continue
        v, f, solid = letters[key]
        flat |= solid
        base = sum(len(x) for x in verts)
        verts.append(np.asarray(loc) + xform.rotate(np.asarray(rot), v * em))
        faces += [tuple(i + base for i in face) for face in f]
        cols.append(np.tile(list(convert.srgb(rgb)) + [1.0], (len(v), 1)))
    if not verts:
        return None
    return np.concatenate(verts), faces, flat, np.concatenate(cols)


def tmp_fonts(baked, font_paths):
    """Flat letters that become TextMesh Pro: ({glyph mesh key: font key}, [{key, file, chars, path}])."""
    by_key, fonts = {}, {}
    for key, src in baked.meshes.items():
        if src.kind != "glyph2d":
            continue
        path = glyphs.font_for_char(font_paths(src.args["role"]), src.args["char"])
        if path is None:
            continue
        fk = safe_name(os.path.splitext(os.path.basename(path))[0])
        # "_": TextMesh Pro looks it up for underlines and warns on every letter when the atlas lacks it
        f = fonts.setdefault(fk, {"key": fk, "file": "fonts/" + safe_name(os.path.basename(path)), "chars": "_", "path": path})
        if src.args["char"] not in f["chars"]:
            f["chars"] += src.args["char"]
        by_key[key] = fk
    return by_key, list(fonts.values())


def pack_meshes(baked, font_paths, mobile=False, skip=()):
    """All meshes the nodes and particle systems use -> (meshbin.Pack, {key: triangles}).
    skip: keys not needed (letters that become TextMesh Pro)."""
    pack, tris, letters = meshbin.Pack(), {}, {}
    keys = dict(baked.meshes)
    for e in baked.emitters:
        for shape in pts.shapes_of(e["spec"]["preset"]):
            if shape in pts.SHAPES_3D:
                keys.setdefault(f"shape:{shape}", None)
    order = sorted(keys, key=lambda k: k.startswith("line:"))          # letters before the lines made of them

    def add(key, data):
        pack.add(key, data)
        tris[key] = meshbin.decode(data)[2].size // 3
    for e in baked.emitters:                             # line effects: one mesh per emitter (design §8.1)
        p = e["spec"]["preset"]
        if lines.is_lines(p):
            v, f, col, uv4 = particles_unity.line_mesh(lines.geometry(p, e["spec"]["seed"], e["spec"]["colors"]))
            add(particles_unity.line_key(e["node"]), meshbin.encode(v, f, colors=col, uv4=uv4))
    for key in order:
        src = keys[key]
        if key in skip:
            continue
        if src is not None and src.kind in ("glyph2d", "glyph3d"):
            path = glyphs.font_for_char(font_paths(src.args["role"]), src.args["char"])
            if path is None:
                continue                                 # no font has it: the node stays empty
            letters[key] = _letter(path, src, mobile)
            v, f, solid = letters[key]
            add(key, meshbin.encode(v, f, flat=solid))
        elif src is not None and src.kind == "line":
            line = _line(src.args["parts"], letters)
            if line:
                add(key, meshbin.encode(line[0], line[1], flat=line[2], colors=line[3]))
        elif src is not None and src.kind == "user":
            data = gimmick_assets.arrays(src.args, mobile)
            if data:
                add(key, meshbin.encode(data[0], data[1], colors=data[2]))
        else:
            v, f = meshes.build(key)
            add(key, meshbin.encode(v, f, flat=key.startswith(("shape:", "gimmick:"))))
    return pack, tris


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
    mobile = bool((options or {}).get("mobile"))
    tmp_map, fonts = tmp_fonts(baked, font_paths) if (options or {}).get("tmp") else ({}, [])
    if fonts:
        os.makedirs(os.path.join(folder, "fonts"), exist_ok=True)
        for f in fonts:                                  # Unity deletes them once the static atlas exists
            shutil.copy2(f.pop("path"), os.path.join(folder, f["file"]))
    pack, _ = pack_meshes(baked, font_paths, mobile, skip=set(tmp_map))
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
    doc = manifest.build(baked, plan, sections, pack.entries, song, opts, dome_params(baked), fonts, tmp_map)
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    install_templates(project)
    with open(os.path.join(folder, MARKER), "w", encoding="utf-8") as f:
        f.write(name)                                    # written last: Unity builds when it sees this
    return folder, os.path.isdir(gen)
