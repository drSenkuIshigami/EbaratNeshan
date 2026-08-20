"""Arabic/Persian presentation-form tables and logical-letter normalization."""

from __future__ import annotations

import re
import unicodedata

# Presentation-form sequences as they typically appear in old Arabic/Persian
# fonts: isolated, final, initial, medial. Dual-joining letters have 4 forms;
# right-joining letters have 2.
LETTER_FORMS: dict[str, tuple[str, ...]] = {
    "آ": ("ﺁ", "ﺂ"),
    "أ": ("ﺃ", "ﺄ"),
    "ؤ": ("ﺅ", "ﺆ"),
    "إ": ("ﺇ", "ﺈ"),
    "ئ": ("ﺉ", "ﺊ", "ﺋ", "ﺌ"),
    "ا": ("ﺍ", "ﺎ"),
    "ب": ("ﺏ", "ﺐ", "ﺑ", "ﺒ"),
    "پ": ("ﭖ", "ﭗ", "ﭘ", "ﭙ"),
    "ة": ("ﺓ", "ﺔ"),
    "ت": ("ﺕ", "ﺖ", "ﺗ", "ﺘ"),
    "ث": ("ﺙ", "ﺚ", "ﺛ", "ﺜ"),
    "ج": ("ﺝ", "ﺞ", "ﺟ", "ﺠ"),
    "چ": ("ﭺ", "ﭻ", "ﭼ", "ﭽ"),
    "ح": ("ﺡ", "ﺢ", "ﺣ", "ﺤ"),
    "خ": ("ﺥ", "ﺦ", "ﺧ", "ﺨ"),
    "د": ("ﺩ", "ﺪ"),
    "ذ": ("ﺫ", "ﺬ"),
    "ر": ("ﺭ", "ﺮ"),
    "ز": ("ﺯ", "ﺰ"),
    "ژ": ("ﮊ", "ﮋ"),
    "س": ("ﺱ", "ﺲ", "ﺳ", "ﺴ"),
    "ش": ("ﺵ", "ﺶ", "ﺷ", "ﺸ"),
    "ص": ("ﺹ", "ﺺ", "ﺻ", "ﺼ"),
    "ض": ("ﺽ", "ﺾ", "ﺿ", "ﻀ"),
    "ط": ("ﻁ", "ﻂ", "ﻃ", "ﻄ"),
    "ظ": ("ﻅ", "ﻆ", "ﻇ", "ﻈ"),
    "ع": ("ﻉ", "ﻊ", "ﻋ", "ﻌ"),
    "غ": ("ﻍ", "ﻎ", "ﻏ", "ﻐ"),
    "ف": ("ﻑ", "ﻒ", "ﻓ", "ﻔ"),
    "ق": ("ﻕ", "ﻖ", "ﻗ", "ﻘ"),
    "ک": ("ﮎ", "ﮏ", "ﮐ", "ﮑ"),
    "ك": ("ﻙ", "ﻚ", "ﻛ", "ﻜ"),
    "گ": ("ﮒ", "ﮓ", "ﮔ", "ﮕ"),
    "ل": ("ﻝ", "ﻞ", "ﻟ", "ﻠ"),
    "م": ("ﻡ", "ﻢ", "ﻣ", "ﻤ"),
    "ن": ("ﻥ", "ﻦ", "ﻧ", "ﻨ"),
    "ه": ("ﻩ", "ﻪ", "ﻫ", "ﻬ"),
    "ۀ": ("ۀ", "ﮥ", "ﮤ"),
    "و": ("ﻭ", "ﻮ"),
    "ی": ("ﯼ", "ﯽ", "ﯾ", "ﯿ"),
    "ي": ("ﻱ", "ﻲ", "ﻳ", "ﻴ"),
    "ى": ("ﻯ", "ﻰ"),
}

# Extra ligatures that should become two (or more) logical letters.
LIGATURES: dict[str, str] = {
    "ﻻ": "لا",
    "ﻼ": "لا",
    "ﻷ": "لأ",
    "ﻸ": "لأ",
    "ﻹ": "لإ",
    "ﻺ": "لإ",
    "ﻵ": "لآ",
    "ﻶ": "لآ",
    "ﷲ": "الله",
}

FORM_TO_LETTER: dict[str, str] = {}
for _letter, _forms in LETTER_FORMS.items():
    FORM_TO_LETTER[_letter] = _letter
    for _form in _forms:
        FORM_TO_LETTER[_form] = _letter

# Persian prefers these codepoints over Arabic lookalikes.
PERSIAN_PREF: dict[str, str] = {
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ۀ": "ه",  # keep hamza-heh as heh + later ZWNJ handling if needed
}

ARABIC_LETTER_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)

TATWEEL = "\u0640"
ZWNJ = "\u200c"
ZWJ = "\u200d"

# Diacritics we keep optional; default is to drop them for LLM-clean text.
HARAKAT = frozenset(
    chr(c)
    for c in (
        0x064B,
        0x064C,
        0x064D,
        0x064E,
        0x064F,
        0x0650,
        0x0651,
        0x0652,
        0x0653,
        0x0654,
        0x0655,
        0x0656,
        0x0657,
        0x0658,
        0x0670,
    )
)


def is_arabic_char(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return any(start <= cp <= end for start, end in ARABIC_LETTER_RANGES)


def is_rtl_char(ch: str) -> bool:
    if not ch:
        return False
    try:
        return unicodedata.bidirectional(ch) in {"R", "AL", "AN"}
    except Exception:
        return is_arabic_char(ch)


def logical_letter(ch: str) -> str:
    """Map a presentation-form (or base) glyph to a logical letter string."""
    if not ch:
        return ch
    if ch in LIGATURES:
        return LIGATURES[ch]
    if ch in FORM_TO_LETTER:
        letter = FORM_TO_LETTER[ch]
        return PERSIAN_PREF.get(letter, letter)
    nfkc = unicodedata.normalize("NFKC", ch)
    if nfkc != ch:
        return "".join(PERSIAN_PREF.get(c, c) for c in nfkc)
    return PERSIAN_PREF.get(ch, ch)


def to_codepoint_name(ch: str) -> str | None:
    if len(ch) != 1:
        return None
    return f"uni{ord(ch):04X}"


def codepoint_from_glyph_name(name: str) -> str | None:
    """Parse Adobe-style glyph names: uniXXXX, uXXXXX, uniXXXXYYYY ligatures."""
    if not name:
        return None
    if name in {"space", "nbspace", "uni00A0"}:
        return " "
    if name == "hyphen":
        return "-"
    if name == "period":
        return "."
    if name == "comma":
        return ","
    if name == "exclam":
        return "!"
    if name == "colon":
        return ":"
    if name == "parenleft":
        return "("
    if name == "parenright":
        return ")"
    if name == "slash":
        return "/"
    if name == "backslash":
        return "\\"
    if name == "quotedbl":
        return '"'
    if name == "quotesingle":
        return "'"
    if name in {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"}:
        digits = {
            "zero": "0",
            "one": "1",
            "two": "2",
            "three": "3",
            "four": "4",
            "five": "5",
            "six": "6",
            "seven": "7",
            "eight": "8",
            "nine": "9",
        }
        return digits[name]
    if name.startswith("uni") and len(name) >= 7:
        hexpart = name[3:]
        chars: list[str] = []
        i = 0
        while i + 4 <= len(hexpart):
            chunk = hexpart[i : i + 4]
            if any(c not in "0123456789ABCDEFabcdef" for c in chunk):
                break
            chars.append(chr(int(chunk, 16)))
            i += 4
        if chars:
            return "".join(chars)
    if name.startswith("u") and 5 <= len(name) <= 8:
        hexpart = name[1:]
        if all(c in "0123456789ABCDEFabcdef" for c in hexpart):
            return chr(int(hexpart, 16))
    return None


def clean_persian_text(text: str, drop_harakat: bool = True, drop_kashida: bool = True) -> str:
    out: list[str] = []
    for ch in text:
        if not ch or (ord(ch) < 32 and ch not in "\n\t"):
            continue
        if drop_kashida and ch == TATWEEL:
            continue
        if drop_harakat and ch in HARAKAT:
            continue
        mapped = logical_letter(ch)
        out.append(mapped)
    collapsed = "".join(out)
    while "  " in collapsed:
        collapsed = collapsed.replace("  ", " ")
    return _fix_visual_delimiters(collapsed.strip())


def _fix_visual_delimiters(text: str) -> str:
    """PDF stores RTL parens visually, e.g. )پیام( → (پیام)."""
    for close, open_ in ((")", "("), ("]", "["), ("}", "{")):
        inner = rf"[^{re.escape(close + open_)}]*"
        text = re.sub(re.escape(close) + f"({inner})" + re.escape(open_), open_ + r"\1" + close, text)
    return text


def rtl_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalnum() or is_arabic_char(ch)]
    if not letters:
        return 0.0
    rtl = sum(1 for ch in letters if is_rtl_char(ch))
    return rtl / len(letters)
