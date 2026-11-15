# Ported from JIZURA (src/08_planner.js parseLyrics / chunkText / splitToCount / partition, src/06_layouts.js splitLines,
# src/01_util.js script classes), MIT License, Copyright (c) 2026 hakoniwa.
# Added: section headings ([A], [サビ], ...).
"""Lyric notation parsing and chunking."""
import difflib
import re
import unicodedata
from dataclasses import dataclass, field

from .rng import js_round

def decode_text(data):
    """Bytes of a text file: UTF-16 with a BOM, UTF-8 with or without one, else Shift_JIS."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp932", errors="replace")


# ---- script classes for Japanese text ----
_KANJI = re.compile(r"[㐀-鿿豈-﫿々〆ヶ]")
_HIRA = re.compile(r"[ぁ-ゟ]")
_KATA = re.compile(r"[゠-ヿㇰ-ㇿｦ-ﾟ]")
_PUNCT = re.compile(r"""[、。，．,.!?！？…‥・「」『』（）()【】〈〉《》〔〕［］\[\]'"“”‘’ー〜～:：;；\-—―]""")
_LATIN = re.compile(r"[A-Za-z0-9]")
SMALL_KANA = "ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ"
VERT_ROTATE = "ー〜～…‥―—-()（）「」『』【】〈〉《》〔〕[]［］→←:：;；=＝"


def is_kanji(c):
    return bool(_KANJI.search(c))


def is_hira(c):
    return bool(_HIRA.search(c))


def is_kata(c):
    return bool(_KATA.search(c))


def is_small_kana(c):
    return c in SMALL_KANA


def is_punct(c):
    return bool(_PUNCT.search(c))


def is_latin(c):
    return bool(_LATIN.search(c))


# ---- section headings ----
SECTION_KINDS = ("intro", "verse", "prechorus", "chorus", "interlude", "bridge", "outro", "custom")
_HEADING_NAMES = {
    "intro": ("イントロ", "intro"),
    "verse": ("a", "aメロ", "verse"),
    "prechorus": ("b", "bメロ", "pre-chorus", "prechorus"),
    "chorus": ("サビ", "chorus"),
    "interlude": ("間奏", "interlude"),
    "bridge": ("cメロ", "bridge", "大サビ"),
    "outro": ("アウトロ", "outro"),
}
_HEADING_KIND = {n: k for k, names in _HEADING_NAMES.items() for n in names}
_HEADING_RE = re.compile(r"^\[([^\]\d:][^\]:]{0,15})\]$")
_META_RE = re.compile(r"^\[(ti|ar|al|by|offset):(.*)\]$", re.I)
_LRC_RE = re.compile(r"^\[(\d+):(\d+(?:[.:]\d+)?)\]")
# a notation mark after a backslash is a letter (spec §5.1): it becomes a private-use character no notation reads
ESCAPABLE = "\\!/*|#[]"
_ESC = {c: chr(0xE000 + i) for i, c in enumerate(ESCAPABLE)}
_ESC_RE = re.compile(r"\\([" + re.escape(ESCAPABLE) + r"])")
_UNESC = str.maketrans({v: k for k, v in _ESC.items()})


def _escape(s):
    return _ESC_RE.sub(lambda m: _ESC[m.group(1)], s)


def _unescape(s):
    return s.translate(_UNESC) if s else s


def heading_kind(name):
    """'Ａメロ' / 'Verse 2' / 'サビ' -> section kind ('custom' when unknown)."""
    key = unicodedata.normalize("NFKC", name).strip().lower()
    key = re.sub(r"[\s_]*\d+$", "", key).replace(" ", "")
    return _HEADING_KIND.get(key, "custom")


@dataclass
class Heading:
    kind: str
    label: str


@dataclass
class Line:
    text: str
    note: str = None
    impact: bool = False
    emph: list = field(default_factory=list)
    manual: list = None              # chunks given with '/'
    gap_before: bool = False
    lrc: float = None
    heading: int = None              # index into ParsedLyrics.headings (None = before any heading)


@dataclass
class ParsedLyrics:
    lines: list
    headings: list
    meta: dict


def parse(raw):
    lines, headings, meta = [], [], {}
    pending_gap = False
    cur_heading = None
    for src in str(raw or "").replace("\r", "").split("\n"):
        s0 = _escape(src.strip())
        if not s0:
            if lines:
                pending_gap = True
            continue
        if s0.startswith("#"):
            continue
        mm = _META_RE.match(s0)
        if mm:
            meta[mm.group(1).lower()] = _unescape(mm.group(2).strip())
            continue
        mh = _HEADING_RE.match(s0)
        if mh:
            label = _unescape(mh.group(1).strip())
            headings.append(Heading(heading_kind(label), label))
            cur_heading = len(headings) - 1
            continue
        s, times = s0, []
        while True:
            m = _LRC_RE.match(s)
            if not m:
                break
            times.append(int(m.group(1)) * 60 + float(m.group(2).replace(":", ".")))
            s = s[m.end():]
        s = s.strip()
        note = None
        bar = s.find("|")
        if bar >= 0:
            note = s[bar + 1:].strip() or None
            s = s[:bar].strip()
        impact = False
        if len(s) > 1 and s.endswith("!"):
            impact = True
            s = s[:-1].strip()
        emph = []

        def _emph(m):
            emph.append(m.group(1))
            return m.group(1)
        s = re.sub(r"\*([^*]+)\*", _emph, s)
        manual = None
        if "/" in s:
            manual = [x.strip() for x in s.split("/") if x.strip()]
            latin = any(re.search(r"[A-Za-z]", x) for x in manual)
            s = (" " if latin else "").join(manual)
        if not s:
            continue
        base = dict(text=_unescape(s), note=_unescape(note), impact=impact, emph=[_unescape(e) for e in emph],
                    manual=[_unescape(x) for x in manual] if manual else manual,
                    gap_before=pending_gap, heading=cur_heading)
        pending_gap = False
        for t in times or [None]:
            lines.append(Line(lrc=t, **base))
    if any(ln.lrc is not None for ln in lines):
        lines.sort(key=lambda ln: 1e9 if ln.lrc is None else ln.lrc)
    return ParsedLyrics(lines, headings, meta)


def match_lines(old, new):
    """Line texts before / after an edit of the lyrics -> {new index: old index}.

    Equal lines are matched in order (repeated chorus lines stay with their own copy); a block
    of edited lines that keeps its size is matched one to one (typo fixes keep their taps)."""
    out = {}
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal" or (op == "replace" and a1 - a0 == b1 - b0):
            out.update({b0 + k: a0 + k for k in range(b1 - b0)})
    return out


# ---- chunking (bunsetsu-ish) ----

def _seg_type(s):
    if s.isspace():
        return "S"
    if all(is_punct(c) for c in s):
        return "P"
    if any(is_kanji(c) for c in s):
        return "K"
    if all(is_hira(c) or c == "ー" for c in s):
        return "H"
    if all(is_kata(c) or c == "ー" for c in s):
        return "T"
    if _LATIN.search(s):
        return "L"
    return "O"


def segments(text):
    """Script-class segmentation (JIZURA's fallback when Intl.Segmenter is missing)."""
    out, cur, ct = [], "", ""
    for c in text:
        t = _seg_type(c)
        if cur and t != ct and not (ct == "K" and t == "H"):
            out.append(cur)
            cur = ""
        cur += c
        ct = t
    if cur:
        out.append(cur)
    return out


def split_lines(text, max_per):
    """Break text into balanced lines of at most ~max_per characters, joined by '\\n'."""
    arr = list(text)
    if len(arr) <= max_per:
        return text
    n_lines = -(-len(arr) // max_per)
    per = len(arr) / n_lines
    out, start = [], 0
    for ln in range(1, n_lines):
        target = js_round(per * ln)
        best, best_score = target, -1
        for k in range(max(start + 1, target - 3), min(len(arr) - 1, target + 3) + 1):
            a, b = arr[k - 1], arr[k]
            s = 3 - abs(k - target)
            if is_hira(a) and not is_hira(b):
                s += 3
            if is_punct(a) or a in " 　":
                s += 5
            if is_small_kana(b) or b in "ーっ、。":
                s -= 6
            if s > best_score:
                best_score, best = s, k
        out.append("".join(arr[start:best]).strip())
        start = best
    out.append("".join(arr[start:]).strip())
    return "\n".join(out)


def chunk_text(text):
    chunks = []
    cur = None

    def close():
        nonlocal cur
        if cur and cur["s"].strip():
            chunks.append(cur["s"].strip())
        cur = None

    for sg in segments(text):
        t = _seg_type(sg)
        if t == "S":
            close()
            continue
        if t == "P":
            if cur:
                cur["s"] += sg
            elif chunks:
                chunks[-1] += sg
            else:
                cur = {"s": sg, "k": "P", "hasH": False}
            continue
        if not cur:
            cur = {"s": sg, "k": t, "hasH": t == "H"}
            continue
        if t == "H":
            n = len(sg)
            if n <= 3 or (cur["k"] != "H" and not cur["hasH"]) or (cur["k"] == "H" and len(cur["s"]) + n <= 4):
                cur["s"] += sg
                cur["hasH"] = True
                continue
            close()
            cur = {"s": sg, "k": "H", "hasH": True}
            continue
        if t == "K" and cur["k"] == "K" and not cur["hasH"] and len(cur["s"] + sg) <= 6:
            cur["s"] += sg
            continue
        if (t == "T" and cur["k"] == "T") or (t == "L" and cur["k"] == "L"):
            cur["s"] += sg
            continue
        close()
        cur = {"s": sg, "k": t, "hasH": t == "H"}
    close()
    out = []
    for c in chunks:
        n = len(c)
        if n > 10:
            out.extend(split_lines(c, -(-n // -(-n // 8))).split("\n"))
        else:
            out.append(c)
    for i in range(len(out) - 1, 0, -1):
        if len(out[i]) == 1 and not is_kanji(out[i]):
            out[i - 1] += out[i]
            del out[i]
    return out or [text]


def split_to_count(chunks, n):
    """Split the longest chunks until there are n, at a word boundary nearest the middle when there is one."""
    out = list(chunks)
    while len(out) < n:
        sizes = [len(c.split()) if " " in c else len(c) for c in out]
        big = max(sizes, default=0)
        if big <= 1:
            break
        i = sizes.index(big)
        c = out[i]
        if " " in c:
            words = c.split()
            mid = (len(words) + 1) // 2
            out[i:i + 1] = [" ".join(words[:mid]), " ".join(words[mid:])]
            continue
        cut, acc, best = (len(c) + 1) // 2, 0, 1e9
        for sg in segments(c)[:-1]:
            acc += len(sg)
            if abs(acc - len(c) / 2) < best:
                best, cut = abs(acc - len(c) / 2), acc
        out[i:i + 1] = [c[:cut], c[cut:]]
    return out


def partition(chunks, k):
    """Group neighbouring chunks into k groups of about the same length."""
    lens = [len(c) + 1 for c in chunks]
    target = sum(lens) / k
    groups, cur, acc = [], [], 0
    for i, c in enumerate(chunks):
        left, need = len(chunks) - i, k - len(groups)
        if cur and (acc + lens[i] / 2 > target or left < need) and len(groups) < k - 1:
            groups.append(cur)
            cur, acc = [], 0
        cur.append(c)
        acc += lens[i]
    if cur:
        groups.append(cur)
    return groups


def split_line(text, chunks, n):
    """text cut into at most n pieces at chunk boundaries: [(offset in text, piece)]."""
    parts = split_to_count(chunks, n)
    groups = partition(parts, min(n, len(parts)))
    starts, pos = [], 0
    for g in groups:
        for j, c in enumerate(g):
            at = text.find(c, pos)
            at = pos if at < 0 else at                     # lyrics edited since the notation was read
            if j == 0:
                starts.append(at)
            pos = at + len(c)
    return [(a, text[a:b].rstrip()) for a, b in zip(starts, starts[1:] + [len(text)])]
