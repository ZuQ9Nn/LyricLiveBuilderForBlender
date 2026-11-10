"""Particle presets and their closed-form state (spec §8.1, design §8.1).

Every particle is a pure function of time: particle i of a continuous emitter is reborn every
lifetime L_i, with a new random spawn per generation. The preview evaluates this each frame;
the Unity export maps the same preset fields to ParticleSystem modules (Unity simulates it
itself, so the two only look alike)."""
import math

import numpy as np

from ..rng import h_np

SHAPES_2D = ("circle_dot", "ring", "soft_dot", "triangle", "square", "cross", "hexagon", "octagon", "bubble",
             "star", "sparkle", "petal", "heart", "note", "snowflake")          # atlas tile = index
SHAPES_3D = ("cube", "hexprism", "octahedron", "icosahedron", "shard", "tetra")
EYE = np.array([0.0, 0.0, 1.5])
MIN_EYE_DISTANCE = 0.6
_ALL = ("glitch", "calm", "pop", "graphic", "editorial", "emotional")

# rate / max_particles are at strength 1; colours are style roles (core.styles.palette)
PRESETS = {
    "motes": dict(name="Light Motes", tags=_ALL, shape="soft_dot", emitter="sphere", radius=(2.0, 9.0),
                  rate=40, life=(4, 7), speed=(0.05, 0.2), direction="random", size=(0.03, 0.08), noise=0.4,
                  noise_freq=0.3, size_life="twinkle", fade=(0.2, 0.4), colors=("ghostA", "ghostB", "white"),
                  blend="add", max=260, prewarm=True),
    "stars": dict(name="Twinkling Stars", tags=("calm", "emotional", "editorial"), shape="sparkle", emitter="sky_shell",
                  radius=(25.0, 35.0), rate=25, life=(8, 14), speed=(0.0, 0.0), direction="random", size=(0.15, 0.45),
                  size_life="twinkle", fade=(0.15, 0.3), colors=("white", "sub"), blend="add", max=300, prewarm=True),
    "shooting": dict(name="Shooting Stars", tags=("emotional", "calm", "pop"), shape="soft_dot", emitter="sky_shell",
                     radius=(28.0, 32.0), rate=0.8, life=(0.6, 1.0), speed=(18.0, 26.0), direction="fall",
                     size=(0.18, 0.3), trail=0.25, fade=(0.1, 0.5), colors=("white", "accent2"), blend="add", max=6),
    "snow": dict(name="Snowfall", tags=("calm", "emotional"), shape="snowflake", emitter="sky_disc", radius=(1.2, 14.0),
                 height=(8.0, 10.0), rate=30, life=(12, 16), speed=(0.4, 0.8), direction="down", size=(0.05, 0.12),
                 noise=0.6, noise_freq=0.25, spin=(-60, 60), fade=(0.1, 0.2), colors=("white", "sub"), blend="alpha",
                 max=400, prewarm=True),
    "petals": dict(name="Falling Petals", tags=("calm", "emotional", "pop"), shape="petal", emitter="sky_disc",
                   radius=(1.2, 12.0), height=(6.0, 8.0), rate=18, life=(8, 11), speed=(0.6, 1.0), direction="down",
                   size=(0.06, 0.12), noise=0.8, noise_freq=0.3, spin=(-120, 120), fade=(0.1, 0.2),
                   colors=("accent", "ghostA"), blend="alpha", max=200, prewarm=True),
    "bubbles": dict(name="Rising Bubbles", tags=("calm", "pop"), shape="bubble", emitter="floor_disc", radius=(1.2, 10.0),
                    height=(0.0, 0.3), rate=22, life=(6, 10), speed=(0.4, 0.9), direction="up", size=(0.05, 0.2),
                    noise=0.3, noise_freq=0.4, fade=(0.1, 0.3), colors=("white", "ghostB"), blend="add", max=220,
                    prewarm=True),
    "fireworks": dict(name="Fireworks", tags=("pop", "emotional", "glitch"), shape="circle_dot", emitter="burst",
                      burst=dict(interval=(1.2, 2.2), count=48, speed=(4.0, 7.0), life=(1.2, 1.8),
                                 sub=dict(count=3, speed=1.5, life=0.5)),
                      gravity=2.0, size=(0.06, 0.1), trail=0.12, fade=(0.0, 0.5),
                      colors=("accent", "ghostA", "ghostB"), blend="add", max=600),
    "hearts": dict(name="Floating Hearts", tags=("pop",), shape="heart", emitter="floor_disc", radius=(1.5, 8.0),
                   height=(0.0, 0.5), rate=8, life=(5, 8), speed=(0.3, 0.6), direction="up", size=(0.1, 0.22),
                   noise=0.3, noise_freq=0.3, size_life="grow", fade=(0.15, 0.3), colors=("accent", "ghostA"),
                   blend="alpha", max=80),
    "notes": dict(name="Music Notes", tags=("pop", "graphic"), shape="note", emitter="ring", radius=(3.0, 6.0),
                  height=(0.5, 2.5), rate=7, life=(5, 8), speed=(0.2, 0.5), direction="orbit", rise=0.2,
                  size=(0.12, 0.25), fade=(0.15, 0.3), colors=("fg", "accent2"), blend="alpha", max=70),
    "cubes": dict(name="Floating Cubes", tags=("graphic", "glitch", "editorial"), shape="cube", emitter="sphere",
                  radius=(3.0, 10.0), rate=6, life=(8, 12), speed=(0.05, 0.15), direction="random", size=(0.08, 0.24),
                  spin=(-40, 40), fade=(0.15, 0.2), colors=("ghostA", "ghostB", "sub"), blend="alpha", max=80,
                  prewarm=True),
    "shard_ring": dict(name="Orbiting Shards", tags=("graphic", "glitch"), shape="shard", emitter="ring",
                       radius=(2.5, 3.5), height=(0.2, 3.2), height_pick=True, rate=10, life=(10, 14),
                       speed=(0.6, 1.0), direction="orbit", size=(0.1, 0.25), spin=(-90, 90), fade=(0.1, 0.2),
                       colors=("accent", "sub"), blend="alpha", max=140, prewarm=True),
    "warp": dict(name="Warp Streaks", tags=("glitch", "pop"), shape="soft_dot", emitter="tunnel", radius=(3.0, 9.0),
                 rate=30, life=(3.5, 4.0), speed=(12.0, 15.0), direction="toward", size=(0.04, 0.08), trail=0.3,
                 fade=(0.1, 0.2), colors=("white", "ghostB"), blend="add", max=130),
    # mixed shapes (one per particle): the 2D ones are neighbours in the atlas
    "shape_confetti": dict(name="Shape Confetti", tags=("pop", "graphic", "emotional"), shape="triangle",
                           shapes=("triangle", "square", "cross", "hexagon", "octagon"), emitter="sky_disc",
                           radius=(1.2, 10.0), height=(6.0, 8.0), rate=20, life=(8, 11), speed=(0.5, 0.9),
                           direction="down", size=(0.08, 0.16), noise=0.7, noise_freq=0.3, spin=(-150, 150),
                           fade=(0.1, 0.2), colors=("accent", "ghostA", "ghostB", "white"), blend="alpha", max=220,
                           prewarm=True),
    "shape_float": dict(name="Floating Shapes", tags=("graphic", "calm", "editorial", "glitch"), shape="square",
                        shapes=("square", "cross", "hexagon", "octagon"), emitter="sphere", radius=(2.5, 9.0),
                        rate=12, life=(6, 9), speed=(0.05, 0.15), direction="random", size=(0.14, 0.32), noise=0.35,
                        noise_freq=0.25, spin=(-40, 40), fade=(0.2, 0.3), colors=("accent", "ghostA", "white"),
                        blend="add", max=120, prewarm=True),
    "poly_float": dict(name="Floating Polyhedra", tags=("graphic", "editorial", "calm"), shape="octahedron",
                       shapes=("octahedron", "icosahedron", "tetra", "hexprism"), emitter="sphere", radius=(3.0, 10.0),
                       rate=6, life=(8, 12), speed=(0.05, 0.15), direction="random", size=(0.1, 0.26),
                       spin=(-50, 50), fade=(0.15, 0.2), colors=("ghostA", "ghostB", "accent"), blend="alpha", max=80,
                       prewarm=True),
    # stepped motion: straight runs along one axis at a time, turning at right angles, with a light tail
    "circuit": dict(name="Circuit", tags=("glitch", "graphic"), shape="square", emitter="sphere", radius=(2.5, 8.0),
                    rate=42, life=(2.5, 4.0), direction="steps", steps=dict(axes="xyxzyxzy", speed=1.6),
                    size=(0.09, 0.15), tail=dict(time=0.6, width=0.04), fade=(0.1, 0.2),
                    colors=("accent", "ghostA", "ghostB"), blend="add", max=150),
    # evenly spaced dots (filled and hollow) flowing round the audience, above and below
    "dot_march": dict(name="Dot March", tags=("graphic", "pop", "editorial"), shape="circle_dot",
                      shapes=("circle_dot", "ring"), emitter="point_orbit", radius=(5.0, 5.0), angle=-45.0,
                      height=(0.4, 3.2), height_pick=True, rate=10, life=(15.0, 15.0), even=True,
                      speed=(2.0, 2.0), direction="orbit", size=(0.14, 0.14), fade=(0.03, 0.06),
                      colors=("fg", "white"), blend="add", max=150),
    # line effects (core/parts/lines.py): drawn as lines, picked like particles
    "horizon": dict(name="Horizon Line", tags=("calm", "emotional", "editorial"), shape="circle_dot", emitter="lines",
                    lines=dict(kind="ring", radius=14.0, height=1.5, segments=128, draw=2.0, erase=1.2,
                               layers=((0.05, 1.0, 0, 0), (0.9, 0.18, 1, 1))),     # (width, alpha, soft, colour)
                    rate=0, life=(1, 1), size=(0.05, 0.05), colors=("white", "accent"), blend="add", max=1),
    "plexus": dict(name="Plexus", tags=("graphic", "calm", "glitch"), shape="circle_dot", emitter="lines",
                   lines=dict(kind="plexus", box=((-8.0, 8.0), (-1.0, 12.0), (3.0, 8.5)), link=2.8, amp=0.7,
                              speed=0.38, width=0.02, dot=0.09, alpha=0.6, draw=2.5, erase=1.5),
                   rate=0, life=(1, 1), size=(0.09, 0.09), colors=("ghostA", "white"), blend="add", max=44),
    # for lines: a short burst around the text (impact lines, line overrides)
    "sparkle_burst": dict(name="Sparkle Burst", tags=_ALL, shape="sparkle", emitter="burst",
                          burst=dict(interval=None, count=36, speed=(1.0, 2.2), life=(0.8, 1.4), sub=None),
                          gravity=0.3, size=(0.04, 0.09), fade=(0.0, 0.6), colors=("accent", "white"), blend="add",
                          max=120),
}
AMBIENT = [k for k in PRESETS if k != "sparkle_burst"]          # the section presets
STEP_AXES = ("xyz", "yzx", "zxy")          # stepped motion: the axis order of the 3 systems (particle i: i % 3)
TAIL_POINTS = 8                            # preview tail: earlier positions per particle


def shapes_of(p):
    """The shapes a preset's particles take (one each)."""
    return tuple(p.get("shapes") or (p["shape"],))


def particle_shapes(p, seed, n):
    """(n,) index into shapes_of(p) of particle slot 0..n-1: fixed for the slot, over all its lives."""
    k = len(shapes_of(p))
    return (h_np(seed, np.arange(n), 0, 60) % k).astype(np.int64) if k > 1 else np.zeros(n, dtype=np.int64)


def tile_range(p):
    """(first, last) atlas tiles of a 2D preset's shapes (they must be neighbours)."""
    idx = [SHAPES_2D.index(s) for s in shapes_of(p)]
    if idx != list(range(idx[0], idx[0] + len(idx))):
        raise ValueError(f"2D shapes must be neighbours in the atlas: {shapes_of(p)}")
    return idx[0], idx[-1]


def _u(seed, i, gen, k):
    """Uniform 0..1 per particle and generation (vectorized hash)."""
    return h_np(seed, i, gen, k) / 4294967296.0


def _rng(lohi, u):
    lo, hi = lohi
    return lo + (hi - lo) * u


def _unit(u1, u2):
    z = 2 * u1 - 1
    a = 2 * math.pi * u2
    r = np.sqrt(np.maximum(0.0, 1 - z * z))
    return np.stack([r * np.cos(a), r * np.sin(a), z], axis=-1)


def scale(preset, strength):
    """Preset fields scaled by the particles strength (0..1): rate and count."""
    k = 0.35 + 1.3 * strength
    out = dict(preset)
    out["rate"] = preset.get("rate", 0) * k
    out["max"] = max(4, int(round(preset["max"] * k)))
    if preset.get("burst"):
        b = dict(preset["burst"])
        b["count"] = max(6, int(round(b["count"] * (0.5 + 0.5 * k))))
        out["burst"] = b
    return out


def continuous_count(p):
    if p["emitter"] in ("burst", "lines"):
        return 0
    n = int(min(p["max"], math.ceil(p["rate"] * (p["life"][0] + p["life"][1]) / 2)))
    if p.get("even") and p.get("height_pick"):          # two evenly spaced streams: the same count in each
        n -= n % 2
    return n


def burst_capacity(p, bursts):
    """Most burst particles alive at once (primaries + their secondaries)."""
    if not bursts:
        return 0
    b = p["burst"]
    span = b["life"][1] + (b["sub"]["life"] if b.get("sub") else 0)
    per = b["count"] * (1 + (b["sub"]["count"] if b.get("sub") else 0))
    times = sorted(x["t"] for x in bursts)
    most = max(sum(1 for u in times if t <= u < t + span) for t in times)
    return min(p["max"], most * per)


def _spawn(p, seed, i, gen):
    u = [_u(seed, i, gen, k) for k in range(6)]
    kind = p["emitter"]
    r_in, r_out = p.get("radius", (1.0, 2.0))
    if kind == "point_orbit":                         # one point (one per height): the stream stays evenly spaced
        a = math.radians(p.get("angle", 0.0))
        lo, hi = p.get("height", (0.0, 0.0))
        z = np.where(i % 2 == 0, lo, hi) if p.get("height_pick") else np.full(np.shape(i), (lo + hi) / 2)
        return np.stack([np.full(z.shape, math.sin(a) * r_in), np.full(z.shape, math.cos(a) * r_in), z], axis=-1)
    if kind in ("sphere", "sky_shell"):
        r = _rng((r_in, r_out), u[0])
        d = _unit(u[1], u[2])
        if kind == "sky_shell":
            d[..., 2] = 0.08 + 0.85 * np.abs(d[..., 2])
            d /= np.linalg.norm(d, axis=-1, keepdims=True)
        pos = EYE + d * r[..., None]
        pos[..., 2] = np.maximum(pos[..., 2], 0.1)
        return pos
    if kind in ("sky_disc", "floor_disc", "ring"):
        r = np.sqrt(_rng((r_in ** 2, r_out ** 2), u[0])) if kind != "ring" else _rng((r_in, r_out), u[0])
        a = 2 * math.pi * u[1]
        lo, hi = p.get("height", (0.0, 0.0))
        z = np.where(u[2] < 0.5, lo, hi) if p.get("height_pick") else _rng((lo, hi), u[2])
        return np.stack([np.sin(a) * r, np.cos(a) * r, z], axis=-1)
    if kind == "tunnel":
        r = _rng((r_in, r_out), u[0])
        a = 2 * math.pi * u[1]
        return np.stack([np.cos(a) * r, np.full(r.shape, 40.0), EYE[2] + np.sin(a) * r], axis=-1)
    raise KeyError(kind)


def _velocity(p, seed, i, gen, spawn):
    u = [_u(seed, i, gen, 10 + k) for k in range(3)]
    speed = _rng(p.get("speed", (0.0, 0.0)), u[0])[..., None]
    d = p.get("direction", "random")
    if d == "random":
        v = _unit(u[1], u[2])
    elif d == "up":
        v = np.broadcast_to([0.0, 0.0, 1.0], spawn.shape).copy()
    elif d == "down":
        v = np.broadcast_to([0.0, 0.0, -1.0], spawn.shape).copy()
    elif d == "toward":
        v = np.broadcast_to([0.0, -1.0, 0.0], spawn.shape).copy()
    elif d == "fall":                                   # across the sky and slightly down
        a = 2 * math.pi * u[1]
        v = np.stack([np.cos(a), np.sin(a), np.full(a.shape, -0.35)], axis=-1)
        v /= np.linalg.norm(v, axis=-1, keepdims=True)
    else:                                               # orbit / steps: handled in _position
        v = np.zeros(spawn.shape)
    return v * speed


def step_axes(p, i):
    """(n, segments) axis index 0..2 of each stepped segment of particles i (Blender axes)."""
    axes = p["steps"]["axes"]
    table = np.array([["xyz".index(order["xyz".index(a)]) for a in axes] for order in STEP_AXES])
    return table[np.asarray(i) % 3]


def _steps(p, age, life, seed, i, gen):
    """Stepped motion: segment k of the life moves along one axis only; each axis has one speed per particle."""
    ax = step_axes(p, i)
    n = ax.shape[1]
    hi = p["steps"]["speed"]
    sp = np.stack([(2 * _u(seed, i, gen, 15 + k) - 1) * hi for k in range(3)], axis=-1)        # (m, 3)
    d = (life / n)[:, None]
    spent = np.clip(age[:, None] - np.arange(n) * d, 0, d)                                      # (m, n)
    comp = np.take_along_axis(sp, ax, axis=1)
    disp = np.stack([np.sum(np.where(ax == a, comp * spent, 0.0), axis=1) for a in range(3)], axis=-1)
    k = np.clip((age / (life / n)).astype(np.int64), 0, n - 1)
    v = np.zeros_like(sp)
    cur = ax[np.arange(len(k)), k]
    v[np.arange(len(k)), cur] = sp[np.arange(len(k)), cur]
    return disp, v


def _position(p, spawn, vel, age, seed, i, gen, life=None):
    if p.get("steps"):
        disp, v = _steps(p, age, life, seed, i, gen)
        return spawn + disp, v
    if p.get("direction") == "orbit":
        r = np.linalg.norm(spawn[..., :2], axis=-1)
        omega = _rng(p["speed"], _u(seed, i, gen, 10)) / np.maximum(r, 0.1)
        a = np.arctan2(spawn[..., 0], spawn[..., 1]) + omega * age
        pos = np.stack([np.sin(a) * r, np.cos(a) * r, spawn[..., 2] + p.get("rise", 0.0) * age], axis=-1)
        tangent = np.stack([np.cos(a), -np.sin(a), np.zeros_like(a)], axis=-1) * (omega * r)[..., None]
        return pos, tangent
    pos = spawn + vel * age[..., None]
    g = p.get("gravity", 0.0)
    pos[..., 2] -= 0.5 * g * age ** 2
    v_now = vel.copy()
    v_now[..., 2] -= g * age
    amp = p.get("noise", 0.0)
    if amp:
        f = 2 * math.pi * p.get("noise_freq", 0.3)
        ph = np.stack([_u(seed, i, gen, 20 + k) * 2 * math.pi for k in range(3)], axis=-1)
        rate = np.array([1.0, 1.3, 0.7])
        pos += amp * (np.sin(f * rate * age[..., None] + ph) - np.sin(ph))
    return pos, v_now


def _look(p, age, life, seed, i, gen, colors):
    """size, alpha, colour, spin of particles of the given age."""
    x = np.clip(age / life, 0, 1)
    size = _rng(p["size"], _u(seed, i, gen, 30))
    sl = p.get("size_life", "flat")
    if sl == "grow":
        size = size * (0.3 + 0.7 * (1 - (1 - x) ** 3))
    elif sl == "shrink":
        size = size * (1 - 0.8 * x)
    elif sl == "twinkle":
        size = size * (0.6 + 0.4 * np.sin(age * 5.0 + _u(seed, i, gen, 31) * 6.283))
    fi, fo = p.get("fade", (0.1, 0.3))
    alpha = np.ones_like(x)
    if fi > 0:
        alpha = np.minimum(alpha, x / fi)
    if fo > 0:
        alpha = np.minimum(alpha, (1 - x) / fo)
    cols = np.asarray(colors, dtype=np.float64)
    col = cols[(h_np(seed, i, gen, 32) % len(cols)).astype(np.int64)]
    lo, hi = p.get("spin", (0.0, 0.0))
    start = _u(seed, i, gen, 33) * 6.283 if (lo or hi) else 0.0         # like Unity: a start angle only when spinning
    spin = start + np.radians(_rng((lo, hi), _u(seed, i, gen, 34))) * age
    return size, np.clip(alpha, 0, 1), col, spin


def _interp(keys, t):
    if not keys:
        return np.ones_like(np.asarray(t, dtype=np.float64))
    ts, vs = zip(*keys)
    return np.interp(t, ts, vs)


def envelope(spec, t):
    """Emitter-wide alpha: fades in after start and out after end (exported as the emitter's colour track)."""
    a = np.clip((t - spec["start"]) / spec.get("fade_in", 0.8), 0, 1)
    return float(np.minimum(a, np.clip(1 - (t - spec["end"]) / spec.get("fade_out", 1.0), 0, 1)))


def state(spec, t):
    """Particles of an emitter spec at time t -> dict of arrays (capacity long); dead ones have alpha 0."""
    p = spec["preset"]
    seed = spec["seed"]
    n = spec["count"]
    cap = n + spec["pool"]
    out = {"pos": np.zeros((cap, 3)), "vel": np.zeros((cap, 3)), "size": np.zeros(cap), "alpha": np.zeros(cap),
           "color": np.ones((cap, 3)), "spin": np.zeros(cap)}
    if p.get("tail"):
        out["tail"] = np.zeros((cap, TAIL_POINTS, 3))
    env = envelope(spec, t)
    if env <= 0 or cap == 0:
        return out
    if n:
        i = np.arange(n)
        life = _rng(p["life"], _u(seed, i, 0, 40))
        phase = i / n if p.get("even") else _u(seed, i, 0, 41)        # even: one birth every life / n
        u = (t - spec["start"]) / life + phase
        gen = np.floor(u).astype(np.int64)
        age = (u - gen) * life
        birth = t - age
        alive = birth < spec["end"]
        if not p.get("prewarm"):
            alive &= birth >= spec["start"]
        want = _interp(spec.get("intensity"), np.maximum(birth, spec["start"]))
        alive &= _u(seed, i, gen + 7, 42) < want
        gen_u = gen & 0x7FFFFFFF
        spawn = _spawn(p, seed, i, gen_u)
        vel = _velocity(p, seed, i, gen_u, spawn)
        pos, v_now = _position(p, spawn, vel, age, seed, i, gen_u, life)
        size, alpha, col, spin = _look(p, age, life, seed, i, gen_u, spec["colors"])
        out["pos"][:n], out["vel"][:n], out["size"][:n] = pos, v_now, size
        out["alpha"][:n] = alpha * alive * env
        out["color"][:n], out["spin"][:n] = col, spin
        if p.get("tail"):                               # earlier positions in the same life (preview tail)
            dt = p["tail"]["time"] / TAIL_POINTS
            for k in range(TAIL_POINTS):
                out["tail"][:n, k] = _position(p, spawn, vel, np.maximum(age - (k + 1) * dt, 0.0), seed, i, gen_u,
                                               life)[0]
    if spec["pool"]:
        _bursts(spec, t, env, out, n)
    out["pos"] = _keep_away(out["pos"])                   # nothing comes closer than 0.6 m (design §7.2)
    if "tail" in out:
        out["tail"] = _keep_away(out["tail"])
    return out


def _keep_away(pos):
    v = pos - EYE
    d = np.linalg.norm(v, axis=-1, keepdims=True)
    return EYE + v / np.maximum(d, 1e-9) * np.maximum(d, MIN_EYE_DISTANCE)


def _bursts(spec, t, env, out, offset):
    p = spec["preset"]
    b = p["burst"]
    sub = b.get("sub")
    span = b["life"][1] + (sub["life"] if sub else 0)
    chunks = []
    for k, ev in enumerate(spec["bursts"]):
        age0 = t - ev["t"]
        if not 0 <= age0 < span:
            continue
        seed = spec["seed"] + 7919 * (k + 1)
        j = np.arange(b["count"])
        life = _rng(b["life"], _u(seed, j, 0, 50))
        d = _unit(_u(seed, j, 0, 51), _u(seed, j, 0, 52))
        speed = _rng(b["speed"], _u(seed, j, 0, 53))
        origin = np.asarray(ev["origin"], dtype=np.float64)

        def at(age):
            drag = 1.5
            s = (1 - np.exp(-drag * age)) / drag
            pos = origin + d * (speed * s)[..., None]
            pos[..., 2] -= 0.5 * p.get("gravity", 0.0) * age ** 2
            v = d * (speed * np.exp(-drag * age))[..., None]
            v[..., 2] -= p.get("gravity", 0.0) * age
            return pos, v
        age = np.full(b["count"], age0)
        pos, v = at(age)
        size, alpha, col, spin = _look(p, age, life, seed, j, 0, spec["colors"])
        chunks.append((pos, v, size, alpha * (age < life), col, spin))
        if sub:
            m = sub["count"]
            jj = np.repeat(j, m)
            kk = np.tile(np.arange(m), b["count"])
            age2 = age0 - life[jj]
            p0, _ = at(life)
            d2 = _unit(_u(seed, jj, kk + 1, 54), _u(seed, jj, kk + 1, 55))
            pos2 = p0[jj] + d2 * (sub["speed"] * np.clip(age2, 0, None))[..., None]
            alive2 = (age2 >= 0) & (age2 < sub["life"])
            a2 = np.clip(1 - age2 / sub["life"], 0, 1) * alive2
            chunks.append((pos2, d2 * sub["speed"], size[jj] * 0.6, a2, col[jj], spin[jj]))
    if not chunks:
        return
    cat = [np.concatenate(c) for c in zip(*chunks)]
    keep = np.flatnonzero(cat[3] > 0)[:spec["pool"]]
    m = len(keep)
    s = slice(offset, offset + m)
    out["pos"][s], out["vel"][s], out["size"][s] = cat[0][keep], cat[1][keep], cat[2][keep]
    out["alpha"][s], out["color"][s], out["spin"][s] = cat[3][keep] * env, cat[4][keep], cat[5][keep]
