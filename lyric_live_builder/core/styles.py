# Style palettes ported from JIZURA v0.13.0 (src/04_styles.js, 11p_styles.js, 11p_horror3.js J.STYLES; the
# schemes in its order: the first is the style's own colour), MIT License, Copyright (c) 2026 hakoniwa.
# With "Style Colors" the dome takes a scheme's background as JIZURA does (core/world.plan_world); the text and
# the particles use the scheme whose background matches the dome.
"""Styles: text and particle colours (design §5.5)."""
from . import color

# scheme: bg (the background it was made for), fg (text), sub, accent (emphasis), accent2, ghostA / ghostB (particles)
STYLES = {
    "noir": {"name": "Noir Chroma", "body": "body", "schemes": [
        dict(bg="#060607", fg="#F5EEEA", sub="#BDB6B2", accent="#F5A50C", accent2="#16F4D4", ghostA="#F5A50C", ghostB="#16F4D4"),
        dict(bg="#F2EDE8", fg="#0B0B0C", sub="#4A4644", accent="#E0600C", accent2="#0FAE98", ghostA="#F5A50C", ghostB="#16C4B4")]},
    "crimson": {"name": "Crimson Signal", "body": "body", "schemes": [
        dict(bg="#C8103F", fg="#FFFFFF", sub="#FFD9E2", accent="#140509", accent2="#39F2C8", ghostA="#FFFFFF", ghostB="#39F2C8"),
        dict(bg="#FF6F98", fg="#FFFFFF", sub="#FFE3EB", accent="#1A0710", accent2="#39F2C8", ghostA="#FFFFFF", ghostB="#1A0710"),
        dict(bg="#150509", fg="#FF3D6E", sub="#FF9DB6", accent="#FFFFFF", accent2="#39F2C8", ghostA="#FF3D6E", ghostB="#39F2C8")]},
    "caution": {"name": "Caution Signs", "body": "body", "schemes": [
        dict(bg="#F4D21F", fg="#141414", sub="#3A3510", accent="#E0231C", accent2="#1F3FD8", ghostA="#E0231C", ghostB="#1F3FD8"),
        dict(bg="#E0231C", fg="#F4D21F", sub="#FFE9A0", accent="#141414", accent2="#FFFFFF", ghostA="#141414", ghostB="#F4D21F"),
        dict(bg="#18181A", fg="#F4D21F", sub="#DDD6B0", accent="#E0231C", accent2="#FFFFFF", ghostA="#E0231C", ghostB="#1F3FD8")]},
    "magenta": {"name": "Pop Magenta", "body": "body", "schemes": [
        dict(bg="#FF0A8C", fg="#FFFFFF", sub="#FFD2EA", accent="#FFFFFF", accent2="#2B2BD9", ghostA="#FF8CC8", ghostB="#2B2BD9"),
        dict(bg="#FFFFFF", fg="#FF0A8C", sub="#FF6DB6", accent="#2B2BD9", accent2="#FF0A8C", ghostA="#2B2BD9", ghostB="#FF8CC8"),
        dict(bg="#2B2BD9", fg="#FFFFFF", sub="#C9C9FF", accent="#FF0A8C", accent2="#FFFFFF", ghostA="#FF0A8C", ghostB="#FFFFFF")]},
    "paper": {"name": "Paper and Ink", "body": "serif", "schemes": [
        dict(bg="#ECE9E3", fg="#1B2350", sub="#4D5270", accent="#C2185B", accent2="#111111", ghostA="#C2185B", ghostB="#1B2350"),
        dict(bg="#151515", fg="#F0EDE7", sub="#B8B4AC", accent="#C2185B", accent2="#1B2350", ghostA="#C2185B", ghostB="#3A4690"),
        dict(bg="#C2185B", fg="#FFFFFF", sub="#F6C6D8", accent="#1B2350", accent2="#111111", ghostA="#1B2350", ghostB="#FFFFFF"),
        dict(bg="#1B2350", fg="#F0EDE7", sub="#AEB2CC", accent="#C2185B", accent2="#FFFFFF", ghostA="#C2185B", ghostB="#FFFFFF")]},
    "hud": {"name": "Dark HUD", "body": "body", "schemes": [
        dict(bg="#131315", fg="#EFEDEA", sub="#8E8B88", accent="#F25A2B", accent2="#FFFFFF", ghostA="#F25A2B", ghostB="#7FD7FF"),
        dict(bg="#0B0B0C", fg="#FFFFFF", sub="#9A9796", accent="#F25A2B", accent2="#FFFFFF", ghostA="#F25A2B", ghostB="#FFFFFF")]},
    "mint": {"name": "Mint Terminal", "body": "body", "schemes": [
        dict(bg="#0A0E0D", fg="#E6FFF5", sub="#7FB9A8", accent="#9CFF3A", accent2="#2E8C74", ghostA="#FF3B6B", ghostB="#2EE6C8"),
        dict(bg="#3FAE93", fg="#0A0E0D", sub="#123A31", accent="#FFFFFF", accent2="#9CFF3A", ghostA="#FFFFFF", ghostB="#0A0E0D"),
        dict(bg="#F2F2EE", fg="#0A0E0D", sub="#40504B", accent="#2E8C74", accent2="#9CFF3A", ghostA="#2E8C74", ghostB="#9CFF3A")]},
    "specimen": {"name": "Specimen Book", "body": "serif", "schemes": [
        dict(bg="#1B1A1C", fg="#F2F0EC", sub="#A19E99", accent="#F2F0EC", accent2="#C8B98C", ghostA="#6E6A66", ghostB="#C8B98C"),
        dict(bg="#F2F0EC", fg="#1B1A1C", sub="#5E5B57", accent="#1B1A1C", accent2="#8A7A4E", ghostA="#B9B4AD", ghostB="#8A7A4E")]},
    "transit": {"name": "Transit Signs", "body": "body", "schemes": [
        dict(bg="#5B582B", fg="#FFFFFF", sub="#E6E2BC", accent="#E8C21A", accent2="#1A1A1A", ghostA="#E8C21A", ghostB="#1A1A1A"),
        dict(bg="#1A1A1A", fg="#FFFFFF", sub="#B8B5A0", accent="#E8C21A", accent2="#FFFFFF", ghostA="#E8C21A", ghostB="#7C7A55"),
        dict(bg="#9C9A94", fg="#FFFFFF", sub="#F0EEE6", accent="#E8C21A", accent2="#1A1A1A", ghostA="#E8C21A", ghostB="#1A1A1A")]},
    "blueprint": {"name": "Blueprint Blue", "body": "body", "schemes": [
        dict(bg="#1B1BE8", fg="#FFFFFF", sub="#C7C7FF", accent="#000000", accent2="#FFFFFF", ghostA="#000000", ghostB="#8C8CFF"),
        dict(bg="#000000", fg="#FFFFFF", sub="#9A9AFF", accent="#1B1BE8", accent2="#FFFFFF", ghostA="#1B1BE8", ghostB="#FFFFFF"),
        dict(bg="#FFFFFF", fg="#1B1BE8", sub="#5A5AF0", accent="#000000", accent2="#1B1BE8", ghostA="#000000", ghostB="#8C8CFF")]},
    "rouge": {"name": "Rouge Gradient", "body": "body", "schemes": [
        dict(bg="#E4E2E0", fg="#141414", sub="#6B6866", accent="#D40F1C", accent2="#141414", ghostA="#D40F1C", ghostB="#6B6866"),
        dict(bg="#140405", fg="#FFFFFF", sub="#C98A8E", accent="#E3141F", accent2="#FFFFFF", ghostA="#E3141F", ghostB="#FFFFFF")]},
    "mono": {"name": "Mono RGB", "body": "serif", "schemes": [
        dict(bg="#3B3D41", fg="#FFFFFF", sub="#B9BBBF", accent="#FFFFFF", accent2="#FFE34D", ghostA="#FF2A2A", ghostB="#2AA8FF"),
        dict(bg="#141517", fg="#FFFFFF", sub="#9EA0A4", accent="#FFE34D", accent2="#FFFFFF", ghostA="#FF2A2A", ghostB="#2AFF7A")]},
    # added in JIZURA v0.10 (the horror styles are picked by おまかせ only with the horror mood)
    "hr_ruin": {"name": "Ruins", "body": "serif", "moods": ("horror",), "schemes": [
        dict(bg="#161B18", fg="#D3DACF", sub="#7D887E", accent="#B0473A", accent2="#6E8B6B", ghostA="#5E7A62", ghostB="#8A3A30"),
        dict(bg="#8C958A", fg="#141814", sub="#2E362F", accent="#6A1A14", accent2="#E4E8DF", ghostA="#3F4D41", ghostB="#6A1A14"),
        dict(bg="#0C0F0D", fg="#A9B8A6", sub="#5D6B5E", accent="#C24A3A", accent2="#A9B8A6", ghostA="#2F4A36", ghostB="#5E1E18")]},
    "hr_night_rec": {"name": "Midnight Recording", "body": "body", "moods": ("horror",), "schemes": [
        dict(bg="#050505", fg="#EDEDED", sub="#8A8A8A", accent="#E3261E", accent2="#FFFFFF", ghostA="#6E6E6E", ghostB="#E3261E"),
        dict(bg="#0B0E0B", fg="#D8F0D8", sub="#6F866F", accent="#FF3A2A", accent2="#D8F0D8", ghostA="#3E6B3E", ghostB="#FF3A2A"),
        dict(bg="#DADADA", fg="#0A0A0A", sub="#4A4A4A", accent="#C8140E", accent2="#0A0A0A", ghostA="#8A8A8A", ghostB="#C8140E")]},
    "hr_curse": {"name": "Cursed Letter", "body": "body", "moods": ("horror",), "schemes": [
        dict(bg="#D8CBA4", fg="#2A2017", sub="#6B5B45", accent="#7E1410", accent2="#3F3326", ghostA="#9A2A20", ghostB="#8A7A5E"),
        dict(bg="#1C140E", fg="#E3D5B0", sub="#9A8866", accent="#B8261C", accent2="#E3D5B0", ghostA="#6E1510", ghostB="#5A4A34"),
        dict(bg="#C4B28A", fg="#3A0D0A", sub="#6E4A3A", accent="#1E1812", accent2="#7E1410", ghostA="#7E1410", ghostB="#6E5E44")]},
    "sakura": {"name": "Sakura", "body": "body", "schemes": [
        dict(bg="#F8E4EB", fg="#4A1434", sub="#8A4A69", accent="#D93A74", accent2="#6F8F4E", ghostA="#EC6A9A", ghostB="#9A8AE6"),
        dict(bg="#26091B", fg="#FCE8F0", sub="#D69DB6", accent="#FF86B0", accent2="#B9E0A2", ghostA="#FF5C95", ghostB="#8A78FF"),
        dict(bg="#E77FA3", fg="#3A0B26", sub="#65173F", accent="#3A0B26", accent2="#FFF3F7", ghostA="#B4205A", ghostB="#6A4CC8"),
        dict(bg="#FFFAF8", fg="#A01E4A", sub="#B45F7E", accent="#E0457F", accent2="#4A1434", ghostA="#F07AA4", ghostB="#A898EA")]},
    "ocean": {"name": "Deep Sea", "body": "body", "schemes": [
        dict(bg="#031A2E", fg="#E4FAFF", sub="#7FB2C8", accent="#1FD2E6", accent2="#4C7DFF", ghostA="#1FD2E6", ghostB="#3B5BFF"),
        dict(bg="#0B5566", fg="#FFFFFF", sub="#A9E3EA", accent="#04182A", accent2="#7FF3FF", ghostA="#27E3F2", ghostB="#031A2E"),
        dict(bg="#DCF1F2", fg="#06243A", sub="#3E6A7C", accent="#0A7F98", accent2="#3B5BFF", ghostA="#16B4CC", ghostB="#5A6BFF"),
        dict(bg="#01060D", fg="#7FF6FF", sub="#3E9AAE", accent="#FFFFFF", accent2="#2E6BFF", ghostA="#2E6BFF", ghostB="#00FFC2")]},
    "sunset": {"name": "Sunset Gradient", "body": "body", "schemes": [
        dict(bg="#2A0F44", fg="#FFF0DC", sub="#E6A98F", accent="#FF7A30", accent2="#FF4A86", ghostA="#FF7A30", ghostB="#B84BFF"),
        dict(bg="#FF8A3D", fg="#2A0F44", sub="#5A1F55", accent="#2A0F44", accent2="#FFF0DC", ghostA="#E0306A", ghostB="#7A2BC0"),
        dict(bg="#B8325F", fg="#FFF3E4", sub="#FFC7A8", accent="#FFC15E", accent2="#2A0F44", ghostA="#FFC15E", ghostB="#2A0F44"),
        dict(bg="#FFE4CF", fg="#3A1250", sub="#8A4A6A", accent="#F2562E", accent2="#8A3FD1", ghostA="#FF6A3D", ghostB="#9A4BE0")]},
    "forest": {"name": "Forest Notebook", "body": "body", "schemes": [
        dict(bg="#1D291B", fg="#EFE9D6", sub="#A8B08A", accent="#B7C95A", accent2="#C4833F", ghostA="#8FB04A", ghostB="#C4833F"),
        dict(bg="#EDE6D1", fg="#22301F", sub="#5D6647", accent="#4F7A35", accent2="#8A5A32", ghostA="#6F9A45", ghostB="#B0703A"),
        dict(bg="#4A3526", fg="#F2EAD3", sub="#CDB894", accent="#B7C95A", accent2="#EFE9D6", ghostA="#8FB04A", ghostB="#D9A441"),
        dict(bg="#A9BC96", fg="#1A2618", sub="#34482F", accent="#1A2618", accent2="#F2EAD3", ghostA="#4F7A35", ghostB="#8A5A32")]},
    "vapor": {"name": "Vaporwave", "body": "body", "schemes": [
        dict(bg="#3A2A6E", fg="#FFFFFF", sub="#D6C8FF", accent="#FF8FD8", accent2="#7DF9FF", ghostA="#FF71CE", ghostB="#01CDFE"),
        dict(bg="#FFC6EC", fg="#3A2A6E", sub="#74489A", accent="#7A3BFF", accent2="#0F9FC8", ghostA="#2EC8F0", ghostB="#B04BFF"),
        dict(bg="#8FEAF2", fg="#35246A", sub="#4A3C8A", accent="#35246A", accent2="#FF4FC0", ghostA="#FF5CC8", ghostB="#8A5CFF"),
        dict(bg="#1A1030", fg="#FFFB96", sub="#B9A6E0", accent="#05FFA1", accent2="#FF71CE", ghostA="#FF71CE", ghostB="#01CDFE")]},
    "newsprint": {"name": "Newsprint", "body": "serif", "schemes": [
        dict(bg="#E6E5E0", fg="#111111", sub="#4E4E4C", accent="#D8141B", accent2="#0A82C8", ghostA="#E4007F", ghostB="#00A0E9"),
        dict(bg="#111111", fg="#F2F2EE", sub="#A5A5A0", accent="#F5D300", accent2="#E4007F", ghostA="#E4007F", ghostB="#00A0E9"),
        dict(bg="#D8141B", fg="#FFFFFF", sub="#FFD6D0", accent="#111111", accent2="#F5D300", ghostA="#111111", ghostB="#F5D300")]},
    "synth80": {"name": "Synth 80s", "body": "body", "schemes": [
        dict(bg="#0B0414", fg="#FF4FD8", sub="#A98BFF", accent="#22E6FF", accent2="#FFE45C", ghostA="#22E6FF", ghostB="#6A3BFF"),
        dict(bg="#0B0414", fg="#22E6FF", sub="#8FA8FF", accent="#E62EBE", accent2="#FFE45C", ghostA="#FF4FD8", ghostB="#FFE45C"),
        dict(bg="#1C0A3A", fg="#FFFFFF", sub="#FFB0E8", accent="#E62EBE", accent2="#22E6FF", ghostA="#FF2E88", ghostB="#22E6FF"),
        dict(bg="#FF2E88", fg="#0B0414", sub="#3A0A30", accent="#0B0414", accent2="#22E6FF", ghostA="#22E6FF", ghostB="#FFE45C")]},
    "kraft": {"name": "Kraft Paper", "body": "body", "schemes": [
        dict(bg="#C49A6C", fg="#1A1410", sub="#46301E", accent="#B8361B", accent2="#F3E9D2", ghostA="#C33A1F", ghostB="#2E5E8C"),
        dict(bg="#F1E6CF", fg="#1A1410", sub="#6A5540", accent="#C33A1F", accent2="#2E5E8C", ghostA="#C33A1F", ghostB="#2E5E8C"),
        dict(bg="#1E1A17", fg="#F1E6CF", sub="#B8A68A", accent="#D9642E", accent2="#C49A6C", ghostA="#C49A6C", ghostB="#C33A1F"),
        dict(bg="#2E5E8C", fg="#F6EEDD", sub="#C9D6E2", accent="#F1E6CF", accent2="#C33A1F", ghostA="#C49A6C", ghostB="#1A1410")]},
    "candy": {"name": "Candy", "body": "body", "schemes": [
        dict(bg="#BDF0E2", fg="#3E2A8C", sub="#5A4A9A", accent="#EE3A88", accent2="#FFB020", ghostA="#FF5FA2", ghostB="#8A6BFF"),
        dict(bg="#FFDDEB", fg="#7A2BB8", sub="#A2468E", accent="#EE3A88", accent2="#2FC2B8", ghostA="#FF5FA2", ghostB="#3FB8FF"),
        dict(bg="#FFF0A0", fg="#B01E5E", sub="#9A4A2A", accent="#3F8FFF", accent2="#FF5FA2", ghostA="#FF5FA2", ghostB="#3FB8FF"),
        dict(bg="#6A33B0", fg="#FFF3FA", sub="#E3C8FF", accent="#FF8FC8", accent2="#7FF0E0", ghostA="#FF8FC8", ghostB="#7FF0E0")]},
    "acid": {"name": "Acid", "body": "body", "schemes": [
        dict(bg="#050505", fg="#C6FF00", sub="#86A800", accent="#FF2BD6", accent2="#FFFFFF", ghostA="#FF2BD6", ghostB="#3D5BFF"),
        dict(bg="#C6FF00", fg="#050505", sub="#2A3A00", accent="#050505", accent2="#FF2BD6", ghostA="#FF2BD6", ghostB="#2B3DFF"),
        dict(bg="#FF2BD6", fg="#050505", sub="#3A0030", accent="#C6FF00", accent2="#050505", ghostA="#C6FF00", ghostB="#2B3DFF"),
        dict(bg="#0A0A0A", fg="#FFFFFF", sub="#9A9A9A", accent="#C6FF00", accent2="#FF2BD6", ghostA="#C6FF00", ghostB="#FF2BD6")]},
    "sumi": {"name": "Ink and Vermilion", "body": "body", "schemes": [
        dict(bg="#EFE5CF", fg="#16130F", sub="#5E574C", accent="#B83A22", accent2="#16130F", ghostA="#9A9284", ghostB="#CC4A2E"),
        dict(bg="#121110", fg="#EFE8D8", sub="#9A9286", accent="#D9402A", accent2="#EFE8D8", ghostA="#5C5750", ghostB="#D9402A"),
        dict(bg="#B3301D", fg="#FFF6E8", sub="#FFD2C0", accent="#16130F", accent2="#FFF6E8", ghostA="#16130F", ghostB="#E8A070"),
        dict(bg="#BAB4A7", fg="#16130F", sub="#3E3A33", accent="#A82A18", accent2="#16130F", ghostA="#6E685E", ghostB="#B8321E")]},
    "gold": {"name": "Golden Night", "body": "serif", "schemes": [
        dict(bg="#0A0907", fg="#F3E7C4", sub="#B39A62", accent="#D4AF37", accent2="#F3E7C4", ghostA="#D4AF37", ghostB="#7A5230"),
        dict(bg="#C9A24A", fg="#0A0907", sub="#3A2C12", accent="#0A0907", accent2="#FFF4D6", ghostA="#8A5A1A", ghostB="#3A2C12"),
        dict(bg="#0B1024", fg="#F3E7C4", sub="#A89A78", accent="#D4AF37", accent2="#F3E7C4", ghostA="#D4AF37", ghostB="#3A5AA8"),
        dict(bg="#2B0A14", fg="#F6EBD0", sub="#C9A987", accent="#D4AF37", accent2="#F6EBD0", ghostA="#D4AF37", ghostB="#9A2A4E")]},
}
ORDER = list(STYLES)
DEFAULT = "noir"


def scheme_for(style_key, backdrop):
    """The style's scheme made for a background like `backdrop` (the dome's horizon colour)."""
    schemes = STYLES.get(style_key, STYLES[DEFAULT])["schemes"]
    return min(schemes, key=lambda s: abs(color.lum(s["bg"]) - color.lum(backdrop)))


def palette(style_key, backdrop, accent=None, scheme=None):
    """Readable colours for text and particles on this backdrop: {role: '#RRGGBB'}.
    accent: a user / random accent that replaces the style's accent. scheme: the scheme the background came from
    (else the one made for a background like this)."""
    schemes = STYLES.get(style_key, STYLES[DEFAULT])["schemes"]
    s = dict(schemes[scheme % len(schemes)] if scheme is not None else scheme_for(style_key, backdrop))
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
