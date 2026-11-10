// LyricLive Builder: manifest.json written by the Blender add-on (design §9.2). JsonUtility friendly:
// no dictionaries, no nested arrays. Positions, rotations and colours are already in Unity space / sRGB.
using System;

namespace LyricLive.Editor
{
    [Serializable] public class LLBManifest
    {
        public string format; public int version; public string generator;
        public LLBSong song; public LLBOptions options;
        public LLBSection[] sections; public LLBMeshRef[] meshes; public LLBMaterialDef[] materials;
        public LLBNode[] nodes; public LLBClip[] clips;
        public LLBFontDef[] fonts; public LLBGuide[] guides;
    }

    [Serializable] public class LLBSong { public string title, artist, audio; public float duration, bpm; }
    [Serializable] public class LLBOptions
    {
        public string materialMode, panorama; public bool mobile, tmp, udonSync; public float particleRatio;
    }
    [Serializable] public class LLBFontDef { public string key, file, chars; }
    [Serializable] public class LLBGuide { public int node, motes; public float tOn, tHit; public float[] target; }
    [Serializable] public class LLBSection { public int index; public string label, kind; public float start, end; }
    [Serializable] public class LLBMeshRef { public string key; public int offset, length; }
    [Serializable] public class LLBParam { public string name; public float[] values; }

    [Serializable] public class LLBMaterialDef
    {
        public string key, shader; public float[] color; public LLBParam[] @params;
    }

    [Serializable] public class LLBNode
    {
        public int id; public string name; public int parent;
        public string category, kind, mesh, material, particles, tmp, tmpFont;
        public float[] p, r, s; public bool active;
    }

    [Serializable] public class LLBCurve
    {
        public int node; public string type, attr; public string[] fields;
        public int interp;                                  // 0 linear, 1 constant
        public float[] times, values;                       // values: times.Length * fields.Length
    }

    [Serializable] public class LLBClip { public int section; public string category; public LLBCurve[] curves; }

    // ---- particle systems (export_unity/particles_unity.py) ----
    [Serializable] public class LLBPSShape { public string type; public float radius, thickness, randomDirection; public float[] position, rotation; }
    [Serializable] public class LLBPSVelocity { public float[] x, y, z, orbitalY; }
    [Serializable] public class LLBPSNoise { public float strength, frequency, scroll; }
    [Serializable] public class LLBPSRenderer { public string mode, mesh, blend; public string[] meshes; public int tile, tileLast; public float stretch; }
    [Serializable] public class LLBPSSub { public int count; public float speed, life; }

    [Serializable] public class LLBParticles
    {
        public bool looping, prewarm;
        public float duration, rate, gravity, drag;
        public int max, burst;
        public float[] life, speed, size, fade, spin, colors;
        public string sizeLife;
        public LLBPSShape shape; public LLBPSVelocity velocity; public LLBPSNoise noise;
        public LLBPSRenderer renderer; public LLBPSSub sub;
    }
}
