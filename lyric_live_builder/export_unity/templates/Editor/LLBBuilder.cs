// LyricLive Builder: builds Generated/<song>.prefab and its Timeline from what the Blender add-on
// exported (design §10.2). It works on temporary objects in a preview scene and never touches the
// open scene: instances already placed there update through the prefab (prototype S0-03).
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.SceneManagement;

namespace LyricLive.Editor
{
    public static class LLBBuilder
    {
        public const string Marker = "_llb_build.pending";
        public const string UdonMarker = "_llb_udon.pending";       // build again once LLBSync.cs has compiled
        const int ManifestVersion = 1;

        [MenuItem("Tools/LyricLive/Rebuild All Songs")]
        public static void RebuildAll()
        {
            if (!Directory.Exists("Assets/LyricLive/Songs")) return;
            foreach (var dir in Directory.GetDirectories("Assets/LyricLive/Songs"))
                if (File.Exists(Path.Combine(dir, "manifest.json"))) Build(dir.Replace('\\', '/'));
        }

        // Unity.exe -batchmode -quit -projectPath P -executeMethod LyricLive.Editor.LLBBuilder.BuildFromCommandLine -llbSong <folder>
        public static void BuildFromCommandLine()
        {
            var args = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(args, "-llbSong");
            if (i < 0 || i + 1 >= args.Length) { Debug.LogError("[LLB][ERROR] -llbSong is missing"); EditorApplication.Exit(2); return; }
            try { Build(args[i + 1].Replace('\\', '/')); }
            catch (Exception e) { Debug.LogError("[LLB][ERROR] " + e); EditorApplication.Exit(1); }
        }

        static string Join(string a, string b) => a.TrimEnd('/') + "/" + b;

        static void Folder(string path)
        {
            var parent = Path.GetDirectoryName(path).Replace('\\', '/');
            if (!AssetDatabase.IsValidFolder(parent)) Folder(parent);
            if (!AssetDatabase.IsValidFolder(path)) AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }

        static Texture2D ImportTexture(string path, bool repeatX)
        {
            if (!File.Exists(path)) return null;
            AssetDatabase.ImportAsset(path);
            if (AssetImporter.GetAtPath(path) is TextureImporter ti)
            {
                ti.alphaIsTransparency = true;
                ti.wrapModeU = repeatX ? TextureWrapMode.Repeat : TextureWrapMode.Clamp;
                ti.wrapModeV = TextureWrapMode.Clamp;
                ti.mipmapEnabled = true;
                ti.SaveAndReimport();
            }
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        public static string Build(string song)
        {
            Debug.Log("[LLB] build " + song);
            var m = JsonUtility.FromJson<LLBManifest>(File.ReadAllText(Join(song, "manifest.json")));
            if (m.format != "llb-manifest" || m.version > ManifestVersion)
                throw new Exception($"[LLB][ERROR] manifest {m.format} v{m.version} is newer than this builder; update the add-on scripts");
            var name = Path.GetFileName(song);
            var gen = Join(song, "Generated");
            if (AssetDatabase.IsValidFolder(gen)) AssetDatabase.DeleteAsset(gen);
            Folder(Join(gen, "Clips"));
            Folder(Join(gen, "Materials"));

            // meshes: one asset holding them all
            Debug.Log("[LLB] meshes " + m.meshes.Length);
            var bin = File.ReadAllBytes(Join(song, "meshes.bin"));
            var meshes = new Dictionary<string, Mesh>();
            var meshPath = Join(gen, "Meshes.asset");
            foreach (var r in m.meshes)
            {
                var mesh = LLBMeshReader.Read(bin, r.offset, r.key.Replace(':', '_').Replace('|', '_'));
                if (meshes.Count == 0) AssetDatabase.CreateAsset(mesh, meshPath);
                else AssetDatabase.AddObjectToAsset(mesh, meshPath);
                meshes[r.key] = mesh;
            }

            // textures, audio, materials
            var atlas = ImportTexture(Join(song, "textures/particles_atlas.png"), false);
            var pano = string.IsNullOrEmpty(m.options.panorama) ? null : ImportTexture(Join(song, m.options.panorama), true);
            AudioClip audio = null;
            if (!string.IsNullOrEmpty(m.song.audio))
            {
                var audioPath = Join(song, m.song.audio);
                AssetDatabase.ImportAsset(audioPath);
                if (AssetImporter.GetAtPath(audioPath) is AudioImporter ai)
                {
                    // a whole song decompressed on load is tens of MB on Quest: keep it compressed in memory
                    var ss = ai.defaultSampleSettings;
                    ss.loadType = AudioClipLoadType.CompressedInMemory;
                    ss.compressionFormat = AudioCompressionFormat.Vorbis;
                    ss.quality = 0.7f;
                    ai.defaultSampleSettings = ss;
                    ai.loadInBackground = false;
                    ai.SaveAndReimport();
                }
                audio = AssetDatabase.LoadAssetAtPath<AudioClip>(audioPath);
            }
            var mats = new Dictionary<string, Material>();
            foreach (var d in m.materials)
            {
                var mat = LLBMaterialFactory.Create(d, pano);
                AssetDatabase.CreateAsset(mat, Join(gen, $"Materials/{d.key}.mat"));
                mats[d.key] = mat;
            }
            var particleMats = new Dictionary<string, Material>();
            Material ParticleMat(string blend, bool textured)
            {
                var key = blend + (textured ? "" : "_mesh");
                if (!particleMats.TryGetValue(key, out var pm))
                {
                    pm = LLBMaterialFactory.Particle(blend, textured ? atlas : null);
                    AssetDatabase.CreateAsset(pm, Join(gen, $"Materials/particle_{key}.mat"));
                    particleMats[key] = pm;
                }
                return pm;
            }

            var fonts = m.options.tmp ? LLBTextMeshProFactory.CreateFonts(m, song, gen, m.options.mobile)
                                      : new Dictionary<string, (UnityEngine.Object asset, float size)>();

            // hierarchy, built in a preview scene
            var scene = EditorSceneManager.NewPreviewScene();
            try
            {
                var root = new GameObject(name);
                SceneManager.MoveGameObjectToScene(root, scene);
                var director = root.AddComponent<PlayableDirector>();
                var source = root.AddComponent<AudioSource>();
                source.playOnAwake = false;
                source.spatialBlend = 0f;
                var cats = new Dictionary<string, Transform>();
                var animators = new Dictionary<string, Animator>();
                for (int c = 0; c < LLBTimelineFactory.Categories.Length; c++)
                {
                    var go = new GameObject(LLBTimelineFactory.TrackNames[c]);
                    go.transform.SetParent(root.transform, false);
                    animators[LLBTimelineFactory.Categories[c]] = go.AddComponent<Animator>();
                    cats[LLBTimelineFactory.Categories[c]] = go.transform;
                }
                var objs = new GameObject[m.nodes.Length];
                var paths = new Dictionary<int, string>();
                foreach (var n in m.nodes)
                {
                    var go = new GameObject(n.name);
                    var parent = n.parent >= 0 ? objs[n.parent].transform : cats[n.category];
                    go.transform.SetParent(parent, false);
                    go.transform.localPosition = new Vector3(n.p[0], n.p[1], n.p[2]);
                    go.transform.localRotation = new Quaternion(n.r[0], n.r[1], n.r[2], n.r[3]);
                    go.transform.localScale = new Vector3(n.s[0], n.s[1], n.s[2]);
                    paths[n.id] = n.parent >= 0 ? paths[n.parent] + "/" + n.name : n.name;
                    if (!string.IsNullOrEmpty(n.mesh) && meshes.TryGetValue(n.mesh, out var mesh))
                    {
                        go.AddComponent<MeshFilter>().sharedMesh = mesh;
                        var mr = go.AddComponent<MeshRenderer>();
                        mr.sharedMaterial = mats.TryGetValue(n.material, out var mat) ? mat : null;
                        mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                        mr.receiveShadows = false;
                    }
                    if (!string.IsNullOrEmpty(n.tmp) && fonts.TryGetValue(n.tmpFont, out var fa))
                        LLBTextMeshProFactory.AddLetter(go, n.tmp, fa.asset, fa.size);
                    if (!string.IsNullOrEmpty(n.particles))
                    {
                        var d = JsonUtility.FromJson<LLBParticles>(n.particles);
                        bool isMesh = d.renderer.mode == "Mesh";
                        meshes.TryGetValue(d.renderer.mesh ?? "", out var pmesh);
                        LLBParticleFactory.Apply(go, d, ParticleMat(d.renderer.blend, !isMesh), pmesh);
                    }
                    go.SetActive(n.active);
                    objs[n.id] = go;
                }

                // clips and timeline
                Debug.Log("[LLB] clips " + m.clips.Length);
                var clips = new Dictionary<(int, string), AnimationClip>();
                foreach (var c in m.clips)
                {
                    var s = Array.Find(m.sections, x => x.index == c.section);
                    int ci = Array.IndexOf(LLBTimelineFactory.Categories, c.category);
                    var clipName = $"{c.section + 1:00}_{SafeName(s.label)}_{LLBTimelineFactory.TrackNames[ci]}";
                    var clip = LLBAnimationFactory.Build(c, PathsUnder(paths, m, c.category), clipName, s.end - s.start);
                    AssetDatabase.CreateAsset(clip, Join(gen, $"Clips/{clipName}.anim"));
                    clips[(c.section, c.category)] = clip;
                }
                LLBTimelineFactory.Build(Join(gen, name + ".playable"), m, audio, clips, director, source, animators);
                director.playableAsset = AssetDatabase.LoadAssetAtPath<PlayableAsset>(Join(gen, name + ".playable"));
                var udon = "off";
                if (m.options.udonSync)
                {
                    var guides = m.guides ?? new LLBGuide[0];
                    var pivots = Array.ConvertAll(guides, g => objs[g.node].transform);
                    udon = LLBUdonSyncFactory.Attach(root, director, pivots, guides);
                    if (udon == "pending")
                    {
                        File.WriteAllText(Join(song, UdonMarker), name);
                        Debug.Log("[LLB] udon-pending: LLBSync.cs was added; the prefab is built again after it compiles");
                    }
                }
                director.playOnAwake = udon != "attached";             // with Udon sync, the start button plays it
                director.extrapolationMode = DirectorWrapMode.Hold;
                director.timeUpdateMode = DirectorUpdateMode.DSPClock;      // follows the audio clock
                var prefabPath = Join(gen, name + ".prefab");
                PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
                AssetDatabase.SaveAssets();
                var marker = Join(song, Marker);
                if (File.Exists(marker)) AssetDatabase.DeleteAsset(marker);
                if (udon != "pending" && File.Exists(Join(song, UdonMarker))) AssetDatabase.DeleteAsset(Join(song, UdonMarker));
                Debug.Log($"[LLB] done {prefabPath} nodes={m.nodes.Length} clips={clips.Count} udon={udon} tmpFonts={fonts.Count}");
                return prefabPath;
            }
            finally
            {
                // one tick later in the editor: UdonSharp's delayCall still touches the component made here
                if (Application.isBatchMode) EditorSceneManager.ClosePreviewScene(scene);
                else EditorApplication.delayCall += () => EditorSceneManager.ClosePreviewScene(scene);
            }
        }

        static string SafeName(string s)
        {
            if (string.IsNullOrEmpty(s)) return "Section";
            foreach (var ch in Path.GetInvalidFileNameChars()) s = s.Replace(ch, '_');
            return s.Replace(' ', '_');
        }

        /// <summary>Paths are relative to the category root that the track's Animator sits on.</summary>
        static Dictionary<int, string> PathsUnder(Dictionary<int, string> all, LLBManifest m, string category)
        {
            var d = new Dictionary<int, string>();
            foreach (var n in m.nodes) if (n.category == category) d[n.id] = all[n.id];
            return d;
        }
    }
}
