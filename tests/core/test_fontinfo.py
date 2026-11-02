"""text.fontinfo on minimal synthetic sfnt files (no font files are shipped in the repo)."""
import os
import struct
import tempfile
import unittest

from lyric_live_builder.text import fontinfo

UPEM = 1000
# glyph id -> (advance, lsb); gid 0 = .notdef
GLYPHS = {0: (500, 0), 1: (600, 10), 2: (1000, 20), 3: (1000, 30), 4: (250, 5)}
CMAP = {ord("A"): 1, ord("あ"): 2, ord("漢"): 3, ord(" "): 4, 0x20B9F: 3}   # last one is outside the BMP


def _table(tag, data):
    return tag.encode("latin-1"), data + b"\0" * (-len(data) % 4)


def _cmap4(cmap):
    bmp = sorted(c for c in cmap if c <= 0xFFFF)
    segs = [(c, c, (cmap[c] - c) & 0xFFFF) for c in bmp] + [(0xFFFF, 0xFFFF, 1)]
    n = len(segs)
    body = struct.pack(">HHHH", n * 2, 0, 0, 0)
    body += b"".join(struct.pack(">H", e) for _, e, _ in segs) + b"\0\0"
    body += b"".join(struct.pack(">H", s) for s, _, _ in segs)
    body += b"".join(struct.pack(">H", d) for _, _, d in segs)
    body += b"".join(struct.pack(">H", 0) for _ in segs)
    return struct.pack(">HHH", 4, 6 + len(body), 0) + body


def _cmap12(cmap):
    groups = sorted(cmap.items())
    body = struct.pack(">I", len(groups)) + b"".join(struct.pack(">III", c, c, g) for c, g in groups)
    return struct.pack(">HHII", 12, 0, 12 + len(body) - 4, 0) + body


def build_face(with_vmtx=True, cmap12=True, n_hmetrics=None):
    n = len(GLYPHS)
    nh = n_hmetrics or n
    head = bytearray(54)
    struct.pack_into(">H", head, 18, UPEM)
    struct.pack_into(">hhhh", head, 36, -100, -250, 1100, 950)      # bbox height 1200
    hhea = bytearray(36)
    struct.pack_into(">H", hhea, 34, nh)
    hmtx = b"".join(struct.pack(">Hh", *GLYPHS[g]) for g in range(nh))
    hmtx += b"".join(struct.pack(">h", GLYPHS[g][1]) for g in range(nh, n))
    maxp = struct.pack(">IH", 0x5000, n)
    sub = [(3, 1, _cmap4(CMAP))] + ([(3, 10, _cmap12(CMAP))] if cmap12 else [])
    off = 4 + 8 * len(sub)
    cmap_h, cmap_b = struct.pack(">HH", 0, len(sub)), b""
    for pid, eid, data in sub:
        cmap_h += struct.pack(">HHI", pid, eid, off + len(cmap_b))
        cmap_b += data
    os2 = bytearray(96)
    struct.pack_into(">H", os2, 0, 4)
    struct.pack_into(">hh", os2, 68, 880, -120)
    struct.pack_into(">h", os2, 88, 700)
    tables = [_table("head", bytes(head)), _table("hhea", bytes(hhea)), _table("hmtx", hmtx),
              _table("maxp", maxp), _table("cmap", cmap_h + cmap_b), _table("OS/2", bytes(os2))]
    if with_vmtx:
        vhea = bytearray(36)
        struct.pack_into(">H", vhea, 34, n)
        tables += [_table("vhea", bytes(vhea)),
                   _table("vmtx", b"".join(struct.pack(">Hh", 1100 if g else 1000, 0) for g in range(n)))]
    return sorted(tables)


def write_sfnt(faces, version=b"\0\1\0\0"):
    """faces: list of table lists. More than one face -> TTC."""
    ttc = len(faces) > 1
    out = bytearray()
    header_len = 12 + 4 * len(faces) if ttc else 0
    dirs, blobs = [], []
    pos = header_len + sum(12 + 16 * len(t) for t in faces)
    for tables in faces:
        d = bytearray(version + struct.pack(">HHHH", len(tables), 0, 0, 0))
        for tag, data in tables:
            d += struct.pack(">4sIII", tag, 0, pos, len(data))
            blobs.append(data)
            pos += len(data)
        dirs.append(d)
    if ttc:
        out += b"ttcf" + struct.pack(">HHI", 1, 0, len(faces))
        p = header_len
        for d in dirs:
            out += struct.pack(">I", p)
            p += len(d)
    for d in dirs:
        out += d
    for b in blobs:
        out += b
    return bytes(out)


class TestFontInfo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def font(self, name, data):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def check(self, fi):
        self.assertEqual(fi.units_per_em, UPEM)
        self.assertAlmostEqual(fi.blender_units_per_em, 1000 / 1200)
        self.assertEqual(fi.advance_em("A"), 0.6)
        self.assertEqual(fi.advance_em("あ"), 1.0)
        self.assertEqual(fi.advance_em("☃"), 0.5)                    # missing -> .notdef
        self.assertTrue(fi.has_char("漢"))
        self.assertEqual(fi.missing("Aあ 漢☃字"), ["☃", "字"])
        self.assertEqual((fi.ascender, fi.descender, fi.cap_height), (880, -120, 700))

    def test_ttf_cmap12_and_vmtx(self):
        fi = fontinfo.FontInfo(self.font("a.ttf", write_sfnt([build_face()])))
        self.check(fi)
        self.assertTrue(fi.has_char(chr(0x20B9F)))                      # format 12 covers non-BMP
        self.assertEqual(fi.vadvance_em("あ"), 1.1)

    def test_otf_cmap4_only_no_vmtx(self):
        fi = fontinfo.FontInfo(self.font("a.otf", write_sfnt([build_face(False, False)], b"OTTO")))
        self.check(fi)
        self.assertFalse(fi.has_char(chr(0x20B9F)))
        self.assertEqual(fi.vadvance_em("あ"), 1.0)                      # no vmtx -> 1 em

    def test_short_hmtx(self):
        fi = fontinfo.FontInfo(self.font("s.ttf", write_sfnt([build_face(n_hmetrics=2)])))
        self.assertEqual(fi.advance_em("あ"), 0.6)                       # past numberOfHMetrics: last advance
        self.assertEqual(fi.lsbs[3], 30)

    def test_ttc_first_face(self):
        path = self.font("c.ttc", write_sfnt([build_face(), build_face(False, False)]))
        fi = fontinfo.FontInfo(path)
        self.check(fi)
        self.assertIsNotNone(fi.vadvances)                               # first face has vmtx
        self.assertIsNone(fontinfo.FontInfo(path, 1).vadvances)

    def test_load_cache_and_errors(self):
        path = self.font("a.ttf", write_sfnt([build_face()]))
        self.assertIs(fontinfo.load(path), fontinfo.load(path))
        with self.assertRaises(ValueError):
            fontinfo.load(self.font("bad.ttf", b"hello world, not a font"))
        with self.assertRaises(ValueError):
            fontinfo.load(self.font("cut.ttf", write_sfnt([build_face()])[:200]))


if __name__ == "__main__":
    unittest.main()
