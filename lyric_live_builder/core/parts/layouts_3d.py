"""Layouts only for 3D (extruded) lines: they show the sides of the glyphs (spec §7.3)."""
import math

import numpy as np

from .. import xform
from ..registry import GlyphPlacement, LayoutPart, Placement, register
from .common import DEG, fit_em, flat, row


class _Layout3D(LayoutPart):
    supports_2d = False
    only_3d = True


@register("layout", "slanted_wall")
class SlantedWall(_Layout3D):
    name = "Slanted Wall"
    tags = ("graphic", "editorial", "pop")
    weight = 1.2

    def plan(self, rng, ctx):
        return {"angle": rng.pick([1, -1]) * rng.range(30, 40) * DEG}

    def place(self, ctx, params):
        # turned about the vertical axis so the extruded sides face the viewer
        return flat(ctx, params, extra_rot=xform.yaw(params["angle"]))


@register("layout", "stairs")
class Stairs(_Layout3D):
    name = "Depth Stairs"
    tags = ("graphic", "pop", "glitch")
    weight = 1.0

    def plan(self, rng, ctx):
        return {"step": rng.range(0.35, 0.6), "rise": rng.range(0.0, 0.15)}

    def place(self, ctx, params):
        p = flat(ctx, params)
        for k, g in enumerate(p.glyphs):
            back = k * params["step"] * p.em
            # spread deeper glyphs sideways so perspective does not slide them behind the nearer ones
            g.loc = np.array([g.loc[0] * (ctx.distance + back) / ctx.distance, back, k * params["rise"] * p.em])
        return p


@register("layout", "floor")
class Floor(_Layout3D):
    name = "Lying on the Floor"
    tags = ("calm", "emotional", "graphic")
    weight = 0.8
    fixed_distance = "near"
    keepable = False                   # ignores the slot elevation: two slots on one side meet on the floor

    def plan(self, rng, ctx):
        return {"distance": rng.range(1.6, 2.4)}

    def place(self, ctx, params):
        d = params["distance"]
        em = fit_em(ctx, sum(ctx.adv), d, max_angle=60)
        em = max(em, 0.25)                                       # readable when looking down
        em = min(em, 2 * d * math.tan(55 * DEG / 2) / max(sum(ctx.adv), 1e-6))
        az = ctx.anchor[0]
        loc = np.array([d * math.sin(az), d * math.cos(az), 0.01 + ctx.depth * em / 2])
        # face up, the tops of the letters away from the viewer
        rot = xform.mul(xform.yaw(-az), xform.pitch(-math.pi / 2))
        glyphs = [GlyphPlacement(i, np.array([x, 0.0, 0.0])) for i, x in row(ctx, em)]
        return Placement(loc, rot, em, glyphs)


@register("layout", "standing")
class Standing(_Layout3D):
    name = "Standing Around"
    tags = ("pop", "graphic")
    weight = 0.8
    big = True
    anchored = False
    fixed_distance = "near"
    exit_ok = ("topple", "collapse", "fade", "shrink")

    def fits(self, n_chars):
        return 2 <= n_chars <= 14

    def plan(self, rng, ctx):
        return {"radius": rng.range(2.2, 2.8), "start": rng.range(-50, -20) * DEG}

    def place(self, ctx, params):
        r = params["radius"]
        em = 0.45
        positions = row(ctx, em)
        step = min(14 * DEG, 200 * DEG / max(1, len(positions)))
        glyphs = []
        for k, (i, _) in enumerate(positions):
            a = params["start"] + k * step
            # standing on the floor like blocks, each facing the viewer
            glyphs.append(GlyphPlacement(i, np.array([r * math.sin(a), r * math.cos(a), em / 2]), xform.facing(a, 0.0)))
        return Placement(np.zeros(3), xform.IDENTITY.copy(), em, glyphs)


@register("layout", "approach")
class Approach(_Layout3D):
    name = "Approaching"
    tags = ("glitch", "pop", "graphic")
    weight = 0.6
    big = True
    anchored = False
    enter_ok = ("fade", "pop_sing", "zoom")
    exit_ok = ("fade", "shrink")

    def plan(self, rng, ctx):
        return {"side": rng.pick([1, -1]), "far": rng.range(22, 30)}

    def place(self, ctx, params):
        em = 1.6                                                 # a huge line far away
        glyphs = [GlyphPlacement(i, np.array([x, 0.0, 0.0])) for i, x in row(ctx, em)]
        width = sum(ctx.adv) * em
        params["offset"] = params["side"] * (width / 2 + 1.2)    # passes beside the viewer, not through
        return Placement(np.array([params["offset"], params["far"], ctx.eye + 0.6]), xform.IDENTITY.copy(), em, glyphs)

    def group_motion(self, ctx, params, placement, t):
        t0, t1 = ctx.span                                         # takes the whole line to pass by
        k = np.clip((t - t0) / max(t1 - t0, 1e-3), 0, 1)
        k = k * k * (3 - 2 * k)
        y = params["far"] + (-3.0 - params["far"]) * k            # from far ahead to behind the viewer
        loc = np.stack([np.full_like(t, params["offset"]), y, np.full_like(t, ctx.eye + 0.6)], axis=-1)
        return loc, np.broadcast_to(xform.IDENTITY, (len(t), 4))


@register("layout", "cube")
class Cube(_Layout3D):
    name = "Rotating Cube"
    tags = ("graphic", "pop", "glitch")
    weight = 0.6
    big = True
    enter_ok = ("fade", "pop_sing", "zoom")

    def fits(self, n_chars):
        return n_chars >= 4

    def _faces(self, ctx):
        """Chunks merged into at most 4 faces: [(first char index, end index)]."""
        chunks = ctx.chunks or [ctx.text]
        starts, pos = [], 0
        for c in chunks:
            i = ctx.text.find(c, pos)
            i = pos if i < 0 else i
            starts.append(i)
            pos = i + len(c)
        k = max(1, -(-len(chunks) // 4))
        firsts = starts[::k]
        return list(zip(firsts, firsts[1:] + [len(ctx.text)]))

    def place(self, ctx, params):
        faces = self._faces(ctx)
        widest = max(sum(ctx.adv[a:b]) for a, b in faces) or 1.0
        em = fit_em(ctx, widest, ctx.distance, max_angle=40)
        size = widest * em * 1.15
        glyphs = []
        for f, (a, b) in enumerate(faces):
            x = -sum(ctx.adv[a:b]) * em / 2
            face = xform.yaw(f * math.pi / 2)
            for i in range(a, b):
                w = ctx.adv[i] * em
                if not ctx.text[i].isspace():
                    p = np.array([x + w / 2, -size / 2 - 0.01, 0.0])
                    glyphs.append(GlyphPlacement(i, xform.rotate(face, p), face))
                x += w
        params["faces"] = [a for a, _ in faces]
        params["face_of"] = {g.char_index: f for f, (a, b) in enumerate(faces) for g in glyphs if a <= g.char_index < b}
        loc = np.array([0.0, 0.0, ctx.eye]) + ctx.distance * xform.direction(ctx.anchor[0], 0.0)
        return Placement(loc, xform.facing(ctx.anchor[0], 0.0), em, glyphs)

    def _turns(self, ctx, params):
        return [ctx.char_times[min(s, len(ctx.char_times) - 1)] - 0.35 for s in params["faces"][1:]]

    def shown(self, ctx, params, placement):
        # a face is shown from its turn until the next turn has finished (no edge-on glyphs)
        turns = [-1e9] + self._turns(ctx, params) + [1e9]
        out = []
        for g in placement.glyphs:
            f = params["face_of"][g.char_index]
            out.append((turns[f], turns[f + 1] + 0.35))
        return out

    def group_motion(self, ctx, params, placement, t):
        # quarter turn toward the next face when its first character is sung
        angle = np.zeros_like(t)
        for f, start in enumerate(params["faces"][1:], 1):
            ts = ctx.char_times[min(start, len(ctx.char_times) - 1)] - 0.35
            k = np.clip((t - ts) / 0.35, 0, 1)
            angle -= (math.pi / 2) * (k * k * (3 - 2 * k))
        rot = xform.mul(placement.rot, xform.yaw(angle))
        return np.broadcast_to(placement.loc, (len(t), 3)), rot
