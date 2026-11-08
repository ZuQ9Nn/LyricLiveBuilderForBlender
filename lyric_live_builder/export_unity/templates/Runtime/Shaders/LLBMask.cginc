// LyricLive Builder: the glyph mask (design §5.6) - the same formulas as the Blender preview's text
// material (preview/materials.py mask_reveal). p: the glyph's own x and up in em (mesh and TextMesh Pro
// letters alike); _Mask: progress (1 = all shown); _MaskShape: kind (1 wipe, 2 bands, 3 checker, 4 one band
// only), value, seed (the band for 4); _MaskBox: the whole line (x0, y0, x1, y1) in the glyph's coordinates.
// llbLineFx draws on the plane in front of the line: the wipe's bar, the checker's tiles.
#ifndef LLB_MASK_INCLUDED
#define LLB_MASK_INCLUDED

float _Mask;
float4 _MaskShape, _MaskBox;

float llbMask(float2 p)
{
    float kind = _MaskShape.x, value = _MaskShape.y, m = _Mask;
    if (kind < 0.5 || m > 0.9999) return 1;
    float2 u = saturate((p - _MaskBox.xy) / max(_MaskBox.zw - _MaskBox.xy, 1e-4));
    if (kind < 1.5)                                            // wipe from the left (0) or the right (1)
    {
        float x = u.x + value * (1 - 2 * u.x);
        return x < m + 1e-4 ? 1 : 0;
    }
    if (kind < 2.5)                                            // bands from alternate sides, each a little later
    {
        float n = max(value, 1);
        float b = min(floor(u.y * n), n - 1);
        float e = 1 - pow(2, -10 * saturate(m * 1.3 - b * 0.05));
        float x = u.x + fmod(b, 2) * (1 - 2 * u.x);
        return x < e + 1e-4 ? 1 : 0;
    }
    if (kind > 3.5)                                            // one band only (a sliding copy of the glyph)
    {
        float n = max(value, 1);
        return abs(min(floor(u.y * n), n - 1) - _MaskShape.z) < 0.5 ? 1 : 0;
    }
    float cell = max(value, 0.05);                             // checker squares growing from their centres
    float2 q = (p - _MaskBox.xy) / cell;
    float2 c = floor(q);
    float rnd = frac(sin(c.x * 12.9898 + c.y * 78.233 + _MaskShape.z) * 43758.5453);
    float d = fmod(c.x + c.y, 2) * 0.25 + u.x * 0.3 + rnd * 0.08;
    float t = saturate((m - d) / 0.22);
    float half = 0.5 * (1 - pow(1 - t, 4));
    float2 f = abs(q - c - 0.5);
    return max(f.x, f.y) < half + 1e-4 ? 1 : 0;
}

// Alpha on the line's effect plane; uv 0..1 across the line box.
float llbLineFx(float2 uv)
{
    float kind = _MaskShape.x, value = _MaskShape.y, m = _Mask;
    float2 size = _MaskBox.zw - _MaskBox.xy;
    if (m > 0.9999) return 0;
    if (kind > 0.5 && kind < 1.5)                              // the wipe's bar (0.07 em wide) on its edge
    {
        float edge = value > 0.5 ? 1 - m : m;
        return abs(uv.x - edge) * size.x < 0.035 ? 1 : 0;
    }
    if (kind > 2.5 && kind < 3.5)                              // accent squares popping up, then shrinking
    {
        float cell = max(value, 0.05);
        float2 q = uv * size / cell;
        float2 c = floor(q);
        float rnd = frac(sin(c.x * 12.9898 + c.y * 78.233 + _MaskShape.z) * 43758.5453);
        float d = fmod(c.x + c.y, 2) * 0.25 + uv.x * 0.3 + rnd * 0.08;
        float t = saturate((m - d) / 0.22);
        if (t <= 0 || t >= 0.75) return 0;
        float half = 0.5 * (1 - pow(t / 0.75, 3)) * min(1, t * 6);
        float2 f = abs(q - c - 0.5);
        return max(f.x, f.y) < half ? 0.9 : 0;
    }
    return 0;
}
#endif
