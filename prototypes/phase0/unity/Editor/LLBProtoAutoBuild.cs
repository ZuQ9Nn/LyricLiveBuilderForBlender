// Phase 0 prototype (S0-04): build automatically when Blender drops a "_pending.llb" marker
// into the project while the editor is open. Two triggers, so both cases work:
//   - AssetPostprocessor: the marker is imported after the scripts already exist
//   - InitializeOnLoad:   scripts and marker arrive together (first export / script update)
using System.IO;
using UnityEditor;
using UnityEngine;

namespace LyricLive.Proto
{
    [InitializeOnLoad]
    public class LLBProtoAutoBuild : AssetPostprocessor
    {
        const string Marker = "_pending.llb";

        static LLBProtoAutoBuild()
        {
            EditorApplication.delayCall += ScanAll;
        }

        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            foreach (var p in imported)
                if (p.EndsWith(Marker))
                {
                    var dir = Path.GetDirectoryName(p).Replace('\\', '/');
                    EditorApplication.delayCall += () => BuildFolder(dir);
                }
        }

        static void ScanAll()
        {
            if (!Directory.Exists("Assets/LyricLive")) return;
            foreach (var f in Directory.GetFiles("Assets/LyricLive", Marker, SearchOption.AllDirectories))
                BuildFolder(Path.GetDirectoryName(f).Replace('\\', '/'));
        }

        static void BuildFolder(string dir)
        {
            var marker = dir + "/" + Marker;
            if (!File.Exists(marker)) return;             // already built by the other trigger
            AssetDatabase.DeleteAsset(marker);
            Debug.Log("[LLB] auto build " + dir);
            LLBProtoS003.BuildAt(dir, false);
            Debug.Log("[LLB] done");
        }
    }
}
