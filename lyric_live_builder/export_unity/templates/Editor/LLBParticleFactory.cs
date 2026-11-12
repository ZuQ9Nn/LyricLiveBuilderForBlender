// LyricLive Builder: ParticleSystem from a description made by the add-on (design §8.1).
// All decisions are taken in Python; this only copies the fields into the modules.
using System.Collections.Generic;
using UnityEngine;

namespace LyricLive.Editor
{
    public static class LLBParticleFactory
    {
        static ParticleSystem.MinMaxCurve Range(float[] r, float scale = 1f) =>
            r == null || r.Length < 2 ? new ParticleSystem.MinMaxCurve(0f) : new ParticleSystem.MinMaxCurve(r[0] * scale, r[1] * scale);

        static bool Any(float[] r) => r != null && r.Length > 1 && (r[0] != 0f || r[1] != 0f);

        static Gradient Choices(float[] c)
        {
            // fixed-mode gradient sampled at random = one of the listed colours
            int n = Mathf.Max(1, c.Length / 4);
            var keys = new GradientColorKey[Mathf.Min(n, 8)];
            for (int i = 0; i < keys.Length; i++)
                keys[i] = new GradientColorKey(new Color(c[i * 4], c[i * 4 + 1], c[i * 4 + 2]), (i + 1f) / keys.Length);
            float a = c.Length >= 4 ? c[3] : 1f;            // the preset's opacity (the same for every colour)
            var g = new Gradient { mode = GradientMode.Fixed };
            g.SetKeys(keys, new[] { new GradientAlphaKey(a, 0f), new GradientAlphaKey(a, 1f) });
            return g;
        }

        static Gradient Fade(float fadeIn, float fadeOut)
        {
            var a = new List<GradientAlphaKey>();
            a.Add(new GradientAlphaKey(fadeIn > 0 ? 0f : 1f, 0f));
            if (fadeIn > 0) a.Add(new GradientAlphaKey(1f, Mathf.Clamp01(fadeIn)));
            if (fadeOut > 0) a.Add(new GradientAlphaKey(1f, Mathf.Clamp01(1f - fadeOut)));
            a.Add(new GradientAlphaKey(fadeOut > 0 ? 0f : 1f, 1f));
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) }, a.ToArray());
            return g;
        }

        static AnimationCurve SizeCurve(string kind)
        {
            switch (kind)
            {
                case "grow": return new AnimationCurve(new Keyframe(0, 0.3f), new Keyframe(0.4f, 0.9f), new Keyframe(1, 1));
                case "shrink": return AnimationCurve.Linear(0, 1, 1, 0.2f);
                case "pop":                                // pops up, settles, shrinks away (particles.POP_CURVE)
                    return new AnimationCurve(new Keyframe(0, 0), new Keyframe(0.12f, 1.2f), new Keyframe(0.22f, 1f),
                                              new Keyframe(0.8f, 1f), new Keyframe(1, 0));
                case "twinkle":
                    var k = new Keyframe[9];
                    for (int i = 0; i < k.Length; i++) k[i] = new Keyframe(i / 8f, i % 2 == 0 ? 1f : 0.55f);
                    return new AnimationCurve(k);
                default: return null;
            }
        }

        static AnimationCurve StepCurve(float[] v, int offset, int n)
        {
            // one flat value per segment of the life: infinite tangents hold each key until the next
            var keys = new Keyframe[n];
            for (int k = 0; k < n; k++)
                keys[k] = new Keyframe((float)k / n, v[offset + k], float.PositiveInfinity, float.PositiveInfinity);
            return new AnimationCurve(keys);
        }

        static ParticleSystem.MinMaxCurve Steps(LLBPSSteps s, int axis) =>
            new ParticleSystem.MinMaxCurve(1f, StepCurve(s.lo, axis * s.n, s.n), StepCurve(s.hi, axis * s.n, s.n));

        public static ParticleSystem Apply(GameObject go, LLBParticles d, Material mat, Mesh mesh, Mesh[] meshes = null,
                                           Material trailMat = null)
        {
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.playOnAwake = true;
            main.loop = d.looping;
            main.duration = Mathf.Max(0.1f, d.duration);
            main.prewarm = d.looping && d.prewarm;
            main.startLifetime = Range(d.life);
            main.startSpeed = Range(d.speed);
            main.startSize = Range(d.size);
            if (d.size3d != null && d.size3d.Length == 6)
            {
                main.startSize3D = true;                    // per-axis sizes (slabs)
                main.startSizeX = new ParticleSystem.MinMaxCurve(d.size3d[0], d.size3d[1]);
                main.startSizeY = new ParticleSystem.MinMaxCurve(d.size3d[2], d.size3d[3]);
                main.startSizeZ = new ParticleSystem.MinMaxCurve(d.size3d[4], d.size3d[5]);
            }
            main.gravityModifier = d.gravity;
            main.maxParticles = Mathf.Max(1, d.max);
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.startColor = new ParticleSystem.MinMaxGradient(Choices(d.colors)) { mode = ParticleSystemGradientMode.RandomColor };
            if (Any(d.spin)) main.startRotation = new ParticleSystem.MinMaxCurve(0f, Mathf.PI * 2f);
            if (d.tumble)
            {
                main.startRotation3D = true;                // any way round, no turning
                main.startRotationX = main.startRotationY = main.startRotationZ = new ParticleSystem.MinMaxCurve(0f, Mathf.PI * 2f);
            }

            var em = ps.emission;
            em.rateOverTime = d.rate;
            if (d.burst > 0) em.SetBursts(new[] { new ParticleSystem.Burst(0f, (short)d.burst) });

            var sh = ps.shape;
            sh.enabled = true;
            switch (d.shape.type)
            {
                case "Hemisphere": sh.shapeType = ParticleSystemShapeType.Hemisphere; break;
                case "Circle": sh.shapeType = ParticleSystemShapeType.Circle; break;
                case "Box": sh.shapeType = ParticleSystemShapeType.Box; break;
                case "Cone": sh.shapeType = ParticleSystemShapeType.Cone; sh.angle = d.shape.angle; break;
                default: sh.shapeType = ParticleSystemShapeType.Sphere; break;
            }
            sh.radius = Mathf.Max(0.001f, d.shape.radius);
            sh.radiusThickness = d.shape.thickness;
            sh.arc = 360f;
            sh.position = new Vector3(d.shape.position[0], d.shape.position[1], d.shape.position[2]);
            sh.rotation = new Vector3(d.shape.rotation[0], d.shape.rotation[1], d.shape.rotation[2]);
            sh.randomDirectionAmount = d.shape.randomDirection;

            var v = d.velocity;
            if (Any(v.x) || Any(v.y) || Any(v.z) || Any(v.orbitalY) || Any(v.radial))
            {
                var vel = ps.velocityOverLifetime;
                vel.enabled = true;
                vel.space = ParticleSystemSimulationSpace.Local;
                vel.x = Range(v.x); vel.y = Range(v.y); vel.z = Range(v.z);
                vel.orbitalX = new ParticleSystem.MinMaxCurve(0f, 0f);
                vel.orbitalY = Range(v.orbitalY);
                vel.orbitalZ = new ParticleSystem.MinMaxCurve(0f, 0f);
                if (Any(v.radial))
                {
                    vel.radial = Range(v.radial);           // toward the ring's own centre
                    vel.orbitalOffsetX = new ParticleSystem.MinMaxCurve(0f);
                    vel.orbitalOffsetY = new ParticleSystem.MinMaxCurve(v.offsetY);
                    vel.orbitalOffsetZ = new ParticleSystem.MinMaxCurve(0f);
                }
            }
            if (d.steps != null && d.steps.n > 0)
            {
                // stepped motion: one axis moves per segment; x, y and z must share the TwoCurves mode
                var vel = ps.velocityOverLifetime;
                vel.enabled = true;
                vel.space = ParticleSystemSimulationSpace.Local;
                vel.x = Steps(d.steps, 0); vel.y = Steps(d.steps, 1); vel.z = Steps(d.steps, 2);
            }
            if (d.noise != null && d.noise.strength > 0)
            {
                var nz = ps.noise;
                nz.enabled = true;
                nz.strength = d.noise.strength;
                nz.frequency = d.noise.frequency;
                nz.scrollSpeed = d.noise.scroll;
            }
            if (Any(d.spin))
            {
                var rot = ps.rotationOverLifetime;
                rot.enabled = true;
                rot.z = Range(d.spin, Mathf.Deg2Rad);
            }
            var col = ps.colorOverLifetime;
            col.enabled = true;
            col.color = new ParticleSystem.MinMaxGradient(Fade(d.fade[0], d.fade[1]));
            var sizeCurve = SizeCurve(d.sizeLife);
            if (sizeCurve != null)
            {
                var size = ps.sizeOverLifetime;
                size.enabled = true;
                size.size = new ParticleSystem.MinMaxCurve(1f, sizeCurve);
            }
            if (d.drag > 0)
            {
                var lim = ps.limitVelocityOverLifetime;
                lim.enabled = true;
                lim.limit = 1000f;                          // only the drag is wanted
                lim.drag = d.drag;
            }

            var r = go.GetComponent<ParticleSystemRenderer>();
            r.sharedMaterial = mat;
            if (d.renderer.mode == "Mesh" && mesh != null)
            {
                r.renderMode = ParticleSystemRenderMode.Mesh;
                r.mesh = mesh;
                if (meshes != null && meshes.Length > 1)
                {
                    r.SetMeshes(meshes);                    // one shape per particle, chosen at random
                    r.meshDistribution = ParticleSystemMeshDistribution.UniformRandom;
                }
            }
            else
            {
                r.renderMode = d.renderer.mode == "Stretch" ? ParticleSystemRenderMode.Stretch : ParticleSystemRenderMode.Billboard;
                r.velocityScale = d.renderer.stretch;
                r.lengthScale = d.renderer.length != 0f ? d.renderer.length : 1f;   // beams: their length
                if (d.renderer.tile >= 0)
                {
                    var tsa = ps.textureSheetAnimation;
                    tsa.enabled = true;
                    tsa.mode = ParticleSystemAnimationMode.Grid;
                    tsa.numTilesX = 4;
                    tsa.numTilesY = 4;
                    tsa.animation = ParticleSystemAnimationType.WholeSheet;
                    tsa.frameOverTime = new ParticleSystem.MinMaxCurve(0f);
                    // startFrame is a fraction of the sheet (frame = startFrame × 16), not a frame number
                    int last = Mathf.Max(d.renderer.tile, d.renderer.tileLast);   // a range: one shape per particle
                    tsa.startFrame = last > d.renderer.tile
                        ? new ParticleSystem.MinMaxCurve((d.renderer.tile + 0.02f) / 16f, (last + 0.98f) / 16f)
                        : new ParticleSystem.MinMaxCurve((d.renderer.tile + 0.5f) / 16f);
                    tsa.cycleCount = 1;
                }
            }
            if (d.trail != null && d.trail.width > 0)
            {
                var tr = ps.trails;
                tr.enabled = true;
                tr.mode = ParticleSystemTrailMode.PerParticle;
                tr.lifetime = d.trail.ratio;                // a share of the particle's lifetime
                tr.minVertexDistance = 0.04f;               // keeps the right-angle corners sharp
                tr.dieWithParticles = true;
                tr.inheritParticleColor = true;
                tr.sizeAffectsWidth = false;
                tr.widthOverTrail = new ParticleSystem.MinMaxCurve(d.trail.width, AnimationCurve.Linear(0f, 1f, 1f, 0f));
                tr.colorOverTrail = new ParticleSystem.MinMaxGradient(Fade(0f, 1f));
                r.trailMaterial = trailMat != null ? trailMat : mat;
            }
            if (d.sub != null && d.sub.count > 0) AddSub(ps, d, mat, mesh);
            return ps;
        }

        static void AddSub(ParticleSystem parent, LLBParticles d, Material mat, Mesh mesh)
        {
            var child = new GameObject("Sub");
            child.transform.SetParent(parent.transform, false);
            var sd = new LLBParticles
            {
                looping = false, duration = 0.5f, burst = d.sub.count, max = d.max * d.sub.count,
                life = new[] { d.sub.life, d.sub.life }, speed = new[] { d.sub.speed * 0.6f, d.sub.speed },
                size = new[] { d.size[0] * 0.6f, d.size[1] * 0.6f }, fade = new[] { 0f, 1f }, colors = d.colors,
                spin = new[] { 0f, 0f }, sizeLife = "flat", gravity = d.gravity,
                shape = new LLBPSShape { type = "Sphere", radius = 0.01f, thickness = 1f, randomDirection = 1f,
                                         position = new float[3], rotation = new float[3] },
                velocity = new LLBPSVelocity(), renderer = d.renderer,
            };
            var ps = Apply(child, sd, mat, mesh);
            var main = ps.main;
            main.playOnAwake = false;
            var subs = parent.subEmitters;
            subs.enabled = true;
            subs.AddSubEmitter(ps, ParticleSystemSubEmitterType.Death, ParticleSystemSubEmitterProperties.InheritColor);
        }
    }
}
