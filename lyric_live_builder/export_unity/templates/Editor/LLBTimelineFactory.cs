// LyricLive Builder: the Timeline (design §10.6): Audio + one Animation track per category,
// one clip per section, all bound to the prefab's own objects.
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace LyricLive.Editor
{
    public static class LLBTimelineFactory
    {
        public static readonly string[] Categories = { "text", "particles", "background", "gimmicks" };
        public static readonly string[] TrackNames = { "Text", "Particles", "Background", "Gimmicks" };

        public static TimelineAsset Build(string path, LLBManifest m, AudioClip audio, Dictionary<(int, string), AnimationClip> clips,
                                          PlayableDirector director, AudioSource source, Dictionary<string, Animator> animators)
        {
            var tl = ScriptableObject.CreateInstance<TimelineAsset>();
            AssetDatabase.CreateAsset(tl, path);
            if (audio != null)
            {
                var at = tl.CreateTrack<AudioTrack>(null, "Audio");
                var ac = at.CreateClip(audio);
                ac.start = 0;
                ac.displayName = audio.name;
                director.SetGenericBinding(at, source);
            }
            for (int c = 0; c < Categories.Length; c++)
            {
                var track = tl.CreateTrack<AnimationTrack>(null, TrackNames[c]);
                foreach (var s in m.sections)
                {
                    if (!clips.TryGetValue((s.index, Categories[c]), out var clip)) continue;
                    var tc = track.CreateClip(clip);
                    tc.start = s.start;
                    tc.duration = Mathf.Max(0.01f, s.end - s.start);
                    tc.displayName = clip.name;
                }
                director.SetGenericBinding(track, animators[Categories[c]]);
            }
            EditorUtility.SetDirty(tl);
            return tl;
        }
    }
}
