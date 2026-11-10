// LyricLive Builder: the background dome (design §8.2). Two background slots (A, B) mixed by a
// transition; the same logic as the Blender preview's LLB_Dome nodes. Opaque and ZWrite On so the
// skybox does not draw over it (prototype S0-07). Built-in RP, VR single-pass safe.
Shader "LyricLiveBuilder/Dome"
{
    Properties
    {
        _ModeA ("Mode A", Float) = 1
        _TopA ("Top A", Color) = (0.05,0.07,0.2,1)
        _HorizonA ("Horizon A", Color) = (0.1,0.14,0.28,1)
        _BottomA ("Bottom A", Color) = (0.02,0.02,0.04,1)
        _InkA ("Ink A", Color) = (1,1,1,1)
        _BandsA ("Bands A", Float) = 1
        _PatternA ("Pattern A", Float) = 0
        _PScaleA ("Pattern Scale A", Float) = 1
        _ModeB ("Mode B", Float) = 1
        _TopB ("Top B", Color) = (0.05,0.07,0.2,1)
        _HorizonB ("Horizon B", Color) = (0.1,0.14,0.28,1)
        _BottomB ("Bottom B", Color) = (0.02,0.02,0.04,1)
        _InkB ("Ink B", Color) = (1,1,1,1)
        _BandsB ("Bands B", Float) = 1
        _PatternB ("Pattern B", Float) = 0
        _PScaleB ("Pattern Scale B", Float) = 1
        _Next ("Next Slot (1 = B)", Float) = 0
        _Progress ("Progress", Float) = 0
        _Trans ("Transition", Float) = 0
        _Flash ("Flash", Float) = 0
        _FlashColor ("Flash Color", Color) = (1,1,1,1)
        _Bright ("Brightness", Float) = 1
        _CueDir ("Cue Direction", Vector) = (0,0,1,0)
        _CueAmount ("Cue Amount", Float) = 0
        _PanoTex ("Panorama", 2D) = "black" {}
    }
    SubShader
    {
        Tags { "Queue"="Geometry" "RenderType"="Opaque" "IgnoreProjector"="True" }
        ZWrite On
        Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "UnityCG.cginc"

            float _ModeA, _BandsA, _PatternA, _PScaleA, _ModeB, _BandsB, _PatternB, _PScaleB;
            float4 _TopA, _HorizonA, _BottomA, _InkA, _TopB, _HorizonB, _BottomB, _InkB, _FlashColor, _CueDir;
            float _Next, _Progress, _Trans, _Flash, _Bright, _CueAmount;
            sampler2D _PanoTex;

            struct appdata { float4 vertex : POSITION; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct v2f { float4 pos : SV_POSITION; float3 opos : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };

            v2f vert (appdata i)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(i.vertex);
                o.opos = i.vertex.xyz;
                return o;
            }

            float is_(float x, float k) { return abs(x - k) <= 0.5 ? 1.0 : 0.0; }
            float lineMask(float f, float lo, float hi) { return 1.0 - smoothstep(lo, hi, min(f, 1.0 - f)); }

            float3 slot(float3 d, float mode, float3 top, float3 hor, float3 bot, float3 ink, float bands,
                        float pattern, float pscale, float3 image)
            {
                float z = d.y;
                float tt = sqrt(abs(z));
                float b = max(bands, 1.0);
                float tq = min(floor(tt * b) / max(b - 1.0, 1.0), 1.0);
                tt = lerp(tt, tq, is_(mode, 2));
                float3 grad = z > 0 ? lerp(hor, top, tt) : lerp(hor, bot, tt);
                float lat = asin(clamp(z, -1, 1));
                float lon = atan2(d.x, d.z);
                float fu = frac(lon / 6.2832 * pscale);
                float fv = frac(lat / 3.1416 * pscale * 0.5);
                float fr = frac(acos(clamp(z, -1, 1)) / 3.1416 * pscale);
                float rings = lineMask(fr, 0.04, 0.09);
                float grid = max(lineMask(fu, 0.02, 0.05), lineMask(fv, 0.02, 0.05));
                float dots = 1.0 - smoothstep(0.18, 0.24, length(float2(fu - 0.5, fv - 0.5)));
                float mask = rings * is_(pattern, 0) + grid * is_(pattern, 1) + dots * is_(pattern, 2);
                float3 patterned = lerp(grad, ink, mask * 0.85);
                float3 c = lerp(hor, grad, saturate(is_(mode, 1) + is_(mode, 2)));
                c = lerp(c, patterned, is_(mode, 3));
                return lerp(c, image, is_(mode, 4));
            }

            float hash3(float3 p) { return frac(sin(dot(p, float3(12.9898, 78.233, 37.719))) * 43758.5453); }
            float vnoise(float3 p)
            {
                float3 i = floor(p), f = frac(p);
                f = f * f * (3 - 2 * f);
                float n000 = hash3(i), n100 = hash3(i + float3(1,0,0)), n010 = hash3(i + float3(0,1,0)), n110 = hash3(i + float3(1,1,0));
                float n001 = hash3(i + float3(0,0,1)), n101 = hash3(i + float3(1,0,1)), n011 = hash3(i + float3(0,1,1)), n111 = hash3(i + float3(1,1,1));
                return lerp(lerp(lerp(n000, n100, f.x), lerp(n010, n110, f.x), f.y), lerp(lerp(n001, n101, f.x), lerp(n011, n111, f.x), f.y), f.z);
            }
            float fbm(float3 p) { return 0.5 * vnoise(p) + 0.3 * vnoise(p * 2.03) + 0.2 * vnoise(p * 4.01); }

            fixed4 frag (v2f i) : SV_Target
            {
                float3 d = normalize(i.opos);
                float lon = atan2(d.x, d.z), lat = asin(clamp(d.y, -1, 1));
                float3 image = tex2D(_PanoTex, float2(0.5 + lon / 6.2832, 0.5 + lat / 3.1416)).rgb;
                float3 a = slot(d, _ModeA, _TopA.rgb, _HorizonA.rgb, _BottomA.rgb, _InkA.rgb, _BandsA, _PatternA, _PScaleA, image);
                float3 b = slot(d, _ModeB, _TopB.rgb, _HorizonB.rgb, _BottomB.rgb, _InkB.rgb, _BandsB, _PatternB, _PScaleB, image);
                float q = _Next * _Progress + (1 - _Next) * (1 - _Progress);
                float w = 0.06;
                float edge = q * (1 + 2 * w) - w;
                float s1 = (1 - d.y) * 0.5, s2 = (1 + d.y) * 0.5, s3 = (1 + d.x) * 0.5;
                float s4 = acos(clamp(d.z, -1, 1)) / 3.1416;
                float s5 = saturate((fbm(d * 4) - 0.3) / 0.4);
                float mask = q * is_(_Trans, 0)
                    + (1 - smoothstep(edge - w, edge + w, s1)) * is_(_Trans, 1)
                    + (1 - smoothstep(edge - w, edge + w, s2)) * is_(_Trans, 2)
                    + (1 - smoothstep(edge - w, edge + w, s3)) * is_(_Trans, 3)
                    + (1 - smoothstep(edge - w, edge + w, s4)) * is_(_Trans, 4)
                    + (1 - smoothstep(edge - w, edge + w, s5)) * is_(_Trans, 5);
                float wb = _Next * mask + (1 - _Next) * (1 - mask);
                float3 c = lerp(a, b, wb);
                c = lerp(c, _FlashColor.rgb, _Flash);
                c *= _Bright;
                float cue = pow(max(dot(d, normalize(_CueDir.xyz + 1e-6)), 0), 6) * _CueAmount * 0.12;
                c += cue * float3(1, 0.95, 0.85);
                return fixed4(c, 1);
            }
            ENDCG
        }
    }
}
