// LyricLive Builder: LLBM meshes from meshes.bin (design §9.3, prototype S0-03).
using System;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;

namespace LyricLive.Editor
{
    public static class LLBMeshReader
    {
        public static Mesh Read(byte[] data, int offset, string name)
        {
            using var br = new BinaryReader(new MemoryStream(data, offset, data.Length - offset));
            if (new string(br.ReadChars(4)) != "LLBM") throw new Exception("[LLB][ERROR] bad mesh " + name);
            br.ReadUInt16();                                 // version
            int flags = br.ReadUInt16();
            int nVerts = (int)br.ReadUInt32(), nIdx = (int)br.ReadUInt32();
            int nShapes = br.ReadUInt16(), nUv4 = br.ReadUInt16();
            var v = new Vector3[nVerts];
            for (int i = 0; i < nVerts; i++) v[i] = new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle());
            Vector3[] n = null;
            if ((flags & 1) != 0)
            {
                n = new Vector3[nVerts];
                for (int i = 0; i < nVerts; i++) n[i] = new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle());
            }
            Vector2[] uv = null;
            if ((flags & 2) != 0)
            {
                uv = new Vector2[nVerts];
                for (int i = 0; i < nVerts; i++) uv[i] = new Vector2(br.ReadSingle(), br.ReadSingle());
            }
            Color32[] col = null;
            if ((flags & 4) != 0)
            {
                col = new Color32[nVerts];
                for (int i = 0; i < nVerts; i++) col[i] = new Color32(br.ReadByte(), br.ReadByte(), br.ReadByte(), br.ReadByte());
            }
            var uv4 = new System.Collections.Generic.List<Vector4>[(flags & 16) != 0 ? nUv4 : 0];
            for (int c = 0; c < uv4.Length; c++)
            {
                uv4[c] = new System.Collections.Generic.List<Vector4>(nVerts);
                for (int i = 0; i < nVerts; i++) uv4[c].Add(new Vector4(br.ReadSingle(), br.ReadSingle(), br.ReadSingle(), br.ReadSingle()));
            }
            bool i32 = (flags & 8) != 0;
            var idx = new int[nIdx];
            for (int i = 0; i < nIdx; i++) idx[i] = i32 ? (int)br.ReadUInt32() : br.ReadUInt16();
            var m = new Mesh { name = name, indexFormat = i32 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            m.vertices = v;
            if (n != null) m.normals = n;
            if (uv != null) m.uv = uv;
            if (col != null) m.colors32 = col;
            for (int c = 0; c < uv4.Length; c++) m.SetUVs(c, uv4[c]);
            m.triangles = idx;
            for (int s = 0; s < nShapes; s++)
            {
                var shapeName = System.Text.Encoding.UTF8.GetString(br.ReadBytes(br.ReadUInt16()));
                var d = new Vector3[nVerts];
                for (int i = 0; i < nVerts; i++) d[i] = new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle());
                m.AddBlendShapeFrame(shapeName, 100f, d, null, null);
            }
            m.RecalculateBounds();
            if (uv4.Length > 0)                              // line effects drift and widen in the shader
            {
                var b = m.bounds;
                b.Expand(4f);
                m.bounds = b;
            }
            return m;
        }
    }
}
