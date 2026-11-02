"""S0-02: speed of writing many keys into Blender 5.x layered actions.

Writes 200 objects x 10 channels x 30 keys = 60,000 keys with three methods:
  A) keyframe_insert per key (baseline, measured on a small subset and extrapolated)
  B) one action per object, channelbag.fcurves.new + keyframe_points.add + foreach_set
  C) one shared action with one slot per object (same bulk write)
"""
import time
import bpy
import numpy as np

N_OBJ, N_KEYS = 200, 30
CHANNELS = [("location", 3), ("rotation_quaternion", 4), ("scale", 3)]


def _objects(prefix, coll):
    obs = []
    for i in range(N_OBJ):
        ob = bpy.data.objects.new(f"{prefix}{i:03d}", None)
        ob.rotation_mode = "QUATERNION"
        coll.objects.link(ob)
        obs.append(ob)
    return obs


def _values(i, comp):
    t = np.arange(N_KEYS, dtype=np.float32)
    return np.sin(t * 0.3 + i + comp).astype(np.float32)


def _write_channelbag(cb, i):
    frames = np.arange(1, N_KEYS + 1, dtype=np.float32)
    for path, n in CHANNELS:
        for c in range(n):
            fc = cb.fcurves.new(path, index=c)
            kp = fc.keyframe_points
            kp.add(N_KEYS)
            co = np.empty(N_KEYS * 2, dtype=np.float32)
            co[0::2] = frames
            co[1::2] = _values(i, c)
            kp.foreach_set("co", co)
            # 1 == 'LINEAR' in the keyframe interpolation enum
            kp.foreach_set("interpolation", np.ones(N_KEYS, dtype=np.int32))
            fc.update()


def method_b(coll):
    obs = _objects("B_", coll)
    t0 = time.perf_counter()
    for i, ob in enumerate(obs):
        act = bpy.data.actions.new(f"B_act_{i:03d}")
        slot = act.slots.new(id_type="OBJECT", name=ob.name)
        strip = act.layers.new("Layer").strips.new(type="KEYFRAME")
        _write_channelbag(strip.channelbag(slot, ensure=True), i)
        ob.animation_data_create()
        ob.animation_data.action = act
        ob.animation_data.action_slot = slot
    return time.perf_counter() - t0


def method_c(coll):
    obs = _objects("C_", coll)
    t0 = time.perf_counter()
    act = bpy.data.actions.new("C_shared")
    strip = act.layers.new("Layer").strips.new(type="KEYFRAME")
    for i, ob in enumerate(obs):
        slot = act.slots.new(id_type="OBJECT", name=ob.name)
        _write_channelbag(strip.channelbag(slot, ensure=True), i)
        ob.animation_data_create()
        ob.animation_data.action = act
        ob.animation_data.action_slot = slot
    return time.perf_counter() - t0


def method_a(coll, n_obj=10):
    obs = _objects("A_", coll)[:n_obj]
    t0 = time.perf_counter()
    for i, ob in enumerate(obs):
        for k in range(N_KEYS):
            ob.location = [float(_values(i, c)[k]) for c in range(3)]
            ob.keyframe_insert("location", frame=k + 1)
            ob.rotation_quaternion = [float(_values(i, c)[k]) for c in range(4)]
            ob.keyframe_insert("rotation_quaternion", frame=k + 1)
            ob.scale = [float(_values(i, c)[k]) for c in range(3)]
            ob.keyframe_insert("scale", frame=k + 1)
    return (time.perf_counter() - t0) * N_OBJ / n_obj


def run():
    coll = bpy.data.collections.new("_s0_02")
    bpy.context.scene.collection.children.link(coll)
    res = {"keys": N_OBJ * N_KEYS * 10}
    res["B_per_object_action_s"] = round(method_b(coll), 3)
    res["C_shared_action_s"] = round(method_c(coll), 3)
    res["A_keyframe_insert_extrapolated_s"] = round(method_a(coll), 3)
    # sanity: evaluated value at frame 5 of one object matches the written data
    bpy.context.scene.frame_set(5)
    ob = bpy.data.objects["C_007"]
    res["check_C_007_loc_x_f5"] = [round(ob.location.x, 4), round(float(_values(7, 0)[4]), 4)]
    t0 = time.perf_counter()
    for f in range(1, N_KEYS + 1):
        bpy.context.scene.frame_set(f)
    res["frame_set_per_frame_ms"] = round((time.perf_counter() - t0) / N_KEYS * 1000, 2)
    return res
