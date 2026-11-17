# Moods ported from JIZURA (src/08b_omakase.js J.MOODS: effect ranges, frame stepping, styles),
# MIT License, Copyright (c) 2026 hakoniwa. Ranges for particles and world switches are new.
"""Moods: what おまかせ rolls first; they bias styles, parts and effect strengths."""

MOODS = {
    "glitch": {"name": "Glitchy", "fx": {"motion": (0.6, 0.9), "particles": (0.5, 0.8), "decor": (0.3, 0.6),
                                         "density": (0.6, 0.9), "world_switch": (0.5, 0.9)},
               "koma": (12, 12, 8), "flash": 0.8, "pulse": True,
               "styles": ("noir", "crimson", "mint", "mono", "hud"),
               "transitions": ("dissolve", "whiteout", "wipe_side", "blackout")},
    "calm": {"name": "Gentle", "fx": {"motion": (0.3, 0.55), "particles": (0.3, 0.55), "decor": (0.2, 0.5),
                                      "density": (0.25, 0.45), "world_switch": (0.2, 0.5)},
             "koma": (0, 0, 12), "flash": 0.15, "pulse": False,
             "styles": ("specimen", "paper", "hud", "noir"),
             "transitions": ("crossfade", "dissolve", "wipe_down")},
    "pop": {"name": "Poppy", "fx": {"motion": (0.7, 1.0), "particles": (0.6, 0.95), "decor": (0.6, 1.0),
                                    "density": (0.5, 0.8), "world_switch": (0.5, 0.9)},
            "koma": (12, 12, 8, 0), "flash": 0.7, "pulse": True,
            "styles": ("magenta", "caution", "transit", "blueprint", "rouge"),
            "transitions": ("ring", "wipe_up", "whiteout", "wipe_side")},
    "graphic": {"name": "Graphic Design", "fx": {"motion": (0.5, 0.8), "particles": (0.4, 0.7), "decor": (0.7, 1.0),
                                                  "density": (0.5, 0.8), "world_switch": (0.4, 0.8)},
                "koma": (12, 12, 0), "flash": 0.5, "pulse": True,
                "styles": ("blueprint", "caution", "rouge", "mint", "transit"),
                "transitions": ("wipe_side", "wipe_down", "ring", "blackout")},
    "editorial": {"name": "Editorial", "fx": {"motion": (0.4, 0.65), "particles": (0.3, 0.55), "decor": (0.4, 0.7),
                                               "density": (0.35, 0.6), "world_switch": (0.3, 0.5)},
                  "koma": (0, 12), "flash": 0.25, "pulse": False,
                  "styles": ("specimen", "paper", "noir", "mono", "hud"),
                  "transitions": ("crossfade", "wipe_down", "blackout")},
    "emotional": {"name": "Emotional", "fx": {"motion": (0.55, 0.85), "particles": (0.5, 0.85), "decor": (0.3, 0.6),
                                               "density": (0.4, 0.7), "world_switch": (0.3, 0.6)},
                  "koma": (12, 0), "flash": 0.6, "pulse": False,
                  "styles": ("noir", "paper", "hud", "mono", "crimson"),
                  "transitions": ("crossfade", "ring", "whiteout", "dissolve")},
    "horror": {"name": "Horror", "fx": {"motion": (0.4, 0.75), "particles": (0.25, 0.5), "decor": (0.3, 0.6),
                                        "density": (0.35, 0.6), "world_switch": (0.3, 0.6)},
               "koma": (12, 0, 8), "flash": 0.55, "pulse": False,
               "styles": ("hr_ruin", "hr_night_rec", "hr_curse", "noir", "mono", "crimson"),
               "transitions": ("blackout", "dissolve", "crossfade")},
    "chaos": {"name": "Everything", "fx": {"motion": (0.5, 1.0), "particles": (0.45, 0.95), "decor": (0.4, 1.0),
                                           "density": (0.45, 0.9), "world_switch": (0.4, 0.9)},
              "koma": (12, 8, 0), "flash": 0.65, "pulse": True, "styles": None, "transitions": None},
}
ORDER = list(MOODS)
STICKY = ("horror",)                  # never rolled; once the user picks it, おまかせ keeps it
DEFAULT = "chaos"                     # no bias: every style and part is equally welcome


def favours(mood, tags):
    """Weight factor for a part / theme with these mood tags."""
    if not mood or mood == "chaos":
        return 1.0
    return 2.0 if mood in tags else 0.6
