"""Large instructions at the top of every 3D Viewport while a modal tool runs
(the status bar text is small and easy to miss)."""
import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader


class Overlay:
    def __init__(self, lines_fn):
        """lines_fn() -> [(text, size in points)], called on every redraw."""
        self.lines_fn = lines_fn
        self.handle = None

    def start(self):
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), "WINDOW", "POST_PIXEL")
        _redraw()

    def stop(self):
        if self.handle:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, "WINDOW")
            self.handle = None
            _redraw()

    def _draw(self):
        try:
            lines = self.lines_fn()
        except Exception:
            return
        scale = bpy.context.preferences.system.ui_scale
        font = 0
        pad = 12 * scale
        rows = []
        for text, size in lines:
            blf.size(font, size * scale)
            w, _ = blf.dimensions(font, text)
            rows.append((text, size * scale, w))
        width = max(w for _, _, w in rows) + pad * 2
        height = sum(s * 1.6 for _, s, _ in rows) + pad
        region = bpy.context.region
        # top centre: clear of the toolbar (left) and the navigation gizmo (right)
        x0, top = (region.width - width) / 2, region.height - 70 * scale
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        quad = ((x0, top - height), (x0 + width, top - height), (x0 + width, top), (x0, top))
        batch = batch_for_shader(shader, "TRI_FAN", {"pos": quad})
        gpu.state.blend_set("ALPHA")
        shader.uniform_float("color", (0.0, 0.0, 0.0, 0.75))
        batch.draw(shader)
        gpu.state.blend_set("NONE")
        y = top - pad
        for text, size, _ in rows:
            y -= size * 1.3
            blf.size(font, size)
            blf.position(font, x0 + pad, y, 0)
            blf.color(font, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font, text)
            y -= size * 0.3


def _redraw():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
