"""Background dome presets, far objects and transitions (spec §8.2, design §8.2).

A preset resolves to a spec: the dome shader values of one slot (A or B) plus far objects.
Colours are '#RRGGBB' (sRGB); "style:<role>" takes the colour from the style's dark scheme."""
from .. import color, styles

MODE = {"solid": 0, "gradient": 1, "bands": 2, "pattern": 3, "image": 4}
PATTERN = {"rings": 0, "grid": 1, "dots": 2}

# far objects: (kind, azimuth°, elevation°, size, colour); sizes are radii in metres at their distance
PRESETS = {
    "morning": {"name": "Morning Sky", "kind": "gradient", "top": "#4A7FC1", "horizon": "#F6D8B8", "bottom": "#6E7F91",
                "far": [("sun", 40, 8, 3.0, "#FFE6B0"), ("mountains", 0, 0, 1.0, "#7D8FA6")]},
    "day": {"name": "Daytime Sky", "kind": "gradient", "top": "#2F6FD0", "horizon": "#BFE0F7", "bottom": "#7C8C70",
            "far": [("sun", -30, 50, 2.5, "#FFF6D8"), ("mountains", 0, 0, 1.0, "#7E95A8")]},
    "evening": {"name": "Sunset Sky", "kind": "gradient", "top": "#2B2D6E", "horizon": "#F2894B", "bottom": "#3A2232",
                "far": [("sun", -70, 4, 3.5, "#FFB070"), ("city", 0, 0, 1.0, "#1B1426")]},
    "night": {"name": "Night Sky", "kind": "gradient", "top": "#03050F", "horizon": "#1B2448", "bottom": "#05060A",
              "far": [("moon", 35, 30, 2.2, "#F2F0E0"), ("city", 0, 0, 1.0, "#0A0C16")]},
    "dawn": {"name": "Dawn Sky", "kind": "gradient", "top": "#1F2A55", "horizon": "#C98FA0", "bottom": "#2A2433",
             "far": [("mountains", 0, 0, 1.0, "#2E2C45")]},
    "starry": {"name": "Starry Sky", "kind": "gradient", "top": "#000006", "horizon": "#0B1030", "bottom": "#020205",
               "far": [("moon", -40, 45, 1.8, "#E8ECF8"), ("water", 0, 0, 1.0, "#070B1E")]},
    "underwater": {"name": "Under the Sea", "kind": "gradient", "top": "#3FA9C9", "horizon": "#0E4F73", "bottom": "#031A2B",
                   "far": []},
    "deep_space": {"name": "Deep Space", "kind": "solid", "top": "#02020A", "horizon": "#02020A", "bottom": "#02020A",
                   "far": []},
    "dusk_bands": {"name": "Banded Dusk", "kind": "bands", "bands": 7, "top": "#241B48", "horizon": "#E07A5F",
                   "bottom": "#1A1030", "far": [("water", 0, 0, 1.0, "#150D28")]},
    "rings": {"name": "Concentric Rings", "kind": "pattern", "pattern": "rings", "pscale": 14.0, "top": "style:bg",
              "horizon": "style:bg", "bottom": "style:bg", "ink": "style:ghostB", "far": []},
    "grid": {"name": "Lat-Long Grid", "kind": "pattern", "pattern": "grid", "pscale": 24.0, "top": "style:bg",
             "horizon": "style:bg", "bottom": "style:bg", "ink": "style:ghostA", "far": []},
    "dots": {"name": "Polka Dots", "kind": "pattern", "pattern": "dots", "pscale": 18.0, "top": "style:bg",
             "horizon": "style:bg", "bottom": "style:bg", "ink": "style:accent2", "far": []},
    "style_color": {"name": "Style Color", "kind": "solid", "top": "style:bg", "horizon": "style:bg", "bottom": "style:bg",
                    "far": []},
    "panorama": {"name": "Panorama Image", "kind": "image", "top": "#000000", "horizon": "#000000", "bottom": "#000000",
                 "far": [], "needs_image": True},
}
ORDER = list(PRESETS)
DEFAULT = "night"

TRANSITIONS = {
    "crossfade": {"name": "Soft Crossfade", "type": 0, "flash": None, "dur": 1.6},
    "whiteout": {"name": "White Out", "type": 0, "flash": "#FFFFFF", "dur": 1.2},
    "blackout": {"name": "Fade Through Black", "type": 0, "flash": "#000000", "dur": 1.6},
    "wipe_down": {"name": "Wipe from Above", "type": 1, "flash": None, "dur": 1.4},
    "wipe_up": {"name": "Wipe from Below", "type": 2, "flash": None, "dur": 1.4},
    "wipe_side": {"name": "Sideways Wipe", "type": 3, "flash": None, "dur": 1.4},
    "ring": {"name": "Expanding Ring", "type": 4, "flash": None, "dur": 1.5},
    "dissolve": {"name": "Speckled Dissolve", "type": 5, "flash": None, "dur": 1.8},
}
TRANSITION_ORDER = list(TRANSITIONS)
SOFTNESS = 0.06                       # half width of the wipe / ring edge (0..1 of the sweep)


def _resolve(value, style_key, scheme=None):
    if isinstance(value, str) and value.startswith("style:"):
        schemes = styles.STYLES.get(style_key, styles.STYLES[styles.DEFAULT])["schemes"]
        s = styles.scheme_for(style_key, "#000000") if scheme is None else schemes[scheme % len(schemes)]
        role = value[6:]
        return s["bg"] if role == "bg" else color.mix(s[role], s["bg"], 0.35)
    return value


def resolve(key, style_key=styles.DEFAULT, image_index=0, scheme=None):
    """Preset key -> concrete spec {key, mode, top, horizon, bottom, ink, bands, pattern, pscale, image, far}.
    scheme: which of the style's schemes gives the "style:" colours (None: its darkest)."""
    p = PRESETS.get(key) or PRESETS[DEFAULT]
    top, hor, bot = (_resolve(p[k], style_key, scheme) for k in ("top", "horizon", "bottom"))
    ink = _resolve(p.get("ink", hor), style_key, scheme)
    return {"key": key if key in PRESETS else DEFAULT, "mode": MODE[p["kind"]], "top": top, "horizon": hor,
            "bottom": bot, "ink": ink, "bands": float(p.get("bands", 1)), "pattern": float(PATTERN.get(p.get("pattern"), 0)),
            "pscale": float(p.get("pscale", 1.0)), "image": float(image_index),
            "far": [dict(kind=k, az=az, el=el, size=size, color=c) for k, az, el, size, c in p["far"]]}


SILHOUETTES = ("mountains", "city")


def backdrop(spec):
    """The colour text is read against: a mountain / city silhouette when there is one (it stands
    right behind lines at eye level), else the horizon of the sky."""
    sil = [f["color"] for f in spec["far"] if f["kind"] in SILHOUETTES]
    return sil[0] if sil else spec["horizon"]


def slot_values(spec):
    """Shader values of one dome slot: {param: tuple of floats} (colours linear)."""
    return {"mode": (float(spec["mode"]),), "top": color.linear(spec["top"]), "horizon": color.linear(spec["horizon"]),
            "bottom": color.linear(spec["bottom"]), "ink": color.linear(spec["ink"]), "bands": (spec["bands"],),
            "pattern": (spec["pattern"],), "pscale": (spec["pscale"],), "image": (spec["image"],)}


def needs_image(key):
    return bool(PRESETS.get(key, {}).get("needs_image"))
