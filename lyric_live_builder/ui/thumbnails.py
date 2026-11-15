"""Part thumbnails in the line details (spec §6.2, design §13): each layout / motion field is a thumbnail dropdown
(a grid of thumbnails with names), with a name filter. The images come from lyric_live_builder/thumbnails
(tools/make_part_thumbnails.py); the motions are animated by stepping through their frames while the details are open."""
import json
import os
import time

import bpy
import bpy.utils.previews
import numpy as np
from bpy.app.translations import pgettext_iface as iface_

from ..core import atlas, registry

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "thumbnails")
KINDS = ("layout", "enter", "hold", "exit")
STEP = 0.16                     # seconds per frame
SCALE = 5.0                     # thumbnail size in the field and in its grid (icon units)
REST = 5                        # extra steps on the settled frame: entrances end on it, exits start from it
ICON = 32                       # small icon size (from the tile)

_previews = None
_index = None
_frames = {}                    # kind -> RGBA bytes (part, frame, row going up, column, 4)
_shown = {}                     # kind -> the frame now in its previews


def index():
    global _index
    if _index is None:
        with open(os.path.join(DIR, "index.json"), encoding="utf-8") as f:
            _index = json.load(f)
    return _index


def _load(kind):
    """A preview per part of a kind (on the first use); _tick puts the frame of the moment in it, so the field and
    an open grid of thumbnails both move."""
    global _previews
    if kind in _frames:
        return
    if _previews is None:
        _previews = bpy.utils.previews.new()
    idx = index()
    t, n, rows = idx["tile"], idx["frames"][kind], idx["rows"][kind]
    with open(os.path.join(DIR, f"{kind}.png"), "rb") as f:
        px = atlas.png_decode(f.read())
    frames = np.ascontiguousarray(px.reshape(len(rows), t, n, t, 4).transpose(0, 2, 1, 3, 4)[:, :, ::-1])
    rest = n - 1 if kind == "enter" else 0                       # the small icon: the settled frame
    step = max(1, t // ICON)
    for row, key in enumerate(rows):
        pv = _previews.new(f"{kind}:{key}")
        pv.image_size = (t, t)
        small = np.ascontiguousarray(frames[row, rest, ::step, ::step])
        pv.icon_size = small.shape[1], small.shape[0]
        pv.icon_pixels.foreach_set(small.view(np.int32).ravel())
    _frames[kind] = frames
    _paint(kind, frame(kind, time.monotonic()))


def _paint(kind, k):
    """Put frame k of every part of a kind in its preview."""
    frames = _frames[kind]
    for row, key in enumerate(index()["rows"][kind]):
        _previews[f"{kind}:{key}"].image_pixels.foreach_set(frames[row, k].view(np.int32).ravel())
    _shown[kind] = k


def icon(kind, key):
    """icon_id of a part's thumbnail (0 when there is none)."""
    try:
        _load(kind)
    except (OSError, KeyError, ValueError) as e:
        print("[LLB] thumbnails:", e)
        return 0
    pv = _previews.get(f"{kind}:{key}")
    return pv.icon_id if pv else 0


def frame(kind, t):
    """Frame shown at time t: entrances rest on their last frame, exits on their first, holds just loop."""
    n = index()["frames"][kind]
    if n <= 1:
        return 0
    seq = list(range(n))
    if kind == "enter":
        seq += [n - 1] * REST
    elif kind == "exit":
        seq = [0] * REST + seq
    return seq[int(t / STEP) % len(seq)]


def parts(kind, group, text):
    """The parts a gallery shows: the picked group, and names / keys containing the filter text."""
    q = text.strip().casefold()
    return [p for p in registry.parts(kind) if (group == "all" or p.group == group)
            and (not q or q in iface_(p.name).casefold() or q in p.name.casefold() or q in p.key.casefold())]


_items = {}                     # kind -> the enum items last given
_strings = {}                   # every item string given: Blender keeps pointers to them while a grid is open


def _keep(text):
    return _strings.setdefault(text, text)


def chosen(kind, proj):
    """The part the planner picks now for the picked line's field, or None."""
    from .panels import _chosen
    return _chosen(proj)[0].get(proj.line_active, {}).get(kind)


def enum_items(kind, proj):
    """Items of proj.pick_<kind>: Planner's Choice, then the shown parts with their thumbnails (the line's current
    part always included). The number of an item is its place in the registry + 1."""
    keys = registry.keys(kind)
    ln = proj.lines[proj.line_active] if 0 <= proj.line_active < len(proj.lines) else None
    current = getattr(ln, kind) if ln else "AUTO"
    shown = parts(kind, proj.part_group, proj.gallery_filter)
    if current in keys and all(p.key != current for p in shown):
        shown.append(registry.get(kind, current))
    auto, picked = iface_("Planner's Choice"), chosen(kind, proj)          # shown with the planner's part
    if picked in keys:
        auto = iface_("{} ({})").format(auto, iface_(registry.get(kind, picked).name))
    items = [("AUTO", _keep(auto), _keep(iface_("Chosen by the planner")),
              icon(kind, picked) if picked in keys else "QUESTION", 0)]
    items += [(p.key, _keep(iface_(p.name)), _keep(iface_(p.name)), icon(kind, p.key),
               1 + keys.index(p.key)) for p in shown]
    _items[kind] = items
    return items


def enum_get(kind, proj):
    ln = proj.lines[proj.line_active] if 0 <= proj.line_active < len(proj.lines) else None
    key = getattr(ln, kind) if ln else "AUTO"
    keys = registry.keys(kind)
    return 1 + keys.index(key) if key in keys else 0


def enum_set(kind, proj, value):
    if 0 <= proj.line_active < len(proj.lines):
        keys = registry.keys(kind)
        setattr(proj.lines[proj.line_active], kind, keys[value - 1] if 0 < value <= len(keys) else "AUTO")


def draw(layout, proj, ln, kind):
    """One kind's field: its name and part, and the current part's thumbnail, which opens a grid of the shown
    parts' thumbnails with their names to pick from."""
    start()
    col = layout.column(align=True)
    prop = ln.bl_rna.properties[kind]
    from .panels import auto_text
    shown = auto_text(ln, kind, chosen(kind, proj)) or iface_(prop.enum_items[getattr(ln, kind)].name)
    col.label(text=f"{iface_(prop.name)}: {shown}", translate=False)
    if proj.gallery_filter.strip() and not parts(kind, proj.part_group, proj.gallery_filter):
        col.label(text="No Parts Found", icon="INFO")
    col.template_icon_view(proj, f"pick_{kind}", show_labels=True, scale=SCALE, scale_popup=SCALE)


def _tick():
    """Next frame of the motions while the details area is open (an open grid is redrawn with the window)."""
    from . import details
    win, area = details.area()
    if area is None:
        return None
    now = time.monotonic()
    for kind in list(_frames):
        k = frame(kind, now)
        if _shown.get(kind) != k:
            _paint(kind, k)
    area.tag_redraw()
    return STEP


def start():
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=STEP)


def unregister():
    global _previews, _index
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
    _previews, _index = None, None
    _frames.clear()
    _shown.clear()


CLASSES = ()
