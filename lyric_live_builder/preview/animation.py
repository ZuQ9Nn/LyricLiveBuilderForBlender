"""Tracks -> keyframes in one layered action per object (prototype S0-02).

"dome:<param>" tracks animate the dome material's node llb_<param> (an action on its node tree)."""
import bpy
import numpy as np

PATHS = {"location": "location", "rotation": "rotation_quaternion", "scale": "scale", "color": "color"}
EXPORT_ONLY = ("emit_rate",)                # the particle preview evaluates the emitter spec itself
LINEAR, CONSTANT = 1, 0                     # keyframe interpolation enum values


def _fcurve(cb, path, index, frames, values, interp):
    fc = cb.fcurves.new(path, index=index)
    kp = fc.keyframe_points
    kp.add(len(frames))
    co = np.empty(len(frames) * 2, dtype=np.float32)
    co[0::2] = frames
    co[1::2] = values
    kp.foreach_set("co", co)
    kp.foreach_set("interpolation", np.full(len(frames), interp, dtype=np.int32))
    fc.update()


def _action(owner, id_type, name):
    act = bpy.data.actions.new(f"LLB_{name}")
    slot = act.slots.new(id_type=id_type, name=name)
    cb = act.layers.new("LLB").strips.new(type="KEYFRAME").channelbag(slot, ensure=True)
    owner.animation_data_create()
    owner.animation_data.action = act
    owner.animation_data.action_slot = slot
    return cb


def apply(ob, tracks, fps, frame_start):
    """Write the tracks of one node onto its object (and the dome's onto its material)."""
    own = [tr for tr in tracks if not tr.prop.startswith("dome:") and tr.prop not in EXPORT_ONLY]
    dome = [tr for tr in tracks if tr.prop.startswith("dome:")]
    if own:
        cb = _action(ob, "OBJECT", ob.name)
        for tr in own:
            frames = frame_start + tr.times.astype(np.float64) * fps
            if tr.prop == "active":
                hidden = 1.0 - tr.values[:, 0]
                for path in ("hide_viewport", "hide_render"):
                    _fcurve(cb, path, 0, frames, hidden, CONSTANT)
                continue
            interp = CONSTANT if tr.interp == "constant" else LINEAR
            for c in range(tr.values.shape[1]):
                _fcurve(cb, PATHS[tr.prop], c, frames, tr.values[:, c], interp)
    if dome:
        tree = ob.data.materials[0].node_tree
        cb = _action(tree, "NODETREE", tree.name if tree.name else "Dome")
        for tr in dome:
            node = tree.nodes.get(f"llb_{tr.prop[5:]}")
            if node is None:
                continue                         # e.g. the image index: the preview has one panorama
            path = f'nodes["{node.name}"].outputs[0].default_value'
            interp = CONSTANT if tr.interp == "constant" else LINEAR
            frames = frame_start + tr.times.astype(np.float64) * fps
            for c in range(tr.values.shape[1]):
                _fcurve(cb, path, c, frames, tr.values[:, c], interp)


def clear_dome(material):
    """Drop the dome material's animation (the preview is being rebuilt or removed)."""
    tree = material.node_tree if material else None
    if tree and tree.animation_data and tree.animation_data.action:
        act = tree.animation_data.action
        tree.animation_data.action = None
        if act.users == 0:
            bpy.data.actions.remove(act)
