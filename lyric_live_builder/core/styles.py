# Style palettes ported from JIZURA (src/04_styles.js J.STYLES), MIT License,
# Copyright (c) 2026 hakoniwa. In 3D the background is the dome, so a style only colours
# the text and the particles; the scheme whose background matches the dome is used.
"""Styles: text and particle colours (design §5.5)."""
from . import color

# scheme: bg (the background it was made for), fg (text), sub, accent (emphasis), accent2, ghostA / ghostB (particles)
STYLES = {
    "noir": {"name": "Noir Chroma", "body": "body", "schemes": [
        dict(bg="#060607", fg="#F5EEEA", sub="#BDB6B2", accent="#F5A50C", accent2="#16F4D4", ghostA="#F5A50C", ghostB="#16F4D4"),
        dict(bg="#F2EDE8", fg="#0B0B0C", sub="#4A4644", accent="#E0600C", accent2="#0FAE98", ghostA="#F5A50C", ghostB="#16C4B4")]},
    "crimson": {"name": "Crimson Signal", "body": "body", "schemes": [
        dict(bg="#150509", fg="#FF3D6E", sub="#FF9DB6", accent="#FFFFFF", accent2="#39F2C8", ghostA="#FF3D6E", ghostB="#39F2C8"),
        dict(bg="#C8103F", fg="#FFFFFF", sub="#FFD9E2", accent="#140509", accent2="#39F2C8", ghostA="#FFFFFF", ghostB="#39F2C8"),
        dict(bg="#FF6F98", fg="#FFFFFF", sub="#FFE3EB", accent="#1A0710", accent2="#39F2C8", ghostA="#FFFFFF", ghostB="#1A0710")]},
    "caution": {"name": "Caution Signs", "body": "body", "schemes": [
        dict(bg="#18181A", fg="#F4D21F", sub="#DDD6B0", accent="#E0231C", accent2="#FFFFFF", ghostA="#E0231C", ghostB="#1F3FD8"),
        dict(bg="#F4D21F", fg="#141414", sub="#3A3510", accent="#E0231C", accent2="#1F3FD8", ghostA="#E0231C", ghostB="#1F3FD8"),
        dict(bg="#E0231C", fg="#F4D21F", sub="#FFE9A0", accent="#141414", accent2="#FFFFFF", ghostA="#141414", ghostB="#F4D21F")]},
    "magenta": {"name": "Pop Magenta", "body": "body", "schemes": [
        dict(bg="#2B2BD9", fg="#FFFFFF", sub="#C9C9FF", accent="#FF0A8C", accent2="#FFFFFF", ghostA="#FF0A8C", ghostB="#FFFFFF"),
        dict(bg="#FF0A8C", fg="#FFFFFF", sub="#FFD2EA", accent="#FFFFFF", accent2="#2B2BD9", ghostA="#FF8CC8", ghostB="#2B2BD9"),
        dict(bg="#FFFFFF", fg="#FF0A8C", sub="#FF6DB6", accent="#2B2BD9", accent2="#FF0A8C", ghostA="#2B2BD9", ghostB="#FF8CC8")]},
    "paper": {"name": "Paper and Ink", "body": "serif", "schemes": [
        dict(bg="#151515", fg="#F0EDE7", sub="#B8B4AC", accent="#C2185B", accent2="#1B2350", ghostA="#C2185B", ghostB="#3A4690"),
        dict(bg="#1B2350", fg="#F0EDE7", sub="#AEB2CC", accent="#C2185B", accent2="#FFFFFF", ghostA="#C2185B", ghostB="#FFFFFF"),
        dict(bg="#ECE9E3", fg="#1B2350", sub="#4D5270", accent="#C2185B", accent2="#111111", ghostA="#C2185B", ghostB="#1B2350")]},
    "hud": {"name": "Dark HUD", "body": "body", "schemes": [
        dict(bg="#131315", fg="#EFEDEA", sub="#8E8B88", accent="#F25A2B", accent2="#FFFFFF", ghostA="#F25A2B", ghostB="#7FD7FF"),
        dict(bg="#0B0B0C", fg="#FFFFFF", sub="#9A9796", accent="#F25A2B", accent2="#FFFFFF", ghostA="#F25A2B", ghostB="#FFFFFF")]},
    "mint": {"name": "Mint Terminal", "body": "body", "schemes": [
        dict(bg="#0A0E0D", fg="#E6FFF5", sub="#7FB9A8", accent="#9CFF3A", accent2="#2E8C74", ghostA="#FF3B6B", ghostB="#2EE6C8"),
        dict(bg="#F2F2EE", fg="#0A0E0D", sub="#40504B", accent="#2E8C74", accent2="#9CFF3A", ghostA="#2E8C74", ghostB="#9CFF3A")]},
    "specimen": {"name": "Specimen Book", "body": "serif", "schemes": [
        dict(bg="#1B1A1C", fg="#F2F0EC", sub="#A19E99", accent="#C8B98C", accent2="#F2F0EC", ghostA="#6E6A66", ghostB="#C8B98C"),
        dict(bg="#F2F0EC", fg="#1B1A1C", sub="#5E5B57", accent="#8A7A4E", accent2="#1B1A1C", ghostA="#B9B4AD", ghostB="#8A7A4E")]},
    "transit": {"name": "Transit Signs", "body": "body", "schemes": [
        dict(bg="#1A1A1A", fg="#FFFFFF", sub="#B8B5A0", accent="#E8C21A", accent2="#FFFFFF", ghostA="#E8C21A", ghostB="#7C7A55"),
        dict(bg="#5B582B", fg="#FFFFFF", sub="#E6E2BC", accent="#E8C21A", accent2="#1A1A1A", ghostA="#E8C21A", ghostB="#1A1A1A"),
        dict(bg="#9C9A94", fg="#FFFFFF", sub="#F0EEE6", accent="#E8C21A", accent2="#1A1A1A", ghostA="#E8C21A", ghostB="#1A1A1A")]},
    "blueprint": {"name": "Blueprint Blue", "body": "body", "schemes": [
        dict(bg="#000000", fg="#FFFFFF", sub="#9A9AFF", accent="#1B1BE8", accent2="#FFFFFF", ghostA="#1B1BE8", ghostB="#FFFFFF"),
        dict(bg="#1B1BE8", fg="#FFFFFF", sub="#C7C7FF", accent="#000000", accent2="#FFFFFF", ghostA="#000000", ghostB="#8C8CFF"),
        dict(bg="#FFFFFF", fg="#1B1BE8", sub="#5A5AF0", accent="#000000", accent2="#1B1BE8", ghostA="#000000", ghostB="#8C8CFF")]},
    "rouge": {"name": "Rouge Gradient", "body": "body", "schemes": [
        dict(bg="#140405", fg="#FFFFFF", sub="#C98A8E", accent="#E3141F", accent2="#FFFFFF", ghostA="#E3141F", ghostB="#FFFFFF"),
        dict(bg="#E4E2E0", fg="#141414", sub="#6B6866", accent="#D40F1C", accent2="#141414", ghostA="#D40F1C", ghostB="#6B6866")]},
    "mono": {"name": "Mono RGB", "body": "serif", "schemes": [
        dict(bg="#141517", fg="#FFFFFF", sub="#9EA0A4", accent="#FFE34D", accent2="#FFFFFF", ghostA="#FF2A2A", ghostB="#2AFF7A"),
        dict(bg="#3B3D41", fg="#FFFFFF", sub="#B9BBBF", accent="#FFE34D", accent2="#FFE34D", ghostA="#FF2A2A", ghostB="#2AA8FF")]},
}
ORDER = list(STYLES)
DEFAULT = "noir"


def scheme_for(style_key, backdrop):
    """The style's scheme made for a background like `backdrop` (the dome's horizon colour)."""
    schemes = STYLES.get(style_key, STYLES[DEFAULT])["schemes"]
    return min(schemes, key=lambda s: abs(color.lum(s["bg"]) - color.lum(backdrop)))


def palette(style_key, backdrop, accent=None):
    """Readable colours for text and particles on this backdrop: {role: '#RRGGBB'}.
    accent: a user / random accent that replaces the style's accent."""
    s = dict(scheme_for(style_key, backdrop))
    if accent:
        s["accent"] = accent
    out = {"bg": backdrop, "fg": color.fit_contrast(s["fg"], backdrop, 3.0),
           "sub": color.fit_contrast(s["sub"], backdrop, 2.0),
           "accent": color.fit_contrast(s["accent"], backdrop, 2.4),
           "accent2": color.fit_contrast(s["accent2"], backdrop, 1.8)}
    for k in ("ghostA", "ghostB"):
        out[k] = color.fit_contrast(s[k], backdrop, 1.35)
    out["white"] = "#FFFFFF"
    return out
