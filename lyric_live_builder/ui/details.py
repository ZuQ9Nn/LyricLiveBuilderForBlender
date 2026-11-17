"""The line's view (spec §6.2, design §13): with "View the Line from the Audience" on, the main 3D view looks at the
picked line from the audience's eye; off, it goes back to the view it had. The line details themselves are drawn in
the Lyric Lines panel (ui/panels.py)."""
import math

import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Vector

from ..core import model, xform
from . import planning, project

LENS = 28.0                 # mm, as the trial views
DELAY = 0.15                # s after a pick before the view is aimed (a quick run of picks plans once)

_saved = {}                 # as_pointer() of the 3D view -> its view before it looked at the lines


def area():
    """(window, area) of the main 3D view: the biggest one of the first window that has one; or (None, None)."""
    for win in bpy.context.window_manager.windows:
        views = [a for a in win.screen.areas if a.type == "VIEW_3D"]
        if views:
            return win, max(views, key=lambda a: a.width * a.height)
    return None, None


def _view(space):
    r3d = space.region_3d
    return (r3d.view_location.copy(), r3d.view_rotation.copy(), r3d.view_distance, r3d.view_perspective, space.lens)


def toggle(proj):
    """Update of proj.line_view: on, remember the view and look at the line; off, put the view back."""
    win, a = area()
    if a is None:
        return
    space = a.spaces.active
    if proj.line_view:
        _saved.setdefault(a.as_pointer(), _view(space))
        picked(force=True)
        return
    saved = _saved.pop(a.as_pointer(), None)
    if saved:
        r3d = space.region_3d
        r3d.view_location, r3d.view_rotation, r3d.view_distance, r3d.view_perspective = saved[:4]
        space.lens = saved[4]
        a.tag_redraw()


def picked(force=False):
    """Update of the picked line: look at it a moment later, while the view follows the lines."""
    if (force or bpy.context.scene.llb.line_view) and not bpy.app.timers.is_registered(_aim_later):
        bpy.app.timers.register(_aim_later, first_interval=DELAY)


_tries = [0]


def _aim_later():
    try:
        if aim() is False and _tries[0] < 20:           # the area is not laid out yet: try again
            _tries[0] += 1
            return DELAY
    except Exception as e:                              # never break the UI
        print("[LLB] line view:", e)
    _tries[0] = 0
    return None


def target(proj, plan=None):
    """(direction from the eye, distance, time the line is fully shown) of the picked line, or None."""
    i = proj.line_active
    if not 0 <= i < len(proj.lines):
        return None
    plan = plan or planning.make_plan(proj)
    lp = next((x for x in plan.lines if x.index == i), None)
    if lp is None:
        return None
    d = Vector(xform.direction(*(lp.anchor if not lp.glide else (0.0, 0.0))))     # a gliding line comes in front
    return d.normalized(), float(model.DISTANCE[lp.distance]), lp.start + min(1.0, (lp.end - lp.start) / 2)


def aim():
    """Look at the picked line from the eye. False: the area has no size yet."""
    win, a = area()
    if a is None or not win.scene.llb.line_view:
        return None
    ui = next((r for r in a.regions if r.type == "UI"), None)
    if (a.width < 2 or next(r for r in a.regions if r.type == "WINDOW").width < 2
            or (a.spaces.active.show_region_ui and ui is not None and ui.width < 2)):
        return False
    scene = win.scene
    hit = target(scene.llb)
    if hit is None:
        return
    d, dist, t = hit
    space = a.spaces.active
    space.lens = LENS
    space.region_3d.view_perspective = "PERSP"
    _look(space.region_3d, _beside_sidebar(a, d), dist)
    if not win.screen.is_animation_playing:
        scene.frame_set(scene.frame_start + round(t * project.fps(scene)))
    a.tag_redraw()


def _eye():
    return Vector((0.0, 0.0, model.EYE_HEIGHT))


def _look(r3d, d, dist):
    r3d.view_rotation = d.to_track_quat("-Z", "Y")     # the view's up is its local Y
    r3d.view_distance = dist
    r3d.view_location = _eye() + d * dist              # orbit about the line, from the eye


def _beside_sidebar(a, d):
    """The sidebar lies over the right of the view (region overlap): the forward direction turned about the eye,
    sideways only, so the line (straight along d) sits in the middle of the part left uncovered.
    The viewport's lens covers 36 mm over the longer side of the region (Blender's sensor fit "auto")."""
    region = next(r for r in a.regions if r.type == "WINDOW")
    ui = next((r for r in a.regions if r.type == "UI"), None)
    w, h = max(region.width, 1), max(region.height, 1)
    covered = ui.width if ui and a.spaces.active.show_region_ui and region.width >= a.width - 2 else 0
    if not covered or covered >= w:
        return d
    ndc = (w - covered) / w - 1                         # the middle of the uncovered part, -1..1 across the region
    p00 = LENS / 36.0 * max(w, h) / w
    up = d.to_track_quat("-Z", "Y") @ Vector((0.0, 1.0, 0.0))
    return (Matrix.Rotation(math.atan(ndc / p00), 3, up) @ d).normalized()


@persistent
def _after_load(_file=None, _arg=None):
    """A reopened file has its own views: forget the remembered one."""
    _saved.clear()


def register():
    bpy.app.handlers.load_post.append(_after_load)


def unregister():
    if _after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_after_load)
    if bpy.app.timers.is_registered(_aim_later):
        bpy.app.timers.unregister(_aim_later)
    _saved.clear()


CLASSES = ()
