// LyricLive Builder: materials (design §10.3). The bundled shaders (Runtime/Shaders) are used in both
// modes; if one is missing (not imported yet, or stripped) a built-in shader stands in with a warning.
using System.Collections.Generic;
using UnityEngine;

namespace LyricLive.Editor
{
    public static class LLBMaterialFactory
    {
        static readonly Dictionary<string, string[]> Shaders = new Dictionary<string, string[]>
        {
            { "text", new[] { "LyricLive/Text", "Unlit/Transparent", "Unlit/Color" } },
            { "text_vc", new[] { "LyricLive/TextVC", "Particles/Standard Unlit", "Unlit/Color" } },
            { "far", new[] { "LyricLive/Far", "Unlit/Transparent", "Unlit/Color" } },
            { "glow", new[] { "LyricLive/Glow", "Particles/Standard Unlit", "Unlit/Color" } },
            { "dome", new[] { "LyricLive/Dome", "Unlit/Color" } },
            { "particle", new[] { "LyricLive/Particle", "Particles/Standard Unlit", "Unlit/Color" } },
        };

        public static Shader Find(string kind)
        {
            var names = Shaders[kind];
            foreach (var n in names)
            {
                var s = Shader.Find(n);
                if (s != null)
                {
                    if (n != names[0]) Debug.LogWarning($"[LLB][WARN] shader {names[0]} not found, using {n}");
                    return s;
                }
            }
            return Shader.Find("Hidden/InternalErrorShader");
        }

        public static Material Create(LLBMaterialDef d, Texture panorama)
        {
            var m = new Material(Find(d.shader)) { name = d.key };
            if (d.color != null && d.color.Length == 4)
                m.SetColor("_Color", new Color(d.color[0], d.color[1], d.color[2], d.color[3]));   // sRGB values
            if (d.@params != null)
                foreach (var p in d.@params)
                {
                    if (p.values.Length == 1) m.SetFloat(p.name, p.values[0]);
                    else if (p.name == "_CueDir") m.SetVector(p.name, new Vector4(p.values[0], p.values[1], p.values[2], 0));
                    else m.SetColor(p.name, new Color(p.values[0], p.values[1], p.values[2], 1));
                }
            if (d.shader == "dome" && panorama != null) m.SetTexture("_PanoTex", panorama);
            return m;
        }

        /// <summary>Particle material: additive or alpha blended, with the atlas or plain (3D shapes).</summary>
        public static Material Particle(string blend, Texture atlas)
        {
            var m = new Material(Find("particle")) { name = $"particle_{blend}" + (atlas ? "" : "_mesh") };
            bool add = blend == "add";
            m.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)(add ? UnityEngine.Rendering.BlendMode.One : UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha));
            if (atlas) m.SetTexture("_MainTex", atlas);
            m.SetColor("_Color", Color.white);
            return m;
        }
    }
}
