// LyricLive Builder: the plane in front of a line for the wipe's bar and the checker's tiles (LLBMask.cginc
// llbLineFx). The mesh is a unit quad; colour and the mask values come from the animation. Built-in RP, VR safe.
Shader "LyricLiveBuilder/LineFx"
{
    Properties
    {
        _Color ("Color", Color) = (1,1,1,1)
        _Mask ("Mask Progress", Range(0, 1)) = 1
        _MaskShape ("Mask Shape", Vector) = (0,0,0,0)
        _MaskBox ("Mask Box", Vector) = (-1,-1,1,1)
    }
    SubShader
    {
        Tags { "Queue"="Transparent+1" "RenderType"="Transparent" "IgnoreProjector"="True" }
        Blend SrcAlpha OneMinusSrcAlpha
        ZWrite Off
        Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            #include "LLBMask.cginc"

            fixed4 _Color;

            struct appdata { float4 vertex : POSITION; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct v2f { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };

            v2f vert (appdata v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = v.vertex.xy + 0.5;
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                fixed4 c = _Color;
                c.a *= llbLineFx(i.uv);
                return c;
            }
            ENDCG
        }
    }
}
