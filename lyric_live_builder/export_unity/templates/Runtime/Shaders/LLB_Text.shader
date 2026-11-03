// LyricLive Builder: lyric letters. Unlit colour with alpha; faces turned away from the view (the sides
// of 3D letters) get darker, like the Blender preview's LLB_Text. Built-in RP, VR single-pass safe.
Shader "LyricLive/Text"
{
    Properties
    {
        _Color ("Color", Color) = (1,1,1,1)
        _SideShade ("Side Shade", Color) = (0.35,0.35,0.4,1)
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" }
        Blend SrcAlpha OneMinusSrcAlpha
        ZWrite Off
        Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "UnityCG.cginc"

            fixed4 _Color, _SideShade;

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
                float facing = 1 - abs(dot(normalize(i.n), normalize(i.v)));
                fixed4 c = _Color;
                c.rgb *= lerp(fixed3(1, 1, 1), _SideShade.rgb, facing);
                return c;
            }
            ENDCG
        }
    }
}
