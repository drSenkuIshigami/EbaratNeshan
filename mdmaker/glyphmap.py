"""Recover CID/GID → Unicode maps from embedded PDF fonts.

Old Iranian B-series fonts (B Zar, B Nazanin, B Titr, …) and Word-generated
Identity-H PDFs often ship a broken ToUnicode CMap that increment-maps glyph
IDs onto consecutive Arabic codepoints.  The actual glyph names, cmap, and
presentation-form grouping in the embedded TTF are trustworthy.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from .arabic import FORM_TO_LETTER, LETTER_FORMS, codepoint_from_glyph_name, logical_letter


AGL_EXTRA = {
    "space": " ",
    "nbspace": " ",
    "hyphen": "-",
    "sfthyphen": "-",
    "period": ".",
    "comma": ",",
    "exclam": "!",
    "colon": ":",
    "semicolon": ";",
    "parenleft": "(",
    "parenright": ")",
    "bracketleft": "[",
    "bracketright": "]",
    "slash": "/",
    "backslash": "\\",
    "quotedbl": '"',
    "quotesingle": "'",
    "asterisk": "*",
    "plus": "+",
    "equal": "=",
    "question": "?",
    "at": "@",
    "numbersign": "#",
    "dollar": "$",
    "percent": "%",
    "ampersand": "&",
    "underscore": "_",
    "bar": "|",
    "verticalbar": "|",
    "pipe": "|",
    "brokenbar": "|",
    "less": "<",
    "greater": ">",
    "asciitilde": "~",
    "asciicircum": "^",
    "grave": "`",
    "quoteleft": "‘",
    "quoteright": "’",
    "quotedblleft": "“",
    "quotedblright": "”",
    "endash": "–",
    "emdash": "—",
    "ellipsis": "…",
    "bullet": "•",
    "periodcentered": "·",
    "minus": "−",
    "multiply": "×",
    "divide": "÷",
    "copyright": "©",
    "registered": "®",
    "trademark": "™",
}


@dataclass
class GlyphInfo:
    gid: int
    name: str
    unicode: str | None
    width: float
    source: str
    fingerprint: tuple[int, ...] = ()


_LATIN_FONT = re.compile(
    r"(Calibri|Arial|Helvetica|Times|Courier|Georgia|Verdana|Tahoma|Cambria)",
    re.I,
)


@dataclass
class FontGlyphMap:
    name: str
    encoding: str
    identity: bool
    glyphs: dict[int, GlyphInfo]
    cid_to_text: dict[int, str]
    broken_tounicode: bool = False
    method: str = "font-cmap"

    def decode_cid(self, cid: int) -> str:
        text = self.cid_to_text.get(cid)
        if not text:
            info = self.glyphs.get(cid)
            text = (info.unicode if info else "") or ""
        if text in {"", "\x00"} and 32 <= cid < 127 and _LATIN_FONT.search(self.name or ""):
            return chr(cid)
        if text == "\x00":
            return ""
        return text


def _glyph_fingerprint(ttf: TTFont, name: str, bins: int = 12) -> tuple[int, ...]:
    glyph_set = ttf.getGlyphSet()
    if name not in glyph_set:
        return ()
    pen = RecordingPen()
    try:
        glyph_set[name].draw(pen)
    except Exception:
        return ()
    xs: list[float] = []
    ys: list[float] = []
    for op, pts in pen.value:
        for pt in pts:
            if not pt:
                continue
            if isinstance(pt[0], (int, float)):
                xs.append(float(pt[0]))
                ys.append(float(pt[1]))
    if not xs:
        return (0,)
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    dx = max(maxx - minx, 1.0)
    dy = max(maxy - miny, 1.0)
    cells = [0] * (bins * bins)
    for x, y in zip(xs, ys):
        ix = min(bins - 1, int((x - minx) / dx * bins))
        iy = min(bins - 1, int((y - miny) / dy * bins))
        cells[iy * bins + ix] += 1
    peak = max(cells) or 1
    return tuple(int(v / peak * 7) for v in cells)


def _hamming_like(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    acc = sum(abs(x - y) for x, y in zip(a, b))
    return acc / (7 * len(a))


def _reverse_cmap(ttf: TTFont) -> dict[str, str]:
    """glyph name → best unicode string. Prefer presentation-form codepoints."""
    best: dict[str, tuple[int, str]] = {}
    if "cmap" not in ttf:
        return {}
    for table in ttf["cmap"].tables:
        for cp, gname in table.cmap.items():
            if cp < 32 or gname in {".notdef", ".null"}:
                continue
            score = 0
            # Presentation forms are the most specific signal for Arabic fonts.
            if 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF:
                score = 3
            elif 0x0600 <= cp <= 0x06FF:
                score = 2
            elif 0x20 <= cp <= 0x7E:
                score = 1
            else:
                score = 0
            prev = best.get(gname)
            if prev is None or score > prev[0]:
                try:
                    best[gname] = (score, chr(cp))
                except ValueError:
                    continue
    return {name: ch for name, (_, ch) in best.items()}


def _letter_of(ch: str) -> str | None:
    if not ch:
        return None
    if ch in FORM_TO_LETTER:
        return FORM_TO_LETTER[ch]
    if ch in LETTER_FORMS:
        return ch
    return None


def _infer_form_groups(glyphs: dict[int, GlyphInfo]) -> None:
    """Fill unnamed GIDs that sit in a presentation-form run of one letter."""
    if not glyphs:
        return
    max_gid = max(glyphs)
    gids = list(range(max_gid + 1))
    i = 0
    while i <= max_gid:
        info = glyphs.get(i)
        if info is None:
            i += 1
            continue
        letter = _letter_of(info.unicode or "")
        if letter is None:
            i += 1
            continue
        j = i
        run: list[int] = []
        while j <= max_gid:
            other = glyphs.get(j)
            if other is None:
                break
            other_letter = _letter_of(other.unicode or "")
            if other.unicode is None or other_letter == letter:
                run.append(j)
                j += 1
                continue
            break
        if len(run) >= 2:
            forms = LETTER_FORMS.get(letter, ())
            used = {
                other.unicode
                for gid in run
                if (other := glyphs.get(gid)) and other.unicode
            }
            missing = [f for f in forms if f not in used]
            unnamed = [
                gid
                for gid in run
                if glyphs[gid].unicode is None
            ]
            for gid, form in zip(unnamed, missing):
                glyphs[gid].unicode = form
                glyphs[gid].source = "form-group"
        i = max(j, i + 1)


def _match_by_shape(glyphs: dict[int, GlyphInfo]) -> None:
    named = [g for g in glyphs.values() if g.unicode and g.fingerprint]
    unnamed = [g for g in glyphs.values() if g.unicode is None and g.fingerprint]
    for target in unnamed:
        best: tuple[float, GlyphInfo] | None = None
        for cand in named:
            dist = _hamming_like(target.fingerprint, cand.fingerprint)
            # Prefer similar advance width so kashida does not match alef.
            width_ratio = abs(target.width - cand.width) / max(cand.width, 1.0)
            score = dist + 0.15 * width_ratio
            if best is None or score < best[0]:
                best = (score, cand)
        if best and best[0] < 0.18:
            target.unicode = best[1].unicode
            target.source = f"shape:{best[1].name}"


def _parse_tounicode(data: bytes) -> dict[int, str]:
    text = data.decode("latin-1", errors="replace")
    mapping: dict[int, str] = {}

    def hex_to_int(h: str) -> int:
        return int(h, 16)

    def dest_to_text(dest: str) -> str:
        dest = dest.strip()
        if dest.startswith("[") and dest.endswith("]"):
            dest = dest[1:-1].strip()
        m = re.match(r"<([0-9A-Fa-f]+)>", dest)
        if not m:
            return ""
        hexbytes = m.group(1)
        chars = [chr(int(hexbytes[i : i + 4], 16)) for i in range(0, len(hexbytes), 4) if i + 4 <= len(hexbytes)]
        return "".join(chars)

    for m in re.finditer(
        r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
        text,
    ):
        # Could be bfchar or the start of a range; handled below more precisely.
        pass

    for block in re.finditer(r"(\d+)\s+beginbfchar(.*?)endbfchar", text, re.S):
        for m in re.finditer(r"<([0-9A-Fa-f]+)>\s*(<[^>]+>|\[[^\]]+\])", block.group(2)):
            mapping[hex_to_int(m.group(1))] = dest_to_text(m.group(2))

    for block in re.finditer(r"(\d+)\s+beginbfrange(.*?)endbfrange", text, re.S):
        body = block.group(2)
        for m in re.finditer(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]+\]|<[^>]+>)",
            body,
        ):
            start = hex_to_int(m.group(1))
            end = hex_to_int(m.group(2))
            dest = m.group(3).strip()
            if dest.startswith("["):
                parts = re.findall(r"<([0-9A-Fa-f]+)>", dest)
                for i, part in enumerate(parts):
                    mapping[start + i] = dest_to_text("<" + part + ">")
            else:
                base = dest_to_text(dest)
                if not base:
                    continue
                cp = ord(base[0])
                rest = base[1:]
                for i in range(end - start + 1):
                    mapping[start + i] = chr(cp + i) + rest
    return mapping


def tounicode_looks_broken(mapping: dict[int, str], glyphs: dict[int, GlyphInfo]) -> bool:
    """Word's Identity-H exporter increment-maps Arabic presentation GIDs."""
    if not mapping:
        return False
    disagreements = 0
    compared = 0
    for cid, text in mapping.items():
        info = glyphs.get(cid)
        if not info or not info.unicode or not text:
            continue
        font_letter = logical_letter(info.unicode)
        tu_letter = logical_letter(text[0])
        if font_letter and tu_letter and font_letter != tu_letter:
            disagreements += 1
        compared += 1
    if compared >= 8 and disagreements / compared > 0.25:
        return True
    # Huge incrementing bfrange over Arabic is another smoking gun.
    sequential = 0
    items = sorted((cid, text) for cid, text in mapping.items() if text)
    for (c1, t1), (c2, t2) in zip(items, items[1:]):
        if c2 == c1 + 1 and t1 and t2 and ord(t2[0]) == ord(t1[0]) + 1:
            sequential += 1
    return sequential >= 12


def _widths(ttf: TTFont) -> dict[str, float]:
    if "hmtx" not in ttf:
        return {}
    return {name: w for name, (w, _) in ttf["hmtx"].metrics.items()}


def build_from_ttf(data: bytes, font_name: str, encoding: str, tounicode: bytes | None) -> FontGlyphMap:
    ttf = TTFont(io.BytesIO(data))
    order = ttf.getGlyphOrder()
    widths = _widths(ttf)
    cmap_rev = _reverse_cmap(ttf)
    glyphs: dict[int, GlyphInfo] = {}
    for gid, name in enumerate(order):
        uname = codepoint_from_glyph_name(name)
        if uname is None:
            uname = AGL_EXTRA.get(name)
        if uname is None:
            uname = cmap_rev.get(name)
        if uname == "\uf0b7":
            uname = "•"
        source = "name" if uname else "unknown"
        if uname is None and name in cmap_rev:
            uname = cmap_rev[name]
            source = "cmap"
        fp = _glyph_fingerprint(ttf, name) if uname is None or name.startswith("glyph") else ()
        glyphs[gid] = GlyphInfo(
            gid=gid,
            name=name,
            unicode=uname,
            width=float(widths.get(name, 500)),
            source=source if uname else "unknown",
            fingerprint=fp,
        )

    _infer_form_groups(glyphs)
    need_shape = [g for g in glyphs.values() if g.unicode is None]
    if need_shape:
        for g in glyphs.values():
            if not g.fingerprint:
                g.fingerprint = _glyph_fingerprint(ttf, g.name)
        _match_by_shape(glyphs)

    identity = encoding in {"/Identity-H", "Identity-H", "/Identity-V", "Identity-V"}
    cid_to_text: dict[int, str] = {
        gid: info.unicode for gid, info in glyphs.items() if info.unicode
    }
    broken = False
    method = "font-cmap"
    if tounicode:
        tu = _parse_tounicode(tounicode)
        broken = tounicode_looks_broken(tu, glyphs)
        if not broken:
            for cid, text in tu.items():
                if cid not in cid_to_text and text:
                    cid_to_text[cid] = text
            method = "tounicode+font"
        else:
            method = "font-cmap (ignored-broken-tounicode)"
    ttf.close()
    return FontGlyphMap(
        name=font_name,
        encoding=encoding,
        identity=identity,
        glyphs=glyphs,
        cid_to_text=cid_to_text,
        broken_tounicode=broken,
        method=method,
    )


def _stream_bytes(obj: Any) -> bytes | None:
    if obj is None:
        return None
    try:
        resolved = obj.get_object() if hasattr(obj, "get_object") else obj
    except Exception:
        resolved = obj
    if hasattr(resolved, "get_data"):
        try:
            return resolved.get_data()
        except Exception:
            return None
    return None


def font_maps_from_page(page) -> dict[str, FontGlyphMap]:
    resources = page.get("/Resources") or {}
    fonts = resources.get("/Font") or {}
    maps: dict[str, FontGlyphMap] = {}
    for key, value in fonts.items():
        font = value.get_object() if hasattr(value, "get_object") else value
        base = str(font.get("/BaseFont", key))
        encoding = str(font.get("/Encoding", "/WinAnsiEncoding"))
        tounicode = _stream_bytes(font.get("/ToUnicode"))
        fd = None
        if "/FontDescriptor" in font:
            fd = font["/FontDescriptor"].get_object()
        elif "/DescendantFonts" in font:
            desc = font["/DescendantFonts"][0].get_object()
            encoding = str(font.get("/Encoding", desc.get("/Encoding", encoding)))
            if "/FontDescriptor" in desc:
                fd = desc["/FontDescriptor"].get_object()
            if tounicode is None:
                tounicode = _stream_bytes(font.get("/ToUnicode"))
        embedded = None
        if fd is not None:
            for tag in ("/FontFile2", "/FontFile3", "/FontFile"):
                if tag in fd:
                    embedded = _stream_bytes(fd[tag])
                    break
        if embedded:
            try:
                maps[str(key)] = build_from_ttf(embedded, base, encoding, tounicode)
                continue
            except Exception:
                pass
        # Fallback: ToUnicode only, or latin 1:1.
        tu_map = _parse_tounicode(tounicode) if tounicode else {}
        cid_to_text = dict(tu_map)
        if not cid_to_text:
            cid_to_text = {i: chr(i) for i in range(32, 127)}
        maps[str(key)] = FontGlyphMap(
            name=base,
            encoding=encoding,
            identity="Identity" in encoding,
            glyphs={},
            cid_to_text=cid_to_text,
            broken_tounicode=False,
            method="tounicode" if tu_map else "latin",
        )
    return maps
