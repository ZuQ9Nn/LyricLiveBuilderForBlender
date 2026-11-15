// LyricLive Builder: attaches LLBSync (UdonSharp) to a start button in the prefab (design §10.7).
// UdonSharp's editor API is called by reflection (its versions differ, and projects without it must
// still compile): program asset -> CompileAllCsPrograms -> UdonSharpUndo.AddComponent -> fields ->
// UdonSharpEditorUtility.CopyProxyToUdon (prototype S0-11).
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;

namespace LyricLive.Editor
{
    public static class LLBUdonSyncFactory
    {
        public const string Folder = "Assets/LyricLive/Runtime/Udon";
        const string Script = Folder + "/LLBSync.cs";
        const string Template = Folder + "/LLBSync.cs.txt";
        const string Program = Folder + "/LLBSync.asset";

        public static Type Find(string fullName) =>
            AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetType(fullName)).FirstOrDefault(t => t != null);

        /// <returns>"attached", "pending" (the script was just added: build again after it compiles) or "unavailable"</returns>
        /// <param name="stageNodes">every node a clip shows or hides, with <paramref name="stageDefaults"/>: put back
        /// when the show stops or starts again</param>
        public static string Attach(GameObject root, PlayableDirector director, Transform[] pivots, LLBGuide[] guides,
                                    GameObject[] stageNodes, bool[] stageDefaults)
        {
            if (Find("UdonSharp.UdonSharpBehaviour") == null)
            {
                Debug.LogWarning("[LLB][WARN] UdonSharp is not in the project: the prefab plays without Udon sync");
                return "unavailable";
            }
            if (!File.Exists(Script) || File.ReadAllText(Script) != File.ReadAllText(Template))
            {
                File.Copy(Template, Script, true);                               // first export, or a new add-on
                AssetDatabase.ImportAsset(Script);
                return "pending";
            }
            // the class from the script asset: UdonSharp also compiles a copy into its own assemblies
            var mono = AssetDatabase.LoadAssetAtPath<MonoScript>(Script);
            var script = mono != null ? mono.GetClass() : null;
            if (script == null) return "pending";
            var fields = new (string name, object value)[]
            {
                ("director", director), ("stage", root.transform), ("guidePivots", pivots),
                ("guideOn", guides.Select(g => g.tOn).ToArray()), ("guideHit", guides.Select(g => g.tHit).ToArray()),
                ("guideTarget", guides.Select(g => new Vector3(g.target[0], g.target[1], g.target[2])).ToArray()),
                ("guideMotes", guides.Select(g => g.motes).ToArray()),
                ("stageNodes", stageNodes), ("stageDefaults", stageDefaults),
                ("stageParticles", root.GetComponentsInChildren<ParticleSystem>(true)),
            };
            if (fields.Any(f => script.GetField(f.name) == null)) return "pending";   // still the previous LLBSync
            var progType = Find("UdonSharp.UdonSharpProgramAsset");
            var prog = AssetDatabase.LoadAssetAtPath(Program, progType);
            if (prog == null)
            {
                prog = ScriptableObject.CreateInstance(progType);
                progType.GetField("sourceCsScript").SetValue(prog, AssetDatabase.LoadAssetAtPath<MonoScript>(Script));
                AssetDatabase.CreateAsset(prog, Program);
                AssetDatabase.SaveAssets();
            }
            progType.GetMethod("CompileAllCsPrograms", BindingFlags.Public | BindingFlags.Static)
                    .Invoke(null, new object[] { true, false });

            var button = GameObject.CreatePrimitive(PrimitiveType.Cube);
            button.name = "LLB_StartButton";
            button.transform.SetParent(root.transform, false);
            button.transform.localPosition = new Vector3(0f, 1.0f, -1.2f);       // behind the audience, at hand height
            button.transform.localScale = Vector3.one * 0.2f;
            var add = Find("UdonSharpEditor.UdonSharpUndo").GetMethod("AddComponent", new[] { typeof(GameObject), typeof(Type) });
            var comp = (Component)add.Invoke(null, new object[] { button, script });
            foreach (var f in fields) script.GetField(f.name).SetValue(comp, f.value);
            var copy = Find("UdonSharpEditor.UdonSharpEditorUtility").GetMethods(BindingFlags.Public | BindingFlags.Static)
                       .Where(m => m.Name == "CopyProxyToUdon").OrderBy(m => m.GetParameters().Length).First();
            var args = copy.GetParameters().Select((p, i) => i == 0 ? comp : (p.HasDefaultValue ? p.DefaultValue : null)).ToArray();
            try
            {
                copy.Invoke(null, args);
            }
            catch (TargetInvocationException e) when (e.InnerException is InvalidOperationException)
            {
                // UdonSharp is still compiling the program ("outdated script version"): build again after the reload
                UnityEngine.Object.DestroyImmediate(button);
                Debug.Log("[LLB] Udon program still compiling: " + e.InnerException.Message);
                return "pending";
            }
            return "attached";
        }
    }
}
