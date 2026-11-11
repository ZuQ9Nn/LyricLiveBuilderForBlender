"""Before / After trial views beside the LyricLive sidebar (spec §6.3, design §12).

The 3D view the button was pressed in is split: two views on the left show the picked line (or section start)
as last generated (Before) and as set now (After); the right part stays the user's 3D view with the sidebar.
A window shows one scene, so the trial objects live in the main scene, hidden from every other view and from
renders. Only Confirm / Generate change the main preview."""
import json

import bpy
import numpy as np
from bpy.app.handlers import persistent
from bpy.app.translations import pgettext_iface as iface_
from mathutils import Vector

from ..core import bake, model, planner
from ..preview import scene as preview_scene
from . import planning, project
from .overlay import Overlay

BEFORE, AFTER = preview_scene.ROOT + "_Before", preview_scene.ROOT + "_After"
RESTORE = "llb_trial_restore"          # scene custom property: range and sound to put back on close
# what Before keeps; the same fields' update rebuilds After
LINE_FIELDS = ("is_3d", "depth", "bevel", "layout", "enter", "hold", "exit", "distance_layer", "cuts", "persist",
               "guide", "gimmick", "gimmick_show", "gimmick_word", "particle", "background", "transition",
               "seed_offset", "lock_cuts")
SECTION_FIELDS = ("kind", "theme", "background", "transition")
LEAD, TAIL = 1.4, 0.4                  # seconds shown before a line (its gaze guide) and after it has left
SECTION_SPAN = (-1.5, 6.0)             # around a section start: the transition and the new background
SPLIT = 0.6                            # share of the 3D view the two trial views take (on the left)
DEBOUNCE = 0.15
TICK = 0.1
LENS = 28.0                            # mm: wide, yet the letters stay readable in a narrow view

_areas = []                            # as_pointer() of the Before and After views
_scene = ""                            # name of the scene they show
_overlay = None
_views = {}                            # last view per side, to see which one the user moved
_both = False
error = ""


# ---------- the saved state (Before) ----------

def snapshot(proj):
    return {"state": planning.state(proj),
            "lines": [dict({f: getattr(ln, f) for f in LINE_FIELDS}, text=ln.text) for ln in proj.lines],
            "sections": [{f: getattr(s, f) for f in SECTION_FIELDS} for s in proj.sections]}


def saved(proj):
    return json.loads(proj.trial_snapshot) if proj.trial_snapshot else None


def built(scene):
    """The main preview was (re)built: it becomes Before."""
    scene.llb.trial_snapshot = json.dumps(snapshot(scene.llb))
    if is_open():
        schedule(both=True)


# ---------- where things are ----------

def views():
    """(window, [Before, After]) while the trial is open, else (None, [])."""
    for win in bpy.context.window_manager.windows:
        found = {a.as_pointer(): a for a in win.screen.areas if a.type == "VIEW_3D"}
        if _areas and all(p in found for p in _areas):
            return win, [found[p] for p in _areas]
    return None, []


def is_open():
    return bool(views()[1])


def target(proj):
    """("line" | "section", index) the trial shows: what was picked last."""
    if proj.trial_focus == "section" and 0 <= proj.section_active < len(proj.sections):
        return "section", proj.section_active
    if 0 <= proj.line_active < len(proj.lines):
        return "line", proj.line_active
    return "section", max(0, proj.section_active)


# ---------- building ----------

def _span(plan, proj, kind, index):
    if kind == "line":
        lp = next((x for x in plan.lines if x.index == index), None)
        if lp is not None:
            return lp.start - LEAD, lp.end + TAIL
    sec = proj.sections[index] if 0 <= index < len(proj.sections) else None
    s = sec.start if sec else 0.0
    return s + SECTION_SPAN[0], min(s + SECTION_SPAN[1], sec.end if sec else s + SECTION_SPAN[1])


def _aim(baked, t0, t1):
    """Direction from the eye to the line's letters (the front when there are none)."""
    eye = np.array([0.0, 0.0, model.EYE_HEIGHT])
    for t in np.linspace(t0 + LEAD, t1, 8):
        pts = list(bake.world_positions(baked, float(t)).values())
        if pts:
            d = np.mean(pts, axis=0) - eye
            return Vector(d / max(np.linalg.norm(d), 1e-6)), float(np.linalg.norm(d))
    return Vector((0.0, 1.0, 0.0)), 3.5


def refresh(both=False):
    """Rebuild After (and Before). both: the target changed, so the playback range and the view are set again."""
    global error
    win, sides = views()
    scene = bpy.data.scenes.get(_scene)
    if not sides or scene is None:
        return
    proj = scene.llb
    if not project.has_any_font(proj):
        error = "Set at least the Body font"
        return
    error = ""
    kind, index = target(proj)
    plans = {AFTER: planning.make_plan(proj)}
    if both:
        plans[BEFORE] = planning.make_plan(proj, saved(proj))
    t0, t1 = _span(plans[AFTER], proj, kind, index)
    t0 = max(0.0, t0)
    fonts = lambda role: project.font_paths(proj, role)
    line = index if kind == "line" else None
    aim = (Vector((0.0, 1.0, 0.0)), 3.5)
    for root, plan in plans.items():
        baked = bake.bake(planner.subset(plan, t0, t1, line), project.metrics(proj))
        preview_scene.build(scene, baked, fonts, panorama=proj.panorama_path, root=root)
        if root == AFTER and line is not None:
            aim = _aim(baked, t0, t1)
    _isolate(scene, win, sides)
    if both:
        fps = project.fps(scene)
        scene.use_preview_range = True
        scene.frame_preview_start = scene.frame_start + round(t0 * fps)
        scene.frame_preview_end = max(scene.frame_preview_start + 1, scene.frame_start + round(t1 * fps))
        scene.frame_set(scene.frame_preview_start)
        _look(sides, *aim)
        _play(win, sides)


def _isolate(scene, win, sides):
    """The trial objects: hidden from other views and renders; each trial view shows its own root."""
    layer = win.view_layer
    names = [c.name for c in layer.layer_collection.children]
    for root in (BEFORE, AFTER):
        if root in names:
            layer.layer_collection.children[root].hide_viewport = True
            bpy.data.collections[root].hide_render = True
    for area, keep in zip(sides, (BEFORE, AFTER)):
        if keep not in names:
            continue
        area.spaces.active.use_local_collections = True
        region = next(r for r in area.regions if r.type == "WINDOW")
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.object.hide_collection(collection_index=names.index(keep) + 1, toggle=False)


def _look(sides, direction, dist):
    eye = Vector((0.0, 0.0, model.EYE_HEIGHT))
    for area in sides:
        space = area.spaces.active
        r3d = space.region_3d
        space.lens = LENS
        r3d.view_perspective = "PERSP"
        r3d.view_rotation = direction.to_track_quat("-Z", "Y")     # the view's up is its local Y
        r3d.view_distance = dist
        r3d.view_location = eye + direction * dist      # orbit around the line, seen from the eye
    _views.clear()


def _play(win, sides):
    if not win.screen.is_animation_playing:
        with bpy.context.temp_override(window=win, area=sides[1]):
            bpy.ops.screen.animation_play()


def schedule(both=False):
    global _both
    _both = _both or both
    if not bpy.app.timers.is_registered(_rebuild):
        bpy.app.timers.register(_rebuild, first_interval=DEBOUNCE)


def _rebuild():
    global _both, error
    both, _both = _both, False
    try:
        refresh(both)
    except Exception as e:                    # a timer must not raise; show it in the panel
        error = str(e)
        print("[LLB] trial:", e)
    return None


def changed(context=None, both=False):
    """Update callback of the line / section fields."""
    if is_open():
        schedule(both)


def set_mute(scene):
    """Mute while the box is ticked; the sound setting from before the trial otherwise."""
    keep = json.loads(scene.get(RESTORE, "{}"))
    if keep:
        scene.use_audio = keep["use_audio"] and not scene.llb.trial_mute        # use_audio: True = plays


# ---------- open / close ----------

def open_views(context):
    global _scene
    scene = context.scene
    proj = scene.llb
    if not proj.trial_snapshot:
        proj.trial_snapshot = json.dumps(snapshot(proj))
    if is_open():
        schedule(both=True)
        return
    win = context.window
    area = context.area if context.area and context.area.type == "VIEW_3D" else \
        max((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    if RESTORE not in scene:
        scene[RESTORE] = json.dumps({"use_preview_range": scene.use_preview_range, "start": scene.frame_preview_start,
                                     "end": scene.frame_preview_end, "use_audio": scene.use_audio})
    proj.trial_mute = False
    _scene = scene.name
    # split: the left part (this area) becomes the trial, the right part (a copy) stays the user's view
    region = next(r for r in area.regions if r.type == "WINDOW")
    with context.temp_override(window=win, area=area, region=region):
        bpy.ops.screen.area_split(direction="VERTICAL", factor=SPLIT)
    known = {a.as_pointer() for a in win.screen.areas}
    with context.temp_override(window=win, area=area, region=region):
        bpy.ops.screen.area_split(direction="VERTICAL", factor=0.5)
    pair = sorted([area, next(a for a in win.screen.areas if a.as_pointer() not in known)], key=lambda a: a.x)
    _areas[:] = [a.as_pointer() for a in pair]                  # left to right: Before, After
    for a in pair:
        space = a.spaces.active
        with context.temp_override(window=win, area=a):
            space.shading.type = "MATERIAL"
            space.show_region_ui = space.show_region_toolbar = False
            space.overlay.show_floor = space.overlay.show_axis_x = space.overlay.show_axis_y = False
    start()
    schedule(both=True)


def close_views(context=None):
    """Remove the two views and the trial objects; put the range and the sound back."""
    win, sides = views()
    if win is not None:
        if win.screen.is_animation_playing:
            with bpy.context.temp_override(window=win):
                bpy.ops.screen.animation_cancel(restore_frame=False)
        for area in sides:
            with bpy.context.temp_override(window=win, area=area):
                bpy.ops.screen.area_close()
    _areas.clear()
    stop()
    scene = bpy.data.scenes.get(_scene)
    if scene is not None:
        cleanup(scene)


def cleanup(scene):
    for root in (BEFORE, AFTER):
        preview_scene.clear(scene, root)
        coll = bpy.data.collections.get(root)
        if coll is not None:
            for child in list(coll.children_recursive):
                bpy.data.collections.remove(child)
            bpy.data.collections.remove(coll)
    keep = json.loads(scene.get(RESTORE, "{}"))
    if keep:
        scene.use_preview_range = keep["use_preview_range"]
        scene.frame_preview_start, scene.frame_preview_end = keep["start"], keep["end"]
        scene.use_audio = keep["use_audio"]
        del scene[RESTORE]


@persistent
def _after_load(_file=None, _arg=None):
    """A file saved with the trial open: its views are gone, so put things back."""
    _areas.clear()
    stop()
    for scene in bpy.data.scenes:
        if RESTORE in scene or bpy.data.collections.get(AFTER):
            cleanup(scene)


@persistent
def _after_undo(_scene_arg=None, _arg=None):
    if is_open():
        schedule(both=True)


# ---------- labels, views kept together ----------

def _labels():
    win, sides = views()
    area = bpy.context.area
    if not sides or area not in sides:
        return []
    if area == sides[0]:
        return [(iface_("Before (as generated)"), 16)]
    return [(iface_("After (settings now)"), 16),
            (iface_("The main preview changes only with Confirm or Generate"), 11)]


def start():
    global _overlay
    if _overlay is None:
        _overlay = Overlay(_labels)
        _overlay.start()
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=TICK)


def stop():
    global _overlay
    if _overlay is not None:
        _overlay.stop()
        _overlay = None
    for fn in (_tick, _rebuild):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)


def _tick():
    """Keep the two views together; clean up once the user closed one of them."""
    win, sides = views()
    if not sides:
        if _areas:
            close_views()
        return None
    now = [_view_of(a) for a in sides]
    moved = next((k for k in (0, 1) if _views.get(k) is not None and now[k] != _views[k]), None)
    if moved is not None:
        _set_view(sides[1 - moved], sides[moved])
        now[1 - moved] = _view_of(sides[1 - moved])
    _views.update(enumerate(now))
    return TICK


def _view_of(area):
    r = area.spaces.active.region_3d
    return (tuple(round(x, 5) for x in r.view_location), tuple(round(x, 5) for x in r.view_rotation),
            round(r.view_distance, 5), r.view_perspective, round(area.spaces.active.lens, 3))


def _set_view(dst, src):
    a, b = dst.spaces.active, src.spaces.active
    a.region_3d.view_location = b.region_3d.view_location
    a.region_3d.view_rotation = b.region_3d.view_rotation
    a.region_3d.view_distance = b.region_3d.view_distance
    a.region_3d.view_perspective = b.region_3d.view_perspective
    a.lens = b.lens
    dst.tag_redraw()


def draw_buttons(layout, proj):
    """Confirm, Back to Before, Mute and Close (the After header and the Try Out panel)."""
    row = layout.row(align=True)
    row.operator("llb.trial_commit", icon="CHECKMARK")
    row.operator("llb.trial_revert", icon="LOOP_BACK")
    row.prop(proj, "trial_mute", icon="MUTE_IPO_ON" if proj.trial_mute else "MUTE_IPO_OFF", toggle=True)
    row.operator("llb.trial_close", text="", icon="X")


def _header(self, context):
    win, sides = views()
    if sides and context.area == sides[1]:
        draw_buttons(self.layout, context.scene.llb)


def register():
    bpy.types.VIEW3D_HT_header.prepend(_header)
    bpy.app.handlers.load_post.append(_after_load)
    bpy.app.handlers.undo_post.append(_after_undo)
    bpy.app.handlers.redo_post.append(_after_undo)


def unregister():
    if is_open():
        close_views()
    stop()
    bpy.types.VIEW3D_HT_header.remove(_header)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        for fn in [f for f in handlers if getattr(f, "__module__", "") == __name__]:
            handlers.remove(fn)


# ---------- operators ----------

class LLB_OT_trial_open(bpy.types.Operator):
    bl_idname = "llb.trial_open"
    bl_label = "Try Out (Before / After)"
    bl_description = ("Show the picked line or section as last generated and as set now, side by side "
                      "beside the sidebar, playing in a loop")

    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.lines) > 0

    def execute(self, context):
        open_views(context)
        return {"FINISHED"}


class LLB_OT_trial_close(bpy.types.Operator):
    bl_idname = "llb.trial_close"
    bl_label = "Close the Trial"
    bl_description = "Remove the Before / After views and put the timeline range and the sound back"

    def execute(self, context):
        close_views(context)
        return {"FINISHED"}


class LLB_OT_trial_commit(bpy.types.Operator):
    bl_idname = "llb.trial_commit"
    bl_label = "Confirm Changes"
    bl_description = "Rebuild the main preview with the settings now (same as Generate); Before becomes the same"

    def execute(self, context):
        try:
            n, dt = planning.build_preview(context)
        except ValueError as e:
            self.report({"ERROR"}, iface_(str(e)))
            return {"CANCELLED"}
        self.report({"INFO"}, iface_("{} characters in {:.1f} s").format(n, dt))
        return {"FINISHED"}


class LLB_OT_trial_revert(bpy.types.Operator):
    bl_idname = "llb.trial_revert"
    bl_label = "Back to Before"
    bl_description = "Set the picked line or section back to Before (as last generated)"
    bl_options = {"UNDO"}

    def execute(self, context):
        proj = context.scene.llb
        snap = saved(proj)
        kind, index = target(proj)
        if snap is None:
            return {"CANCELLED"}
        if kind == "line":
            item, values = proj.lines[index], snap["lines"][index] if index < len(snap["lines"]) else None
            if values is None or values["text"] != item.text:
                self.report({"WARNING"}, iface_("This line was not there when the preview was generated"))
                return {"CANCELLED"}
        else:
            item = proj.sections[index]
            values = snap["sections"][index] if len(snap["sections"]) == len(proj.sections) else None
            if values is None:
                self.report({"WARNING"}, iface_("The sections changed since the preview was generated"))
                return {"CANCELLED"}
        for f in (LINE_FIELDS if kind == "line" else SECTION_FIELDS):
            if getattr(item, f) != values[f]:
                setattr(item, f, values[f])
        schedule()
        return {"FINISHED"}


class LLB_OT_trial_refresh(bpy.types.Operator):
    bl_idname = "llb.trial_refresh"
    bl_label = "Update the Trial"
    bl_description = "Build After again (after Make It for Me or a change in the Stage Effects)"

    def execute(self, context):
        schedule(both=True)
        return {"FINISHED"}


CLASSES = (LLB_OT_trial_open, LLB_OT_trial_close, LLB_OT_trial_commit, LLB_OT_trial_revert, LLB_OT_trial_refresh)
