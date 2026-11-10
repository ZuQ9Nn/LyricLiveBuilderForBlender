// LyricLive Builder: TextMesh Pro letters (signed distance field atlas) with the glyph mask (LLBMask.cginc).
// Written for LyricLive, not derived from TextMesh Pro's shaders: it reads the atlas (_MainTex, distance in
// alpha), the vertex colour TextMesh Pro writes, and the letter's own coordinates. Built-in RP, VR single-pass safe.
Shader "LyricLiveBuilder/TextSDF"
{
    Properties
    {
        _MainTex ("Font Atlas", 2D) = "white" {}
        _Mask ("Mask Progress", Range(0, 1)) = 1
        _MaskShape ("Mask Shape", Vector) = (0,0,0,0)
        _MaskBox ("Mask Box", Vector) = (-1,-1,1,1)
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
            #include "UnityCG.cginc"
            #include "LLBMask.cginc"

            sampler2D _MainTex;

            struct appdata { float4 vertex : POSITION; float2 uv : TEXCOORD0; fixed4 color : COLOR; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct v2f { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float2 lp : TEXCOORD1; fixed4 color : COLOR; UNITY_VERTEX_OUTPUT_STEREO };

            v2f vert (appdata v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = v.uv;
                o.lp = v.vertex.xy;
                o.color = v.color;
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                float d = tex2D(_MainTex, i.uv).a;
                float w = max(fwidth(d), 1e-4) * 0.75;       // about a pixel of anti-aliasing at any distance
                fixed4 c = i.color;
                c.a *= smoothstep(0.5 - w, 0.5 + w, d) * llbMask(i.lp);
                return c;
            }
            ENDCG
        }
    }
}
