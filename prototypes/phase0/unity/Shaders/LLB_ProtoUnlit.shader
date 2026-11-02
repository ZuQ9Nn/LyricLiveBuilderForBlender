// Phase 0 prototype (S0-07): unlit text/gimmick shader — color, emission, alpha, noise dissolve.
// Built-in RP, no geometry shader, mobile friendly.
Shader "LyricLive/Proto/Unlit"
{
    Properties
    {
        _Color ("Color", Color) = (1,1,1,1)
        _EmissionStrength ("Emission Strength", Range(0, 4)) = 0
        _Dissolve ("Dissolve", Range(0, 1)) = 0
        _DissolveScale ("Dissolve Scale", Float) = 8
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" }
        Blend SrcAlpha OneMinusSrcAlpha
        ZWrite Off
        Cull Back
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "UnityCG.cginc"

            fixed4 _Color;
            half _EmissionStrength, _Dissolve, _DissolveScale;

            struct appdata { float4 vertex : POSITION; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct v2f { float4 pos : SV_POSITION; float3 opos : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };

            v2f vert (appdata v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.opos = v.vertex.xyz;
                return o;
            }

            float hash3(float3 p) { return frac(sin(dot(p, float3(12.9898, 78.233, 37.719))) * 43758.5453); }

            fixed4 frag (v2f i) : SV_Target
            {
                float n = hash3(floor(i.opos * _DissolveScale));
                clip(n - _Dissolve);
                fixed4 c = _Color;
                c.rgb *= 1 + _EmissionStrength;
                return c;
            }
            ENDCG
        }
    }
}
