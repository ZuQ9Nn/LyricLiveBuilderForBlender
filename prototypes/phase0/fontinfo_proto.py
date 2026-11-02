"""Phase 0 prototype: minimal sfnt (TTF/OTF/TTC) metrics reader.

Reads only what the add-on needs: unitsPerEm, horizontal/vertical advances,
cmap (format 4 / 12) and OS/2 vertical metrics. Pure Python (struct only),
so it runs both inside and outside Blender.
"""
import struct


class FontInfo:
    def __init__(self, path, face_index=0):
        with open(path, "rb") as f:
            self.data = f.read()
        offset = 0
        if self.data[:4] == b"ttcf":
            num_fonts = struct.unpack_from(">I", self.data, 8)[0]
            if face_index >= num_fonts:
                raise ValueError(f"face {face_index} out of range ({num_fonts})")
            offset = struct.unpack_from(">I", self.data, 12 + 4 * face_index)[0]
        num_tables = struct.unpack_from(">H", self.data, offset + 4)[0]
        self.tables = {}
        for i in range(num_tables):
            tag, _, off, length = struct.unpack_from(">4sIII", self.data, offset + 12 + 16 * i)
            self.tables[tag.decode("latin-1")] = (off, length)
        head = self.tables["head"][0]
        self.units_per_em = struct.unpack_from(">H", self.data, head + 18)[0]
        _, y_min, _, y_max = struct.unpack_from(">hhhh", self.data, head + 36)
        # Blender scales a FONT curve so that the head bbox height is 1.0 at size=1 (measured in S0-01)
        self.blender_units_per_em = self.units_per_em / (y_max - y_min)
        self.num_glyphs = struct.unpack_from(">H", self.data, self.tables["maxp"][0] + 4)[0]
        self.advances, self.lsbs = self._read_metrics("hhea", "hmtx")
        self.vadvances = None
        if "vhea" in self.tables and "vmtx" in self.tables:
            self.vadvances, _ = self._read_metrics("vhea", "vmtx")
        self.cmap = self._read_cmap()
        self.ascender = self.descender = self.cap_height = None
        if "OS/2" in self.tables:
            o = self.tables["OS/2"][0]
            self.ascender, self.descender = struct.unpack_from(">hh", self.data, o + 68)
            version = struct.unpack_from(">H", self.data, o)[0]
            if version >= 2:
                self.cap_height = struct.unpack_from(">h", self.data, o + 88)[0]

    def _read_metrics(self, head_tag, mtx_tag):
        n_metrics = struct.unpack_from(">H", self.data, self.tables[head_tag][0] + 34)[0]
        o = self.tables[mtx_tag][0]
        adv, lsb = [], []
        for i in range(n_metrics):
            a, b = struct.unpack_from(">Hh", self.data, o + 4 * i)
            adv.append(a)
            lsb.append(b)
        # glyphs past numberOfHMetrics reuse the last advance
        tail = self.num_glyphs - n_metrics
        for i in range(tail):
            adv.append(adv[-1])
            lsb.append(struct.unpack_from(">h", self.data, o + 4 * n_metrics + 2 * i)[0])
        return adv, lsb

    def _read_cmap(self):
        o = self.tables["cmap"][0]
        n = struct.unpack_from(">H", self.data, o + 2)[0]
        best = None
        for i in range(n):
            pid, eid, off = struct.unpack_from(">HHI", self.data, o + 4 + 8 * i)
            fmt = struct.unpack_from(">H", self.data, o + off)[0]
            # prefer full-repertoire format 12, then BMP format 4
            if fmt == 12 and (pid, eid) in ((3, 10), (0, 4), (0, 6)):
                best = (12, o + off)
                break
            if fmt == 4 and (pid, eid) in ((3, 1), (0, 3)) and best is None:
                best = (4, o + off)
        if best is None:
            raise ValueError("no unicode cmap")
        fmt, p = best
        table = {}
        if fmt == 12:
            n_groups = struct.unpack_from(">I", self.data, p + 12)[0]
            for g in range(n_groups):
                start, end, gid = struct.unpack_from(">III", self.data, p + 16 + 12 * g)
                for c in range(start, end + 1):
                    table[c] = gid + (c - start)
        else:
            seg2 = struct.unpack_from(">H", self.data, p + 6)[0]
            ends = p + 14
            starts = ends + seg2 + 2
            deltas = starts + seg2
            ranges = deltas + seg2
            for s in range(seg2 // 2):
                end = struct.unpack_from(">H", self.data, ends + 2 * s)[0]
                start = struct.unpack_from(">H", self.data, starts + 2 * s)[0]
                delta = struct.unpack_from(">h", self.data, deltas + 2 * s)[0]
                ro = struct.unpack_from(">H", self.data, ranges + 2 * s)[0]
                for c in range(start, end + 1):
                    if c == 0xFFFF:
                        continue
                    if ro == 0:
                        gid = (c + delta) & 0xFFFF
                    else:
                        addr = ranges + 2 * s + ro + 2 * (c - start)
                        gid = struct.unpack_from(">H", self.data, addr)[0]
                        if gid:
                            gid = (gid + delta) & 0xFFFF
                    if gid:
                        table[c] = gid
        return table

    def has_char(self, ch):
        return ord(ch) in self.cmap

    def advance_em(self, ch):
        """Horizontal advance in em (1.0 = unitsPerEm)."""
        gid = self.cmap.get(ord(ch), 0)
        return self.advances[gid] / self.units_per_em

    def vadvance_em(self, ch):
        if self.vadvances is None:
            return 1.0
        gid = self.cmap.get(ord(ch), 0)
        return self.vadvances[gid] / self.units_per_em

    def missing(self, text):
        return sorted({c for c in text if not c.isspace() and not self.has_char(c)})


if __name__ == "__main__":
    import sys
    fi = FontInfo(sys.argv[1])
    print("upem", fi.units_per_em, "glyphs", fi.num_glyphs, "asc", fi.ascender, "desc", fi.descender,
          "blender_units_per_em", round(fi.blender_units_per_em, 5))
    for c in "あア漢Ag、ー":
        print(c, fi.has_char(c), round(fi.advance_em(c), 4), round(fi.vadvance_em(c), 4))
