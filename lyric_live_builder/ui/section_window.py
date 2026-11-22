"""Section settings in a window of their own (spec §6.2, design §13): "Section Settings" opens a new Blender window
whose sidebar lists every section. The window's screen carries a mark (a custom property), so its panel shows there
and nowhere else, also after the file is opened again. The rest of the window is an empty 3D view."""
import bpy

MARK = "llb_sections"       # custom property on the window's screen


def is_section_screen(screen):
    return screen is not None and bool(screen.get(MARK))


def windows():
    return [w for w in bpy.context.window_manager.windows if is_section_screen(w.screen)]


def open_window(context):
    """Open the window (an open one is closed first, so the new one comes to the front)."""
    for win in windows():
        with context.temp_override(window=win):
            bpy.ops.wm.window_close()
    win = context.window
    src = context.area if context.area and context.area.type == "VIEW_3D" else \
        max((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    known = {w.as_pointer() for w in context.window_manager.windows}
    with context.temp_override(window=win, area=src):
        bpy.ops.wm.window_new()                          # a window with this 3D view alone (its sidebar width too)
    new = next(w for w in context.window_manager.windows if w.as_pointer() not in known)
    new.screen[MARK] = True
    for a in new.screen.areas:
        if a.type != "VIEW_3D":
            continue
        space = a.spaces.active
        space.show_region_ui = True
        space.show_region_toolbar = False
        space.show_region_header = False
        space.overlay.show_overlays = False
        space.show_gizmo = False
        for name in dir(space):                          # nothing in the view: the sidebar is what the window is for
            if name.startswith("show_object_viewport_"):
                setattr(space, name, False)
    return new


class LLB_OT_section_window(bpy.types.Operator):
    bl_idname = "llb.section_window"
    bl_label = "Section Settings"
    bl_description = "Open a window that lists every section with its particles, background and transition"

    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.sections) > 0

    def execute(self, context):
        open_window(context)
        return {"FINISHED"}


class LLB_PT_section_window(bpy.types.Panel):
    """Only in the section window. No header: header-less panels come first, so its sidebar opens on this tab."""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LyricLive"
    bl_label = "Section Settings"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return is_section_screen(getattr(context, "screen", None))

    def draw(self, context):
        from .panels import draw_section_window
        draw_section_window(self.layout.column(), context.scene.llb)


CLASSES = (LLB_OT_section_window, LLB_PT_section_window)
