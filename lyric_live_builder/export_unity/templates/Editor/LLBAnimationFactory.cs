// LyricLive Builder: one AnimationClip per section × category (design §10.4, §10.5).
// Linear keys get the slopes of their segments; constant keys get infinite tangents (stepped).
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace LyricLive.Editor
{
    public static class LLBAnimationFactory
    {
        static readonly Dictionary<string, Type> Types = new Dictionary<string, Type>
        {
            { "GameObject", typeof(GameObject) }, { "Transform", typeof(Transform) },
            { "MeshRenderer", typeof(MeshRenderer) }, { "ParticleSystem", typeof(ParticleSystem) },
            { "ParticleSystemRenderer", typeof(ParticleSystemRenderer) },
        };

        static LLBAnimationFactory()
        {
            if (LLBTextMeshProFactory.LetterType != null) Types["TextMeshPro"] = LLBTextMeshProFactory.LetterType;
        }

        public static AnimationCurve Curve(float[] t, float[] v, int stride, int comp, bool constant)
        {
            int n = t.Length;
            var keys = new Keyframe[n];
            for (int i = 0; i < n; i++)
            {
                float value = v[i * stride + comp];
                if (constant)
                {
                    keys[i] = new Keyframe(t[i], value, float.PositiveInfinity, float.PositiveInfinity);
                    continue;
                }
                float inT = i > 0 ? (value - v[(i - 1) * stride + comp]) / Mathf.Max(1e-6f, t[i] - t[i - 1]) : 0f;
                float outT = i < n - 1 ? (v[(i + 1) * stride + comp] - value) / Mathf.Max(1e-6f, t[i + 1] - t[i]) : 0f;
                keys[i] = new Keyframe(t[i], value, i > 0 ? inT : outT, i < n - 1 ? outT : inT);
            }
            return new AnimationCurve(keys);
        }

        /// <param name="paths">node id -> path from the category root</param>
        public static AnimationClip Build(LLBClip c, Dictionary<int, string> paths, string name, float length)
        {
            var clip = new AnimationClip { name = name, frameRate = 60 };
            var bindings = new List<EditorCurveBinding>();
            var curves = new List<AnimationCurve>();
            foreach (var cv in c.curves)
            {
                if (!paths.TryGetValue(cv.node, out var path) || !Types.TryGetValue(cv.type, out var type)) continue;
                int stride = cv.fields.Length;
                for (int k = 0; k < stride; k++)
                {
                    var prop = string.IsNullOrEmpty(cv.fields[k]) ? cv.attr : cv.attr + "." + cv.fields[k];
                    bindings.Add(EditorCurveBinding.FloatCurve(path, type, prop));
                    curves.Add(Curve(cv.times, cv.values, stride, k, cv.interp == 1 || cv.type == "GameObject"));
                }
            }
            // an empty clip still spans its section, so the track keeps every section visible
            bindings.Add(EditorCurveBinding.FloatCurve("", typeof(Transform), "m_LocalScale.x"));
            curves.Add(AnimationCurve.Constant(0f, length, 1f));
            AnimationUtility.SetEditorCurves(clip, bindings.ToArray(), curves.ToArray());
            clip.EnsureQuaternionContinuity();
            return clip;
        }
    }
}
