"""Themes: a background family and a particle set for a section (spec §3, design §5.5).

kinds: section kinds the theme suits (weighted up there); backgrounds / particles: preset keys
(core/parts/backgrounds.py, core/parts/particles.py), the first ones are the most typical."""

THEMES = {
    "morning_garden": {"name": "Morning Garden", "tags": ("calm", "emotional", "editorial", "pop"),
                       "kinds": ("intro", "verse"), "backgrounds": ("morning", "day", "dawn"),
                       "particles": ("petals", "motes", "bubbles")},
    "blue_sky": {"name": "Blue Sky Day", "tags": ("pop", "calm", "graphic"), "kinds": ("verse", "prechorus"),
                 "backgrounds": ("day", "morning"), "particles": ("bubbles", "motes", "hearts", "notes", "shape_confetti", "dot_march")},
    "sunset_city": {"name": "Sunset City", "tags": ("emotional", "editorial", "calm"),
                    "kinds": ("prechorus", "bridge", "verse"), "backgrounds": ("evening", "dusk_bands"),
                    "particles": ("motes", "petals", "shooting", "horizon")},
    "night_city": {"name": "City at Night", "tags": ("emotional", "glitch", "graphic", "editorial"),
                   "kinds": ("verse", "chorus"), "backgrounds": ("night", "deep_space"),
                   "particles": ("motes", "notes", "cubes", "circuit", "horizon")},
    "starry_night": {"name": "Starlit Night", "tags": ("emotional", "calm"), "kinds": ("chorus", "bridge", "outro"),
                     "backgrounds": ("starry", "night"), "particles": ("stars", "shooting", "motes", "plexus", "horizon")},
    "under_sea": {"name": "Under the Sea", "tags": ("calm", "emotional", "pop"), "kinds": ("verse", "interlude", "bridge"),
                  "backgrounds": ("underwater",), "particles": ("bubbles", "motes")},
    "flower_field": {"name": "Flower Field", "tags": ("pop", "calm", "emotional"), "kinds": ("chorus", "verse"),
                     "backgrounds": ("dawn", "morning", "day"), "particles": ("petals", "hearts", "motes")},
    "snow_night": {"name": "Snowy Night", "tags": ("calm", "emotional", "editorial"), "kinds": ("verse", "bridge", "outro"),
                   "backgrounds": ("night", "starry", "deep_space"), "particles": ("snow", "motes")},
    "warp_space": {"name": "Warp Space", "tags": ("glitch", "pop", "graphic"), "kinds": ("chorus", "interlude"),
                   "backgrounds": ("deep_space", "grid"), "particles": ("warp", "shard_ring", "motes", "circuit", "poly_float")},
    "festival": {"name": "Fireworks Festival", "tags": ("pop", "emotional"), "kinds": ("chorus", "outro"),
                 "backgrounds": ("night", "evening", "starry"), "particles": ("fireworks", "motes", "hearts", "shape_confetti")},
    "geometric": {"name": "Geometric Space", "tags": ("graphic", "editorial", "glitch"),
                  "kinds": ("verse", "prechorus", "interlude"), "backgrounds": ("grid", "rings", "dots", "style_color"),
                  "particles": ("cubes", "shard_ring", "motes", "shape_float", "poly_float", "dot_march", "plexus")},
    "digital": {"name": "Digital Noise", "tags": ("glitch", "graphic"), "kinds": ("bridge", "chorus", "interlude"),
                "backgrounds": ("grid", "deep_space", "style_color"), "particles": ("cubes", "warp", "notes", "circuit", "plexus")},
}
ORDER = list(THEMES)
