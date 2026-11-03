// LyricLive Builder: gaze-guide light orbs. Additive; bright where the sphere faces the viewer,
// fading to its rim (the Blender preview's LLB_Glow).
Shader "LyricLive/Glow"
{
    Properties { _Color ("Color", Color) = (1,1,1,1) }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" }
        Blend One One
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
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct v2f { float4 pos : SV_POSITION; float3 n : TEXCOORD0; float3 v : TEXCOORD1; UNITY_VERTEX_OUTPUT_STEREO };
            v2f vert (appdata i)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(i.vertex);
                o.n = UnityObjectToWorldNormal(i.normal);
                o.v = _WorldSpaceCameraPos - mul(unity_ObjectToWorld, i.vertex).xyz;
                return o;
            }
            fixed4 frag (v2f i) : SV_Target
            {
                float core = pow(saturate(abs(dot(normalize(i.n), normalize(i.v)))), 2.5);
                return fixed4(_Color.rgb * core * _Color.a * 0.9, 1);
            }
            ENDCG
        }
    }
}
