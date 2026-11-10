"""Keywords -> gimmick tags (spec §8.3.1, design §8.3). Lyrics and tags are compared after folding
katakana to hiragana, full width to half width and upper to lower case, so one entry covers
「星・ほし・ホシ・スター・STAR」."""
import re
import unicodedata

# tag -> words. The first group of tags has a built-in shape (core/gimmick_shapes.py); the rest are
# here so a user's asset tagged 猫 or cat matches both spellings (without an asset: the emblem).
WORDS = {
    "star": ("星", "ほし", "スター", "star", "stars", "☆", "★"),
    "moon": ("月", "つき", "ムーン", "moon", "三日月", "みかづき"),
    "sun": ("太陽", "たいよう", "お日様", "おひさま", "サン", "sun", "sunshine", "日差し", "ひざし"),
    "cloud": ("雲", "くも", "クラウド", "cloud", "clouds"),
    "heart": ("心", "こころ", "ハート", "heart", "hearts", "♡", "♥", "恋", "こい"),
    "flower": ("花", "はな", "フラワー", "flower", "flowers", "桜", "さくら", "薔薇", "ばら", "rose"),
    "snow": ("雪", "ゆき", "スノー", "snow", "❄"),
    "rain": ("雨", "あめ", "レイン", "rain", "雫", "しずく", "涙", "なみだ", "tears"),
    "feather": ("羽", "翼", "つばさ", "フェザー", "feather", "wings", "wing"),
    "door": ("扉", "とびら", "ドア", "door"),
    "key": ("鍵", "カギ", "キー", "key"),
    "clock": ("時計", "とけい", "クロック", "clock", "時間", "じかん"),
    "umbrella": ("傘", "アンブレラ", "umbrella"),
    "note": ("音符", "おんぷ", "メロディ", "メロディー", "melody", "音楽", "おんがく", "music", "♪", "♫"),
    "crown": ("王冠", "おうかん", "クラウン", "crown", "王様", "おうさま", "king", "queen"),
    "gem": ("宝石", "ほうせき", "ジュエル", "ダイヤ", "diamond", "jewel", "gem", "宝物", "たからもの"),
    "candle": ("蝋燭", "ろうそく", "キャンドル", "candle"),
    "tree": ("木", "樹", "ツリー", "tree", "trees", "森", "もり", "forest"),
    "pillar": ("柱", "はしら", "ピラー", "pillar", "塔", "tower"),
    "arch": ("アーチ", "arch", "虹", "にじ", "rainbow"),
    "box": ("箱", "はこ", "ボックス", "box", "プレゼント", "present", "gift"),
    "ring": ("指輪", "ゆびわ", "リング", "ring", "輪"),
    "bell": ("鐘", "ベル", "bell", "鈴", "すず"),
    "leaf": ("葉", "葉っぱ", "はっぱ", "リーフ", "leaf", "leaves"),
    "house": ("家", "おうち", "ハウス", "ホーム", "house", "home"),
    # no built-in shape
    "cat": ("猫", "ねこ", "ニャン", "キャット", "cat", "cats"),
    "dog": ("犬", "いぬ", "ドッグ", "dog", "dogs"),
    "bird": ("鳥", "とり", "バード", "bird", "birds"),
    "fish": ("魚", "さかな", "フィッシュ", "fish"),
    "butterfly": ("蝶", "ちょう", "バタフライ", "butterfly"),
    "fire": ("炎", "ほのお", "ファイア", "fire", "flame"),
    "sea": ("海", "うみ", "シー", "sea", "ocean"),
}
# particle preset -> words, for a line's particles set to "From the Lyrics" (longer words win: 花火 over 花)
PARTICLE_WORDS = {
    "stars": ("星", "ほし", "スター", "star", "stars", "☆", "★", "星空", "ほしぞら", "キラキラ", "きらきら", "twinkle"),
    "shooting": ("流れ星", "ながれぼし", "流星", "りゅうせい", "meteor"),
    "snow": ("雪", "ゆき", "スノー", "snow", "❄", "粉雪", "こなゆき"),
    "petals": ("花", "はな", "花びら", "はなびら", "桜", "さくら", "flower", "flowers", "petal", "petals", "blossom"),
    "bubbles": ("泡", "あわ", "シャボン", "bubble", "bubbles", "海", "うみ", "sea", "ocean"),
    "fireworks": ("花火", "はなび", "firework", "fireworks"),
    "hearts": ("心", "こころ", "ハート", "heart", "hearts", "♡", "♥", "恋", "こい", "愛", "好き", "love"),
    "notes": ("音符", "おんぷ", "メロディ", "メロディー", "melody", "音楽", "おんがく", "music", "♪", "♫", "歌", "song"),
    "motes": ("光", "ひかり", "light", "lights", "粒", "つぶ"),
    "shard_ring": ("欠片", "かけら", "破片", "はへん", "shards"),
    "warp": ("ワープ", "warp", "加速", "かそく", "スピード", "speed"),
    "shape_confetti": ("紙吹雪", "かみふぶき", "confetti", "お祝い", "おいわい", "祝福", "しゅくふく", "パレード", "parade"),
    "shape_float": ("図形", "ずけい", "幾何学", "きかがく", "geometry", "shape", "shapes", "かたち"),
    "poly_float": ("結晶", "けっしょう", "宝石", "ほうせき", "クリスタル", "crystal", "ダイヤ", "jewel", "gem"),
    "sparkle_burst": ("輝き", "かがやき", "輝く", "かがやく", "煌めき", "きらめき", "sparkle", "shine"),
}
# longer words that merely contain a keyword; blanked out before matching
STOP = ("ほしい", "ほしく", "ほしか", "ほしがる", "ほしがっ", "つきあ", "つきな", "うそつき", "くっつき", "おもいつき", "気づき",
        "月曜", "月日", "年月", "木曜", "花火", "はなび", "はなし", "はなれ", "はなす", "はなさ", "はなせ", "はなそ", "はなつ",
        "言葉", "ことのは", "家族", "家庭", "火曜", "かぎり", "かぎら", "かぎる", "ゆきた", "ゆきま", "ゆきな", "とりあ", "とりも",
        "ひとり", "ふたり", "あめりか", "こいし", "こいつ", "こいよ", "心配", "輪郭", "中心", "くもり", "もりあ", "もりも", "にじむ",
        "うみだ", "うみの親", "すずし", "すずめ", "はこぶ", "はこん", "いぬき")


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def _pattern(word):
    w = re.escape(normalize(word))
    return rf"(?<![a-z]){w}(?![a-z])" if word.isascii() and word.isalpha() else w


_cache = {}


def _table(extra, table=None):
    """[(normalized word, compiled pattern, tag)], longest first so 三日月 wins over 月."""
    table = table or WORDS
    key = (id(table),) + tuple(sorted((k, tuple(v)) for k, v in (extra or {}).items()))
    if key not in _cache:
        words = {t: list(ws) for t, ws in table.items()}
        for tag, ws in (extra or {}).items():
            words.setdefault(canonical(tag), []).extend(ws)
        rows = [(normalize(w), re.compile(_pattern(w)), t) for t, ws in words.items() for w in ws]
        _cache[key] = sorted(rows, key=lambda r: -len(r[0]))
    return _cache[key]


def find(text, extra=None, table=None, stop=STOP):
    """[(tag, word as written in the lyric)] in order of appearance. extra: {tag: [words]} (the user's);
    table: another dictionary than the stage objects' (PARTICLE_WORDS)."""
    folded = normalize(text)
    for s in stop:
        folded = folded.replace(normalize(s), " " * len(normalize(s)))
    hits = []
    for _, pattern, tag in _table(extra, table):
        for m in pattern.finditer(folded):
            hits.append((m.start(), m.end(), tag))
            folded = folded[:m.start()] + " " * (m.end() - m.start()) + folded[m.end():]
    hits.sort()
    # NFKC keeps the length of everything lyrics use, so the span also fits the written text
    fits = len(folded) == len(text)
    return [(tag, text[a:b] if fits else "") for a, b, tag in hits]


def canonical(tag):
    """A user's tag (猫, Cat, cat) -> the dictionary's tag, or the folded tag itself."""
    t = normalize(tag.strip())
    for key, words in WORDS.items():
        if t == key or t in (normalize(w) for w in words):
            return key
    return t


def parse_user(text):
    """Preferences text "cat=にゃんこ,ミケ; fox=きつね" -> {tag: [words]}."""
    out = {}
    for part in (text or "").replace("；", ";").split(";"):
        tag, _, words = part.partition("=")
        words = [w.strip() for w in re.split("[,、，]", words) if w.strip()]
        if tag.strip() and words:
            out.setdefault(canonical(tag), []).extend(words)
    return out


# for particles 花火 is a keyword itself, not a word to keep 花 from matching
PARTICLE_STOP = tuple(s for s in STOP if s not in ("花火", "はなび"))


def particles(text):
    """Particle presets named by the words of a line, in order of appearance."""
    return [tag for tag, _ in find(text, table=PARTICLE_WORDS, stop=PARTICLE_STOP)]

