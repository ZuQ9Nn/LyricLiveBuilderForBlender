// LyricLive Builder: builds automatically when the add-on drops its marker while the editor is open
// (design §10.1, prototype S0-04). Two triggers so both cases work:
//   - AssetPostprocessor: the marker is imported after the scripts already exist
//   - InitializeOnLoad:   scripts and marker arrive together (first export / script update)
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace LyricLive.Editor
{
    [InitializeOnLoad]
    public class LLBAutoBuild : AssetPostprocessor
    {
        static LLBAutoBuild()
        {
            EditorApplication.delayCall += ScanAll;
        }

        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            foreach (var p in imported)
                if (p.EndsWith(LLBBuilder.Marker))
                {
                    var dir = Path.GetDirectoryName(p).Replace('\\', '/');
                    EditorApplication.delayCall += () => BuildFolder(dir);
                }
        }

        static void ScanAll()
        {
            if (Application.isBatchMode || !Directory.Exists("Assets/LyricLive/Songs")) return;
            foreach (var f in Directory.GetFiles("Assets/LyricLive/Songs", LLBBuilder.Marker, SearchOption.AllDirectories))
                BuildFolder(Path.GetDirectoryName(f).Replace('\\', '/'));
        }

        static void BuildFolder(string dir)
        {
            if (Application.isBatchMode || EditorApplication.isPlayingOrWillChangePlaymode) return;
            if (!File.Exists(Path.Combine(dir, LLBBuilder.Marker))) return;      // the other trigger got it
            try { LLBBuilder.Build(dir); }
            catch (Exception e) { Debug.LogError("[LLB][ERROR] " + e); }
        }
    }
}
