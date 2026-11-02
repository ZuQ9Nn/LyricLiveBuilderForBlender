// Phase 0 prototype (S0-03): LLBM mesh reader + clip builder + comparison screenshots.
using System;
using System.IO;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace LyricLive.Proto
{
    public static class LLBProtoS003
    {
        const string Dir = "Assets/LyricLive/Tests/S0-03";

        [Serializable] class MeshRef { public string key; public int offset; public int length; }
        [Serializable] class Node { public string name, mesh, parent; public float[] color, p, r, s; }
        [Serializable] class Clip { public string node; public float[] times, pos, rot; }
        [Serializable] class Cam { public float[] p; public float fov; }
        [Serializable] class Doc { public MeshRef[] meshes; public Node[] nodes; public Clip clip; public Cam camera; public float[] sampleTimes; }

        public static Mesh ReadLLBM(byte[] data, int offset, string name)
        {
            using var br = new BinaryReader(new MemoryStream(data, offset, data.Length - offset));
            if (new string(br.ReadChars(4)) != "LLBM") throw new Exception("bad magic");
            br.ReadUInt16();                       // version
            int flags = br.ReadUInt16();
            int nVerts = (int)br.ReadUInt32(), nIdx = (int)br.ReadUInt32();
            br.ReadUInt16(); br.ReadUInt16();      // shapes, reserved
            var v = new Vector3[nVerts];
            for (int i = 0; i < nVerts; i++) v[i] = new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle());
            Vector3[] n = null;
            if ((flags & 1) != 0) { n = new Vector3[nVerts]; for (int i = 0; i < nVerts; i++) n[i] = new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle()); }
            var idx = new int[nIdx];
            bool i32 = (flags & 8) != 0;
            for (int i = 0; i < nIdx; i++) idx[i] = i32 ? (int)br.ReadUInt32() : br.ReadUInt16();
            var m = new Mesh { name = name, indexFormat = i32 ? UnityEngine.Rendering.IndexFormat.UInt32 : UnityEngine.Rendering.IndexFormat.UInt16 };
            m.vertices = v;
            if (n != null) m.normals = n;
            m.triangles = idx;
            m.RecalculateBounds();
            return m;
        }

        static Vector3 V3(float[] a) => new Vector3(a[0], a[1], a[2]);
        static Quaternion Q(float[] a) => new Quaternion(a[0], a[1], a[2], a[3]);

        [MenuItem("Tools/LyricLive/Prototype/S0-03 Build")]
        public static string Build() => BuildAt(Dir, true);

        // Batch mode entry: Unity.exe -batchmode -quit -projectPath P -executeMethod LyricLive.Proto.LLBProtoS003.BuildFromCommandLine -llbSong <folder>
        public static void BuildFromCommandLine()
        {
            var args = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(args, "-llbSong");
            var dir = i >= 0 && i + 1 < args.Length ? args[i + 1] : Dir;
            Debug.Log("[LLB] build " + dir);
            BuildAt(dir, false);
            Debug.Log("[LLB] done");
        }

        public static string BuildAt(string Dir, bool shoot)
        {
            var doc = JsonUtility.FromJson<Doc>(File.ReadAllText(Dir + "/s003.json"));
            var bin = File.ReadAllBytes(Dir + "/meshes.bin");
            // Only the interactive build replaces the scene instance; batch/auto builds must not touch the open scene.
            var old = shoot ? GameObject.Find("LLB_S0-03") : null;
            if (old) UnityEngine.Object.DestroyImmediate(old);
            var root = new GameObject("LLB_S0-03");
            var map = new System.Collections.Generic.Dictionary<string, Transform>();
            foreach (var nd in doc.nodes)
            {
                var mr = Array.Find(doc.meshes, x => x.key == nd.mesh);
                var mesh = ReadLLBM(bin, mr.offset, nd.mesh);
                var meshPath = $"{Dir}/{nd.mesh}.asset";
                AssetDatabase.DeleteAsset(meshPath);
                AssetDatabase.CreateAsset(mesh, meshPath);
                var mat = new Material(Shader.Find("Unlit/Color")) { color = new Color(nd.color[0], nd.color[1], nd.color[2], 1) };
                var matPath = $"{Dir}/{nd.name}.mat";
                AssetDatabase.DeleteAsset(matPath);
                AssetDatabase.CreateAsset(mat, matPath);
                var go = new GameObject(nd.name);
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                go.AddComponent<MeshRenderer>().sharedMaterial = mat;
                go.transform.SetParent(string.IsNullOrEmpty(nd.parent) ? root.transform : map[nd.parent], false);
                go.transform.localPosition = V3(nd.p);
                go.transform.localRotation = Q(nd.r);
                go.transform.localScale = V3(nd.s);
                map[nd.name] = go.transform;
            }
            var clip = BuildClip(doc.clip);
            clip.name = "S0-03";
            var clipPath = Dir + "/S0-03.anim";
            AssetDatabase.DeleteAsset(clipPath);
            AssetDatabase.CreateAsset(clip, clipPath);
            var ctrl = AnimatorController.CreateAnimatorControllerAtPathWithClip(Dir + "/S0-03.controller", clip);
            root.AddComponent<Animator>().runtimeAnimatorController = ctrl;
            PrefabUtility.SaveAsPrefabAssetAndConnect(root, Dir + "/S0-03.prefab", InteractionMode.AutomatedAction);
            AssetDatabase.SaveAssets();
            if (!shoot) { UnityEngine.Object.DestroyImmediate(root); return "ok"; }
            return Shoot(root, doc, Dir);
        }

        static AnimationClip BuildClip(Clip c)
        {
            var clip = new AnimationClip { frameRate = 30 };
            string path = c.node;
            string[] pn = { "m_LocalPosition.x", "m_LocalPosition.y", "m_LocalPosition.z" };
            string[] rn = { "m_LocalRotation.x", "m_LocalRotation.y", "m_LocalRotation.z", "m_LocalRotation.w" };
            for (int k = 0; k < 3; k++) clip.SetCurve(path, typeof(Transform), pn[k], Curve(c.times, c.pos, 3, k));
            for (int k = 0; k < 4; k++) clip.SetCurve(path, typeof(Transform), rn[k], Curve(c.times, c.rot, 4, k));
            clip.EnsureQuaternionContinuity();
            return clip;
        }

        static AnimationCurve Curve(float[] t, float[] v, int stride, int comp)
        {
            var keys = new Keyframe[t.Length];
            for (int i = 0; i < t.Length; i++) keys[i] = new Keyframe(t[i], v[i * stride + comp]);
            var curve = new AnimationCurve(keys);
            for (int i = 0; i < keys.Length; i++)
            {
                AnimationUtility.SetKeyLeftTangentMode(curve, i, AnimationUtility.TangentMode.Linear);
                AnimationUtility.SetKeyRightTangentMode(curve, i, AnimationUtility.TangentMode.Linear);
            }
            return curve;
        }

        // Renders the viewer camera at the sample times into Temp/LLB/s003_unity_t*.png
        static string Shoot(GameObject root, Doc doc, string Dir)
        {
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(Dir + "/S0-03.anim");
            var camGo = new GameObject("LLB_TmpCam");
            try
            {
                var cam = camGo.AddComponent<Camera>();
                cam.transform.position = V3(doc.camera.p);
                cam.transform.rotation = Quaternion.identity;          // looks along +Z
                cam.fieldOfView = doc.camera.fov;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.22f, 0.22f, 0.22f);
                var rt = new RenderTexture(640, 480, 24);
                cam.targetTexture = rt;
                Directory.CreateDirectory("Temp/LLB");
                foreach (var t in doc.sampleTimes)
                {
                    clip.SampleAnimation(root, t);
                    cam.Render();
                    RenderTexture.active = rt;
                    var tex = new Texture2D(640, 480, TextureFormat.RGB24, false);
                    tex.ReadPixels(new Rect(0, 0, 640, 480), 0, 0);
                    File.WriteAllBytes($"Temp/LLB/s003_unity_t{t:0}.png", tex.EncodeToPNG());
                    UnityEngine.Object.DestroyImmediate(tex);
                }
                RenderTexture.active = null;
                cam.targetTexture = null;
                UnityEngine.Object.DestroyImmediate(rt);
                clip.SampleAnimation(root, 0);
            }
            finally { UnityEngine.Object.DestroyImmediate(camGo); }
            return "ok: " + Path.GetFullPath("Temp/LLB");
        }
    }
}
