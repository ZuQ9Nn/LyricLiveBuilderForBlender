"""Tracks -> keyframes in one layered action per object (prototype S0-02)."""
import bpy
import numpy as np

# track prop -> (data path, invert for hide flags)
PATHS = {"location": "location", "rotation": "rotation_quaternion", "scale": "scale", "color": "color"}
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


def apply(ob, tracks, fps, frame_start):
    """Write the tracks of one node onto its object."""
    if not tracks:
        return
    act = bpy.data.actions.new(f"LLB_{ob.name}")
    slot = act.slots.new(id_type="OBJECT", name=ob.name)
    cb = act.layers.new("LLB").strips.new(type="KEYFRAME").channelbag(slot, ensure=True)
    for tr in tracks:
        frames = frame_start + tr.times.astype(np.float64) * fps
        if tr.prop == "active":
            hidden = 1.0 - tr.values[:, 0]
            for path in ("hide_viewport", "hide_render"):
                _fcurve(cb, path, 0, frames, hidden, CONSTANT)
            continue
        interp = CONSTANT if tr.interp == "constant" else LINEAR
        for c in range(tr.values.shape[1]):
            _fcurve(cb, PATHS[tr.prop], c, frames, tr.values[:, c], interp)
    ob.animation_data_create()
    ob.animation_data.action = act
    ob.animation_data.action_slot = slot
