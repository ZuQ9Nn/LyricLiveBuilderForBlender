// LyricLive Builder: the glyph mask (design §5.6) - the same formulas as the Blender preview's text
// material (preview/materials.py mask_reveal / line_fx_material). p: the glyph's own x and up in em (mesh and
// TextMesh Pro letters alike); _Mask: progress (1 = all shown); _MaskShape: kind, value, seed, w;
// _MaskBox: the line (x0, y0, x1, y1) in the glyph's coordinates (or the glyph's own frame for a window).
// Kinds: 1 wipe (value 1: from the right), 2 bands, 3 checker (value: cell em), 4 one band only (seed: band),
// 5 iris, 6 diagonal (value: direction), 7 blinds, 8 shutter, 9 window (value, seed: offset em at 0),
// 10 one vertical band only. llbLineFx draws on the plane in front of the line: wipe bar, checker tiles,
// iris ring, diagonal band, shutter lines.
#ifndef LLB_MASK_INCLUDED
#define LLB_MASK_INCLUDED

float _Mask;
float4 _MaskShape, _MaskBox;

float llbInOutCubic(float x) { x = saturate(x); return x < 0.5 ? 4 * x * x * x : 1 - pow(-2 * x + 2, 3) / 2; }
float llbInOutQuart(float x) { x = saturate(x); return x < 0.5 ? 8 * x * x * x * x : 1 - pow(-2 * x + 2, 4) / 2; }
float llbOutQuart(float x) { return 1 - pow(1 - saturate(x), 4); }
float llbOutQuint(float x) { return 1 - pow(1 - saturate(x), 5); }
float llbHash(float2 c, float seed) { return frac(sin(c.x * 12.9898 + c.y * 78.233 + seed) * 43758.5453); }

float llbMask(float2 p)
{
    float kind = _MaskShape.x, value = _MaskShape.y, m = _Mask;
    if (kind < 0.5 || m > 0.9999) return 1;
    float2 size = max(_MaskBox.zw - _MaskBox.xy, 1e-4), c = (_MaskBox.xy + _MaskBox.zw) * 0.5;
    float2 u = saturate((p - _MaskBox.xy) / size);
    if (kind < 1.5)                                            // wipe from the left (0) or the right (1)
        return u.x + value * (1 - 2 * u.x) < m + 1e-4 ? 1 : 0;
    if (kind < 2.5)                                            // bands from alternate sides, each a little later
    {
        float n = max(value, 1), b = min(floor(u.y * n), n - 1);
        float e = 1 - pow(2, -10 * saturate(m * 1.3 - b * 0.05));
        return u.x + fmod(b, 2) * (1 - 2 * u.x) < e + 1e-4 ? 1 : 0;
    }
    if (kind < 3.5)                                            // checker squares growing from their centres
    {
        float cell = max(value, 0.05);
        float2 q = (p - _MaskBox.xy) / cell, cc = floor(q);
        float d = fmod(cc.x + cc.y, 2) * 0.25 + u.x * 0.3 + llbHash(cc, _MaskShape.z) * 0.08;
        float half = 0.5 * (1 - pow(1 - saturate((m - d) / 0.22), 4));
        float2 f = abs(q - cc - 0.5);
        return max(f.x, f.y) < half + 1e-4 ? 1 : 0;
    }
    if (kind < 4.5)                                            // one horizontal band only (a sliding copy)
    {
        float n = max(value, 1);
        return abs(min(floor(u.y * n), n - 1) - _MaskShape.z) < 0.5 ? 1 : 0;
    }
    if (kind < 5.5)                                            // iris: a circle from the centre
        return length(p - c) < 0.5 * length(size) * m ? 1 : 0;
    if (kind < 6.5)                                            // diagonal: a slanted edge
    {
        float hv = size.y * 0.5, half = size.x * 0.5 + 0.5 * hv;
        float T = -half + 2 * half * llbInOutCubic((m - 0.18) / 0.74);
        return (p.x - c.x) * value < T + 0.5 * (p.y - c.y) ? 1 : 0;
    }
    if (kind < 7.5)                                            // blinds: slats widen from the top down
    {
        float pitch = max(0.2, size.y / 40), n = max(1, ceil(size.y / pitch));
        float k = floor((_MaskBox.w - p.y) / pitch), cy = _MaskBox.w - (k + 0.5) * pitch;
        float e = llbOutQuart((m - 0.55 * (n > 1 ? k / (n - 1) : 0)) / 0.45);
        return abs(p.y - cy) < pitch * 0.5 * e ? 1 : 0;
    }
    if (kind < 8.5)                                            // shutter: opens from the middle line
        return abs(p.y - c.y) < size.y * 0.5 * llbInOutQuart((m - 0.18) / 0.82) ? 1 : 0;
    if (kind < 9.5)                                            // window: the glyph's own frame, the glyph slides in
    {
        float2 q = p + (1 - m) * _MaskShape.yz;
        return all(q >= _MaskBox.xy) && all(q <= _MaskBox.zw) ? 1 : 0;
    }
    float n = max(value, 1);                                   // one vertical band only
    return abs(min(floor(u.x * n), n - 1) - _MaskShape.z) < 0.5 ? 1 : 0;
}

// Alpha on the line's effect plane; uv 0..1 across the line box.
float llbLineFx(float2 uv)
{
    float kind = _MaskShape.x, value = _MaskShape.y, m = _Mask;
    float2 size = _MaskBox.zw - _MaskBox.xy, p = uv * size, c = size * 0.5;
    if (m > 0.9999) return 0;
    if (kind > 0.5 && kind < 1.5)                              // the wipe's bar (0.07 em wide) on its edge
    {
        float edge = value > 0.5 ? 1 - m : m;
        return abs(uv.x - edge) * size.x < 0.035 ? 1 : 0;
    }
    if (kind > 2.5 && kind < 3.5)                              // accent squares popping up, then shrinking
    {
        float cell = max(value, 0.05);
        float2 q = p / cell, cc = floor(q);
        float d = fmod(cc.x + cc.y, 2) * 0.25 + uv.x * 0.3 + llbHash(cc, _MaskShape.z) * 0.08;
        float t = saturate((m - d) / 0.22);
        if (t <= 0 || t >= 0.75) return 0;
        float half = 0.5 * (1 - pow(t / 0.75, 3)) * min(1, t * 6);
        float2 f = abs(q - cc - 0.5);
        return max(f.x, f.y) < half ? 0.9 : 0;
    }
    if (kind > 4.5 && kind < 5.5)                              // the iris' ring
        return abs(length(p - c) - 0.5 * length(size) * m) < 0.015 ? 1 - smoothstep(0.55, 0.97, m) : 0;
    if (kind > 5.5 && kind < 6.5)                              // the band running ahead of the diagonal edge
    {
        float hv = size.y * 0.5, half = size.x * 0.5 + 0.5 * hv;
        float T = -half + 2 * half * llbInOutCubic((m - 0.18) / 0.74);
        float L = -half + 2 * half * llbOutQuart(m / 0.5);
        float x = (p.x - c.x) * value - 0.5 * (p.y - c.y);
        return x >= T && x < L ? 1 : 0;
    }
    if (kind > 7.5 && kind < 8.5)                              // the shutter's two lines
    {
        float half = size.x * 0.5 * llbOutQuint(m / 0.32), hh = size.y * 0.5 * llbInOutQuart((m - 0.18) / 0.82);
        float dy = abs(p.y - c.y);
        return abs(p.x - c.x) < half && abs(dy - hh) < 0.015 ? 1 - smoothstep(0.6, 0.9, m) : 0;
    }
    return 0;
}
#endif
