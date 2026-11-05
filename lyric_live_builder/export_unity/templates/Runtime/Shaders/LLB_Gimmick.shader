// LyricLive Builder: stage objects. Opaque, a soft fixed light so forms read without scene lights, and
// a dissolve: alpha 1 is whole, alpha 0 is gone (the Blender preview's LLB_Gimmick). _Color is animated
// per object; user objects carry their colours per vertex (white otherwise). Built-in RP, VR single-pass safe.
Shader "LyricLive/Gimmick"
{
    Properties { _Color ("Color", Color) = (1,1,1,1) }
    SubShader
    {
        Tags { "Queue"="Geometry+10" "RenderType"="Opaque" "IgnoreProjector"="True" }
        Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "UnityCG.cginc"

            fixed4 _Color;

            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; fixed4 color : COLOR; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct v2f { float4 pos : SV_POSITION; float3 n : TEXCOORD0; float3 p : TEXCOORD1; fixed4 color : COLOR; UNITY_VERTEX_OUTPUT_STEREO };

            v2f vert (appdata i)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(i.vertex);
                o.n = UnityObjectToWorldNormal(i.normal);
                o.p = i.vertex.xyz;
                o.color = i.color;
                return o;
            }

            float noise (float3 p)
            {
                float3 q = p * 7.0;
                return 0.5 + 0.25 * (sin(q.x + 1.3 * sin(q.y)) + sin(q.y * 1.7 + 1.1 * sin(q.z))) * sin(q.z * 1.3 + 0.7 * sin(q.x * 1.9));
            }

            fixed4 frag (v2f i) : SV_Target
            {
                clip(noise(i.p) + 0.001 - (1 - _Color.a));
                float d = dot(normalize(i.n), normalize(float3(0, 0.89, 0.45)));   // from above, the audience's side
                fixed3 c = _Color.rgb * i.color.rgb * (0.55 + 0.55 * (0.5 + 0.5 * d));
                return fixed4(c, 1);
            }
            ENDCG
        }
    }
}
