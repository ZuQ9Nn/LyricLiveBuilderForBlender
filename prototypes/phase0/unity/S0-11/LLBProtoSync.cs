// Phase 0 prototype (S0-11): keep a PlayableDirector in sync for everyone, including late joiners.
// Interact (or the start button) -> owner stores the server time of "t = 0"; every client seeks
// the director to (now - startServerTime). Udon cannot change playback speed, so drift is
// corrected by re-seeking only when it exceeds MaxDrift.
using UdonSharp;
using UnityEngine;
using UnityEngine.Playables;
using VRC.SDKBase;

[UdonBehaviourSyncMode(BehaviourSyncMode.Manual)]
public class LLBProtoSync : UdonSharpBehaviour
{
    public PlayableDirector director;
    public float maxDrift = 0.2f;

    [UdonSynced] private double startServerTime;
    [UdonSynced] private bool playing;

    public override void Interact()
    {
        if (!Networking.IsOwner(gameObject)) Networking.SetOwner(Networking.LocalPlayer, gameObject);
        startServerTime = Networking.GetServerTimeInSeconds();
        playing = true;
        RequestSerialization();
        Apply();
    }

    public override void OnDeserialization()
    {
        Apply();
    }

    private void Apply()
    {
        if (director == null) return;
        if (!playing)
        {
            director.Stop();
            return;
        }
        double t = Networking.GetServerTimeInSeconds() - startServerTime;
        if (t < 0 || t > director.duration) return;
        director.time = t;
        director.Play();
    }

    private void Update()
    {
        if (!playing || director == null) return;
        double t = Networking.GetServerTimeInSeconds() - startServerTime;
        if (t > director.duration) return;
        if (System.Math.Abs(director.time - t) > maxDrift)
        {
            director.time = t;
            director.Evaluate();
        }
    }
}
