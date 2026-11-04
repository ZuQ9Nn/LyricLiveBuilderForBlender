"""Unity export (spec §9): write the song folder, then build it in Unity (batch mode when the project is
closed; the editor's auto build when it is open)."""
import os

import bpy
from bpy.app.translations import pgettext_iface as iface_

from .. import prefs
from ..core import bake
from ..export_unity import exporter, unity_locate, unity_run
from . import planning, project

_job = {}                        # the running batch build (one at a time)


def addon_version():
    import tomllib
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blender_manifest.toml")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f).get("version", "")
    except (OSError, ValueError):
        return ""


def unity_path(context):
    st = context.scene.llb.export
    p = prefs.get(context)
    explicit = bpy.path.abspath(st.unity_path) if st.unity_path else (p.unity_path if p and p.unity_path else "")
    return unity_locate.find_unity(explicit)


def song_name(proj):
    st = proj.export
    if st.folder_name:
        return exporter.safe_name(st.folder_name)
    if proj.audio_path:
        return exporter.safe_name(os.path.splitext(os.path.basename(bpy.path.abspath(proj.audio_path)))[0])
    return "Song"


def _error(context, title, lines):
    print("[LLB][ERROR]", title, *lines)
    if bpy.app.background:
        return
    def draw(self, _context):
        for ln in lines:
            self.layout.label(text=ln, translate=False)
    context.window_manager.popup_menu(draw, title=iface_(title), icon="ERROR")


def export_options(st):
    return {"materialMode": st.material_mode, "mobile": st.use_mobile, "particleRatio": st.particle_ratio,
            "tmp": st.use_tmp, "udonSync": st.use_udon_sync}


class LLB_OT_check_budget(bpy.types.Operator):
    bl_idname = "llb.check_budget"
    bl_label = "Check the Budget"
    bl_description = ("Count triangles on stage, particles alive and materials as the Unity export would make them "
                      "(with the Unity Export panel's options), against the mobile limits")

    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.lines) > 0

    def execute(self, context):
        import json
        from ..export_unity import budget, exporter as ex
        proj = context.scene.llb
        st = proj.export
        if not project.has_any_font(proj):
            self.report({"ERROR"}, iface_("Set at least the Body font"))
            return {"CANCELLED"}
        plan = planning.make_plan(proj)
        baked = bake.bake(plan, project.metrics(proj), mobile=st.use_mobile, tmp=st.use_tmp, udon=st.use_udon_sync)
        skip = set(ex.tmp_fonts(baked, lambda role: project.font_paths(proj, role))[0]) if st.use_tmp else set()
        _, tris = ex.pack_meshes(baked, lambda role: project.font_paths(proj, role), st.use_mobile, skip)
        res = budget.check(baked, tris, st.use_mobile, st.particle_ratio,
                           {"tris": st.limit_tris, "particles": st.limit_particles, "materials": st.limit_materials})
        st.budget = json.dumps(res)
        over = [k for k, (v, lim, _) in res.items() if v > lim]
        self.report({"WARNING" if over else "INFO"},
                    iface_("Over the limit: {}").format(", ".join(over)) if over else iface_("Within the limits"))
        return {"FINISHED"}


class LLB_OT_export_unity(bpy.types.Operator):
    bl_idname = "llb.export_unity"
    bl_label = "Export to Unity"
    bl_description = "Write the song into the Unity project and build its prefab and Timeline"

    _timer = None

    @classmethod
    def poll(cls, context):
        return len(context.scene.llb.lines) > 0 and not _job

    def check_inputs(self, context):
        proj = context.scene.llb
        project_dir = bpy.path.abspath(proj.export.project_path).rstrip("\\/")
        if not project_dir or not unity_locate.is_project(project_dir):
            _error(context, "Not a Unity project", [iface_("Choose the folder that holds Assets and ProjectSettings"),
                                                     project_dir])
            return None
        if not unity_locate.has_timeline(project_dir):
            _error(context, "The Timeline package is missing",
                   [iface_("Add Timeline in Unity: Window > Package Manager > Unity Registry > Timeline")])
            return None
        st = proj.export
        if st.use_tmp and not unity_locate.has_package(project_dir, "com.unity.textmeshpro"):
            _error(context, "The TextMesh Pro package is missing",
                   [iface_("Add TextMesh Pro in Unity, or turn TextMesh Pro off")])
            return None
        unity, others = unity_path(context)
        if unity is None:
            _error(context, "Unity was not found", [iface_("Install Unity 2022.3.22f1 with Unity Hub,"),
                                                    iface_("or set the Unity Editor path")] + others[:3])
            return None
        if not project.has_any_font(proj):
            _error(context, "Set at least the Body font", [])
            return None
        return project_dir, unity

    def invoke(self, context, event):
        found = self.check_inputs(context)
        if found is None:
            return {"CANCELLED"}
        proj = context.scene.llb
        gen = os.path.join(exporter.song_folder(found[0], song_name(proj)), "Generated")
        if os.path.isdir(gen):
            return context.window_manager.invoke_confirm(
                self, event, title=iface_("Overwrite the song in Unity?"),
                message=iface_("Generated files of this song are replaced (scene instances update)"), confirm_text=iface_("Write the Song"))
        return self.execute(context)

    def execute(self, context):
        found = self.check_inputs(context)
        if found is None:
            return {"CANCELLED"}
        project_dir, unity = found
        scene = context.scene
        proj = scene.llb
        st = proj.export
        try:
            plan = planning.make_plan(proj)
            baked = bake.bake(plan, project.metrics(proj), mobile=st.use_mobile, tmp=st.use_tmp, udon=st.use_udon_sync)
            sections = [{"index": i, "label": s.label or s.kind.capitalize(), "kind": s.kind,
                         "start": float(a), "end": float(b)} for i, (s, (a, b)) in enumerate(zip(proj.sections, plan.sections))]
            folder, existed = exporter.export(
                project_dir, song_name(proj), baked, plan, sections, lambda role: project.font_paths(proj, role),
                audio_path=bpy.path.abspath(proj.audio_path) if proj.audio_path else "",
                panorama_path=bpy.path.abspath(proj.panorama_path) if proj.panorama_path else "",
                title=song_name(proj), options=export_options(st), version=addon_version())
        except (OSError, ValueError) as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        rel = os.path.relpath(folder, project_dir).replace("\\", "/")
        if st.use_udon_sync and not unity_locate.has_package(project_dir, "com.vrchat.worlds"):
            self.report({"WARNING"}, iface_("No VRChat Worlds SDK (UdonSharp): the prefab plays without Udon sync"))
        if unity_locate.project_is_open(project_dir):
            st.status = iface_("Written. Switch to Unity: it builds there automatically")
            st.log_path = ""
            self.report({"INFO"}, st.status)
            return {"FINISHED"}
        _job["build"] = unity_run.BatchBuild(unity, project_dir, rel)
        _job["args"] = (unity, project_dir, rel)
        st.status = iface_("Unity is building (the first time takes a few minutes)…")
        st.log_path = _job["build"].log
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        st = context.scene.llb.export
        if event.type == "ESC":
            _job["build"].cancel()
            st.status = iface_("Export cancelled")
            return self._finish(context, {"CANCELLED"})
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        done, code, lines = _job["build"].poll()
        for ln in lines:
            st.status = ln[:120]
        for area in context.screen.areas if context.screen else ():
            if area.type == "VIEW_3D":
                area.tag_redraw()
        if not done:
            return {"PASS_THROUGH"}
        if code == 0 and _job["build"].udon_pending and not _job.get("again"):
            # LLBSync.cs was added: a second run compiles it and attaches it to the prefab
            _job["again"] = True
            _job["build"] = unity_run.BatchBuild(*_job["args"])
            st.status = iface_("Adding Udon sync (Unity runs once more)…")
            return {"PASS_THROUGH"}
        if code == 0:
            st.status = iface_("Done: the prefab is in Generated/")
            self.report({"INFO"}, st.status)
            return self._finish(context, {"FINISHED"})
        st.status = iface_("Unity failed (exit code {})").format(code)
        _error(context, "Unity build failed", [st.status, iface_("Log: {}").format(st.log_path)])
        return self._finish(context, {"CANCELLED"})

    def _finish(self, context, result):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        _job.clear()
        return result


CLASSES = (LLB_OT_check_budget, LLB_OT_export_unity)
