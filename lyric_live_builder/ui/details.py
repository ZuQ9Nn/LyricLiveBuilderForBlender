"""Line details beside the 3D view (spec §6.2, design §13): "Details" in the line list splits the 3D view and
makes the narrow left part the details area. Its sidebar shows the picked line's layout and below; its view looks
at that line from the audience's eye. The area is remembered by as_pointer(), like the trial views."""
import math

import bpy
from bpy.app.handlers import persistent
from bpy.app.translations import pgettext_iface as iface_
from mathutils import Matrix, Vector

from ..core import model, xform
from . import planning, project

LENS = 28.0                 # mm, as the trial views
DELAY = 0.15                # s after a pick before the view is aimed (a quick run of picks plans once)
EXTRA = 360                 # px of 3D view beside the sidebar (times the UI scale)
MAX_SHARE = 0.45            # of the 3D view that was split

_area = []                  # as_pointer() of the details area


def area():
    """(window, area) of the details area, or (None, None)."""
    if _area:
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                if a.as_pointer() == _area[0] and a.type == "VIEW_3D":
                    return win, a
    return None, None


def is_open():
    return area()[1] is not None


def is_details_area(a):
    return a is not None and bool(_area) and a.as_pointer() == _area[0]


def open_area(context, index):
    proj = context.scene.llb
    if 0 <= index < len(proj.lines):
        proj.line_active = index                        # also re-aims an open area (picked)
    if is_open():
        return
    win = context.window
    src = context.area if context.area and context.area.type == "VIEW_3D" else \
        max((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    ui = next((r for r in src.regions if r.type == "UI"), None)
    want = (ui.width if ui else 300) + EXTRA * context.preferences.system.ui_scale
    factor = max(0.15, min(MAX_SHARE, want / max(src.width, 1)))
    region = next(r for r in src.regions if r.type == "WINDOW")
    known = {a.as_pointer() for a in win.screen.areas}
    with context.temp_override(window=win, area=src, region=region):
        bpy.ops.screen.area_split(direction="VERTICAL", factor=factor)
    new = next(a for a in win.screen.areas if a.as_pointer() not in known)
    left = min((src, new), key=lambda a: a.x)           # the narrow part on the left
    _area[:] = [left.as_pointer()]
    space = left.spaces.active
    space.shading.type = "MATERIAL"
    space.show_region_toolbar = False
    space.show_region_ui = True
    space.overlay.show_floor = space.overlay.show_axis_x = space.overlay.show_axis_y = False
    if not bpy.app.timers.is_registered(_aim_later):
        bpy.app.timers.register(_aim_later, first_interval=DELAY)     # once the new area has its size


def close_area(context=None):
    win, a = area()
    if a is not None:
        with bpy.context.temp_override(window=win, area=a):
            bpy.ops.screen.area_close()
    _area.clear()


def picked():
    """Update of the picked line: aim the open area at it a moment later."""
    if is_open() and not bpy.app.timers.is_registered(_aim_later):
        bpy.app.timers.register(_aim_later, first_interval=DELAY)


_tries = [0]


def _aim_later():
    try:
        if aim() is False and _tries[0] < 20:           # the new area is not laid out yet: try again
            _tries[0] += 1
            return DELAY
    except Exception as e:                              # never break the UI
        print("[LLB] line details:", e)
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
    """Look at the picked line from the eye. False: the area has no size yet (just split)."""
    win, a = area()
    if a is None:
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
    """The area stays as a plain 3D view in a reopened file: forget it."""
    _area.clear()


def register():
    bpy.app.handlers.load_post.append(_after_load)


def unregister():
    close_area()
    if _after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_after_load)
    for fn in (_aim_later,):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)


class LLB_OT_line_details(bpy.types.Operator):
    bl_idname = "llb.line_details"
    bl_label = "Line Details"
    bl_description = "Set this line's layout and motions beside the 3D view, seen from the audience"

    index: bpy.props.IntProperty(default=-1, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.lines) > 0

    def execute(self, context):
        open_area(context, self.index if self.index >= 0 else context.scene.llb.line_active)
        return {"FINISHED"}


class LLB_OT_line_details_close(bpy.types.Operator):
    bl_idname = "llb.line_details_close"
    bl_label = "Close Line Details"
    bl_description = "Remove the line details area beside the 3D view"

    def execute(self, context):
        close_area(context)
        return {"FINISHED"}


class LLB_PT_line_details(bpy.types.Panel):
    """Only in the details area (the other LyricLive panels stay out of it). No header: Blender puts header-less
    panels first, so the fresh sidebar of the new area opens on the LyricLive tab (it cannot be set from Python)."""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LyricLive"
    bl_label = "Line Details"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return is_details_area(getattr(context, "area", None))

    def draw(self, context):
        from .panels import draw_line_details, draw_line_timing
        proj = context.scene.llb
        col = self.layout.column()
        col.label(text="Line Details", icon="PREFERENCES")
        col.operator("llb.line_details_close", icon="X")
        if not 0 <= proj.line_active < len(proj.lines):
            return
        ln = proj.lines[proj.line_active]
        box = col.box()
        box.label(text=iface_("Line {}").format(proj.line_active + 1), translate=False)
        box.label(text=ln.text, translate=False)
        draw_line_timing(box, proj, ln)                   # which section the line is in (spec §6.2)
        draw_line_details(col, proj, ln)


CLASSES = (LLB_OT_line_details, LLB_OT_line_details_close, LLB_PT_line_details)
