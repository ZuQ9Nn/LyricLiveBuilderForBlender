// LyricLive Builder: line effects (design §8.1, core/parts/lines.py). Each quad is one segment (or one dot)
// baked at rest; the vertex shader drifts both ends, fades links by length, widens lines that would be thinner
// than _Drift.w radians (dimming them by the ratio) and faces the band to the camera. _LineState = (draw, erase,
// seconds since the start, 0) comes from the Timeline; a fragment shows while erase <= s <= draw. Additive.
// Mesh: POSITION = this end; uv0 = other end + side; uv1 = this end's phase + s; uv2 = other end's phase + width;
// uv3 = (soft, dot, end sign, 0). Built-in RP, VR safe.
Shader "LyricLiveBuilder/Line"
{
    Properties
    {
        _Color ("Tint", Color) = (1,1,1,1)
        _LineState ("Draw, Erase, Time", Vector) = (1,0,0,0)
        _Drift ("Amplitude, Speed, Link Distance, Min Angle", Vector) = (0,0,0,0.0015)
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" }
        Blend SrcAlpha One
        ZWrite Off
        Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "UnityCG.cginc"

            fixed4 _Color;
            float4 _LineState, _Drift;
            static const float3 RATES = float3(1.0, 0.7, 1.3);       // Blender (1.0, 1.3, 0.7) in Unity's axes

            struct appdata
            {
                float4 vertex : POSITION; fixed4 color : COLOR;
                float4 other : TEXCOORD0; float4 phase : TEXCOORD1; float4 otherPhase : TEXCOORD2; float4 flags : TEXCOORD3;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };
            struct v2f
            {
                float4 pos : SV_POSITION; fixed4 color : COLOR;
                float4 uv : TEXCOORD0;      // side, end sign, s, soft
                float dot : TEXCOORD1;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            float3 Drift(float3 rest, float3 phase)
            {
                return rest + _Drift.x * sin(_Drift.y * RATES * _LineState.z + phase);
            }

            v2f vert (appdata v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 a = mul(unity_ObjectToWorld, float4(Drift(v.vertex.xyz, v.phase.xyz), 1)).xyz;
                float3 b = mul(unity_ObjectToWorld, float4(Drift(v.other.xyz, v.otherPhase.xyz), 1)).xyz;
                float side = v.other.w, w = v.otherPhase.w, alpha = v.color.a;
                if (_Drift.z > 0) alpha *= saturate((_Drift.z - distance(a, b)) / (0.45 * _Drift.z));
                float3 view = 0.5 * (a + b) - _WorldSpaceCameraPos;
                float dist = max(length(view), 1e-4);
                float minW = dist * _Drift.w;
                if (w < minW) { alpha *= w / minW; w = minW; }
                float3 p;
                if (v.flags.y > 0.5)
                {
                    float3 fwd = view / dist;
                    float3 ref = abs(fwd.y) > 0.98 ? float3(0, 0, 1) : float3(0, 1, 0);
                    float3 right = normalize(cross(ref, fwd));
                    float3 up = cross(fwd, right);
                    p = a + (right * side + up * v.flags.z) * (0.5 * w);
                }
                else
                {
                    // b - a points away from this end: flip it at the b end (end sign +1) so both ends agree
                    float3 s = cross(b - a, view) * -v.flags.z;
                    float sl = length(s);
                    s = sl > 1e-6 ? s / sl : float3(0, 1, 0);
                    p = a + s * (side * 0.5 * w);
                }
                o.pos = UnityWorldToClipPos(p);
                o.color = fixed4(v.color.rgb, alpha) * _Color;
                o.uv = float4(side, v.flags.z, v.phase.w, v.flags.x);
                o.dot = v.flags.y;
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                clip(_LineState.x - i.uv.z);
                clip(i.uv.z - _LineState.y);
                float a = i.color.a;
                if (i.dot > 0.5) a *= saturate((1 - length(i.uv.xy)) * 4);         // round dot
                else if (i.uv.w > 0.5) a *= saturate(1 - i.uv.x * i.uv.x);         // soft across the width
                return fixed4(i.color.rgb, a);
            }
            ENDCG
        }
    }
}
