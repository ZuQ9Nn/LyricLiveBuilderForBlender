// Phase 0 prototype (S0-07): background dome — two gradient sets (A/B) mixed by a transition.
// _TransType: 0 crossfade, 1 wipe from top, 2 wipe from bottom, 3 ring from the front, 4 noise dissolve.
// Opaque, drawn from the inside (Cull Front), so Quest pays for one full-screen pass only.
// ZWrite On is required: the built-in skybox is drawn after opaques wherever depth is still at
// the far plane, so a dome that does not write depth gets painted over by the skybox.
Shader "LyricLive/Proto/Dome"
{
    Properties
    {
        _TopA ("Top A", Color) = (0.55,0.75,1,1)
        _HorizonA ("Horizon A", Color) = (1,0.85,0.7,1)
        _BottomA ("Bottom A", Color) = (0.3,0.3,0.35,1)
        _TopB ("Top B", Color) = (0.02,0.02,0.1,1)
        _HorizonB ("Horizon B", Color) = (0.15,0.1,0.35,1)
        _BottomB ("Bottom B", Color) = (0,0,0,1)
        _TransType ("Transition Type", Float) = 0
        _Progress ("Progress", Range(0, 1)) = 0
        _Softness ("Softness", Range(0.001, 0.5)) = 0.08
        _Flash ("Flash", Range(0, 1)) = 0
    }
    SubShader
    {
        Tags { "Queue"="Background+10" "RenderType"="Opaque" }
        Cull Front
        ZWrite On
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            fixed4 _TopA, _HorizonA, _BottomA, _TopB, _HorizonB, _BottomB;
            half _TransType, _Progress, _Softness, _Flash;

            struct appdata { float4 vertex : POSITION; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct v2f { float4 pos : SV_POSITION; float3 dir : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };

            v2f vert (appdata v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.dir = normalize(v.vertex.xyz);
                return o;
            }

            fixed3 grad(float y, fixed3 top, fixed3 hor, fixed3 bot)
            {
                return y >= 0 ? lerp(hor, top, saturate(y * 1.5)) : lerp(hor, bot, saturate(-y * 3));
            }

            float hash2(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453); }

            fixed4 frag (v2f i) : SV_Target
            {
                float3 d = normalize(i.dir);
                fixed3 a = grad(d.y, _TopA.rgb, _HorizonA.rgb, _BottomA.rgb);
                fixed3 b = grad(d.y, _TopB.rgb, _HorizonB.rgb, _BottomB.rgb);
                // m: 0 at the start of the transition, 1 where B already shows
                float key;
                if (_TransType < 0.5)      key = 0.5;                                  // crossfade
                else if (_TransType < 1.5) key = 1 - (d.y * 0.5 + 0.5);                // from top
                else if (_TransType < 2.5) key = d.y * 0.5 + 0.5;                      // from bottom
                else if (_TransType < 3.5) key = acos(clamp(d.z, -1, 1)) / UNITY_PI;   // ring from front (+Z)
                else key = hash2(floor(float2(atan2(d.x, d.z), d.y) * 24));            // dissolve
                float p = _Progress * (1 + _Softness);
                float m = _TransType < 0.5 ? _Progress : smoothstep(key, key + _Softness, p);
                fixed3 c = lerp(a, b, m);
                c = lerp(c, fixed3(1, 1, 1), _Flash);
                return fixed4(c, 1);
            }
            ENDCG
        }
    }
}
