"""Thumbnails (spec §6.2, design §13): the line's layout, motions, particles and background, and the style, are
thumbnail dropdowns (a grid of thumbnails with names); the parts have a name filter. The images come from
lyric_live_builder/thumbnails (tools/make_part_thumbnails.py); motions and particles are animated by stepping through
their frames while they are drawn."""
import json
import os
import time

import bpy
import bpy.utils.previews
import numpy as np
from bpy.app.translations import pgettext_iface as iface_

from .. import props
from ..core import atlas, registry

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "thumbnails")
PARTS = ("layout", "enter", "hold", "exit")        # with the planner's choice and the filter
KINDS = PARTS + ("particle", "background", "style")
ANIMATED = ("enter", "hold", "exit", "particle")
# no thumbnail, or one that cannot show it ("Style Color" is in the colours of the style picked now)
STILL_ICONS = {"particle": {"AUTO": "X", "lyrics": "SYNTAX_OFF"},
               "background": {"AUTO": "X", "panorama": "IMAGE_DATA", "style_color": "COLOR"}}
LINGER = 1.0                    # s the frames go on after an animated thumbnail was last drawn
STEP = 0.16                     # seconds per frame
SCALE = 5.0                     # thumbnail size in the field and in its grid (icon units)
REST = 5                        # extra steps on the settled frame: entrances end on it, exits start from it
ICON = 32                       # small icon size (from the tile)

_previews = None
_index = None
_frames = {}                    # kind -> RGBA bytes (part, frame, row going up, column, 4)
_shown = {}                     # kind -> the frame now in its previews
_drawn = [0.0]                  # when an animated thumbnail was last drawn


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


def _target(kind, proj):
    """The data a kind's field sets: the project (style) or the picked line (None without one)."""
    if kind == "style":
        return proj
    return proj.lines[proj.line_active] if 0 <= proj.line_active < len(proj.lines) else None


def _rna_items(kind):
    return (props.LLBProject if kind == "style" else props.LLBLine).bl_rna.properties[kind].enum_items


def enum_items(kind, proj):
    """Items of proj.pick_<kind>. Parts: Planner's Choice, then the shown parts (the line's current part always
    included), numbered by their place in the registry + 1. The others: the items of the field itself in its order,
    with thumbnails as icons."""
    if kind not in PARTS:
        return _other_items(kind, proj)
    keys = registry.keys(kind)
    ln = _target(kind, proj)
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


def _now_shown(kind, proj, data):
    """(name, thumbnail key) of the field's value as it works out now: "From the Lyrics (Petals)", or the
    section's background behind "No Change"."""
    value = getattr(data, kind) if data is not None else "AUTO"
    name = iface_(_rna_items(kind)[value].name)
    if kind == "particle" and value == "lyrics":
        got = chosen(kind, proj)
        if got in index()["rows"]["particle"]:
            return iface_("{} ({})").format(name, iface_(_rna_items(kind)[got].name)), got
    if kind == "background" and value == "AUTO":
        from .panels import _line_summary
        lines = _line_summary(proj)
        if 0 <= proj.line_active < len(lines):
            return name, lines[proj.line_active]["background"]
    return name, value


def _other_items(kind, proj):
    data = _target(kind, proj)
    rows = index()["rows"][kind]
    value = getattr(data, kind) if data is not None else None
    items = []
    for i, it in enumerate(_rna_items(kind)):
        name, key = _now_shown(kind, proj, data) if it.identifier == value else (iface_(it.name), it.identifier)
        still = STILL_ICONS.get(kind, {})
        ic = still[key] if key in still and key != "AUTO" else icon(kind, key) if key in rows else \
            still.get(it.identifier, "QUESTION")
        items.append((it.identifier, _keep(name), _keep(iface_(it.description) if it.description else name), ic, i))
    _items[kind] = items
    return items


def enum_get(kind, proj):
    data = _target(kind, proj)
    if kind not in PARTS:
        return max(0, _rna_items(kind).find(getattr(data, kind))) if data is not None else 0
    key = getattr(data, kind) if data else "AUTO"
    keys = registry.keys(kind)
    return 1 + keys.index(key) if key in keys else 0


def enum_set(kind, proj, value):
    data = _target(kind, proj)
    if data is None:
        return
    if kind not in PARTS:
        setattr(data, kind, _rna_items(kind)[value].identifier)
        return
    keys = registry.keys(kind)
    setattr(data, kind, keys[value - 1] if 0 < value <= len(keys) else "AUTO")


def draw(layout, proj, data, kind):
    """One kind's field: its name and value, and the current thumbnail, which opens a grid of thumbnails with their
    names to pick from."""
    if kind in ANIMATED:
        start()
    col = layout.column(align=True)
    prop = data.bl_rna.properties[kind]
    if kind in PARTS:
        from .panels import auto_text
        shown = auto_text(data, kind, chosen(kind, proj)) or iface_(prop.enum_items[getattr(data, kind)].name)
        col.label(text=f"{iface_(prop.name)}: {shown}", translate=False)
        if proj.gallery_filter.strip() and not parts(kind, proj.part_group, proj.gallery_filter):
            col.label(text="No Parts Found", icon="INFO")
    elif kind == "style":
        col.label(text=f"{iface_(prop.name)}: {_now_shown(kind, proj, data)[0]}", translate=False)
    else:                                                # long names: the value on its own row
        col.label(text=prop.name)
        col.label(text=_now_shown(kind, proj, data)[0], translate=False)
    col.template_icon_view(proj, f"pick_{kind}", show_labels=True, scale=SCALE, scale_popup=SCALE)


def thumb(layout, kind, key, name, scale=2.5):
    """A thumbnail beside its name (the section's In Use); without one, the name alone."""
    ic = icon(kind, key) if key in index()["rows"].get(kind, ()) and key not in STILL_ICONS.get(kind, {}) else 0
    if not ic:
        layout.label(text=name, icon=STILL_ICONS.get(kind, {}).get(key, "BLANK1"), translate=False)
        return
    if kind in ANIMATED:
        start()
    split = layout.split(factor=0.34)
    split.template_icon(icon_value=ic, scale=scale)
    split.label(text=name, translate=False)


def _tick():
    """Next frame of the animated thumbnails while they are being drawn: the 3D views' sidebars are redrawn (an open
    grid of thumbnails is redrawn with its window)."""
    now = time.monotonic()
    if now - _drawn[0] > LINGER:
        return None
    for kind in list(_frames):
        if kind in ANIMATED:
            k = frame(kind, now)
            if _shown.get(kind) != k:
                _paint(kind, k)
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "UI":
                        region.tag_redraw()
    return STEP


def start():
    """An animated thumbnail is being drawn: keep the frames going."""
    _drawn[0] = time.monotonic()
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
