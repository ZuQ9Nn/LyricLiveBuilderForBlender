// LyricLive Builder: TextMesh Pro letters (design §10.8, prototype S0-06). One static atlas per font with
// only the lyric's characters; the font file is copied in by the add-on and deleted again here, and
// every reference to it is cleared, so the world build never contains the font itself. The font assets
// live in <song>/FontAssets (not Generated/, which every build wipes): a rebuild without the font files,
// such as the one after Udon sync is added, reuses them.
// Compiled only when the TextMesh Pro package is in the project (LLB_TMP, LyricLive.Editor.asmdef).
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
#if LLB_TMP
using TMPro;
#endif

namespace LyricLive.Editor
{
    public static class LLBTextMeshProFactory
    {
#if LLB_TMP
        public const bool Available = true;
        public static readonly System.Type LetterType = typeof(TextMeshPro);

        static void EnsureResources()
        {
            if (Shader.Find("TextMeshPro/Distance Field") != null) return;
            Debug.Log("[LLB] importing TMP Essential Resources");
            TMPro.TMP_PackageResourceImporter.ImportResources(true, false, false);
            AssetDatabase.Refresh();
        }

        /// <returns>font key -> (asset, font size that makes 1 em one unit)</returns>
        public static Dictionary<string, (Object asset, float size)> CreateFonts(LLBManifest m, string song, string gen, bool mobile)
        {
            var result = new Dictionary<string, (Object, float)>();
            if (m.fonts == null || m.fonts.Length == 0) return result;
            EnsureResources();
            Directory(song + "/FontAssets");          // not "Fonts": Windows folder names ignore case (the copies are in "fonts")
            foreach (var f in m.fonts)
            {
                var src = song + "/" + f.file;
                var path = $"{song}/FontAssets/{f.key} SDF.asset";
                if (!System.IO.File.Exists(src))
                {
                    var kept = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(path);
                    if (kept != null) { UseOurShader(kept.material); result[f.key] = (kept, EmSize(kept, f.chars)); continue; }
                    Debug.LogError("[LLB][ERROR] no font file and no font asset for " + f.key + ": export again from Blender");
                    continue;
                }
                AssetDatabase.ImportAsset(src);
                var font = AssetDatabase.LoadAssetAtPath<Font>(src);
                if (font == null) { Debug.LogError("[LLB][ERROR] font not imported: " + src); continue; }
                AssetDatabase.DeleteAsset(path);
                var fa = TMP_FontAsset.CreateFontAsset(font, 72, 7, UnityEngine.TextCore.LowLevel.GlyphRenderMode.SDFAA,
                                                       2048, 2048, AtlasPopulationMode.Dynamic, true);
                fa.name = f.key + " SDF";
                if (!fa.TryAddCharacters(f.chars, out var missing) && !string.IsNullOrEmpty(missing))
                    Debug.LogWarning("[LLB][WARN] characters missing in " + f.key + ": " + missing);
                fa.atlasPopulationMode = AtlasPopulationMode.Static;
                AssetDatabase.CreateAsset(fa, path);
                for (int i = 0; i < fa.atlasTextures.Length; i++)
                {
                    fa.atlasTextures[i].name = $"{f.key} Atlas {i}";
                    AssetDatabase.AddObjectToAsset(fa.atlasTextures[i], fa);
                }
                fa.material.name = f.key + " Material";
                UseOurShader(fa.material);
                AssetDatabase.AddObjectToAsset(fa.material, fa);
                // forget the font file: all three references (S0-06), then delete the copy
                var so = new SerializedObject(fa);
                so.FindProperty("m_SourceFontFile").objectReferenceValue = null;
                so.FindProperty("m_SourceFontFileGUID").stringValue = "";
                var editorRef = so.FindProperty("m_SourceFontFile_EditorRef");
                if (editorRef != null) editorRef.objectReferenceValue = null;
                so.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(fa);
                AssetDatabase.SaveAssets();
                AssetDatabase.DeleteAsset(src);
                result[f.key] = (fa, EmSize(fa, f.chars));
            }
            var dir = song + "/fonts";
            if (AssetDatabase.IsValidFolder(dir) && System.IO.Directory.GetFiles(dir, "*", System.IO.SearchOption.AllDirectories).Length == 0)
                AssetDatabase.DeleteAsset(dir);
            return result;
        }

        /// <summary>LyricLive/TextSDF: the same look, plus the glyph mask (design §5.6). It keeps the atlas in _MainTex.</summary>
        static void UseOurShader(Material mat)
        {
            var sh = Shader.Find("LyricLive/TextSDF");
            if (sh == null) { Debug.LogError("[LLB][ERROR] LyricLive/TextSDF is missing: the letters keep TextMesh Pro's shader"); return; }
            var atlas = mat.GetTexture("_MainTex");
            mat.shader = sh;
            mat.SetTexture("_MainTex", atlas);
            EditorUtility.SetDirty(mat);
        }

        static void Directory(string path)
        {
            if (!AssetDatabase.IsValidFolder(path))
                AssetDatabase.CreateFolder(System.IO.Path.GetDirectoryName(path).Replace('\\', '/'), System.IO.Path.GetFileName(path));
        }

        /// <summary>Font size at which one em is one unit: measured, so it does not depend on TMP's scaling rules.</summary>
        static float EmSize(TMP_FontAsset fa, string chars)
        {
            var go = new GameObject("llb_measure", typeof(TextMeshPro));
            try
            {
                var t = go.GetComponent<TextMeshPro>();
                t.font = fa;
                t.fontSize = 10;
                foreach (var ch in chars)
                {
                    if (!fa.characterLookupTable.TryGetValue(ch, out var c)) continue;
                    float advEm = c.glyph.metrics.horizontalAdvance / fa.faceInfo.pointSize * fa.faceInfo.scale;
                    float w = t.GetPreferredValues(ch.ToString()).x;
                    if (advEm > 0.2f && w > 0) return 10f * advEm / w;
                }
                return 10f;
            }
            finally { Object.DestroyImmediate(go); }
        }

        public static void AddLetter(GameObject go, string ch, Object asset, float size)
        {
            var t = go.AddComponent<TextMeshPro>();
            t.font = (TMP_FontAsset)asset;
            t.fontSize = size;
            t.text = ch;
            t.alignment = TextAlignmentOptions.Center;
            t.enableWordWrapping = false;
            t.overflowMode = TextOverflowModes.Overflow;
            t.rectTransform.sizeDelta = new Vector2(2f, 2f);
            t.color = Color.white;
            var r = go.GetComponent<MeshRenderer>();
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.receiveShadows = false;
        }
#else
        public const bool Available = false;
        public static readonly System.Type LetterType = null;
        public static Dictionary<string, (Object asset, float size)> CreateFonts(LLBManifest m, string song, string gen, bool mobile)
        {
            if (m.fonts != null && m.fonts.Length > 0)
                Debug.LogError("[LLB][ERROR] TextMesh Pro was asked for, but the TextMesh Pro package is not in the project");
            return new Dictionary<string, (Object, float)>();
        }
        public static void AddLetter(GameObject go, string ch, Object asset, float size) { }
#endif
    }
}
