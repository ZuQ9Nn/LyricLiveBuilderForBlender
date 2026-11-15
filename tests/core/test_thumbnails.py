"""Part thumbnails (design §13): every part has its frames, and the PNG reader reads what the writer wrote."""
import json
import os
import unittest

import numpy as np

from lyric_live_builder.core import atlas, registry, styles
from lyric_live_builder.core.parts import backgrounds as bgs
from lyric_live_builder.core.parts import particles as pts

DIR = os.path.join(os.path.dirname(__file__), "..", "..", "lyric_live_builder", "thumbnails")


class Thumbnails(unittest.TestCase):
    def test_every_part_has_its_thumbnail(self):
        with open(os.path.join(DIR, "index.json"), encoding="utf-8") as f:
            idx = json.load(f)
        t = idx["tile"]
        want = {k: registry.keys(k) for k in ("layout", "enter", "hold", "exit")}
        want.update(particle=list(pts.PRESETS), style=list(styles.ORDER),
                    background=[k for k in bgs.ORDER if not bgs.needs_image(k)])     # a panorama is the user's
        for kind, keys in want.items():
            # a part added without running tools/make_part_thumbnails.py again fails here
            self.assertEqual(idx["rows"][kind], keys, kind)
            with open(os.path.join(DIR, f"{kind}.png"), "rb") as f:
                px = atlas.png_decode(f.read())
            self.assertEqual(px.shape, (len(idx["rows"][kind]) * t, idx["frames"][kind] * t, 4), kind)
            rows = px.reshape(len(idx["rows"][kind]), t, -1, 4)
            self.assertTrue((rows.reshape(len(rows), -1).max(axis=1) > 120).all(), kind)   # nothing left blank

    def test_png_round_trip(self):
        img = np.random.default_rng(3).random((5, 7, 4))
        back = atlas.png_decode(atlas.png_bytes(img))
        np.testing.assert_array_equal(back, (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
        with self.assertRaises(ValueError):
            atlas.png_decode(b"not a png")


if __name__ == "__main__":
    unittest.main()
