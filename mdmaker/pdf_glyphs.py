"""Walk a PDF content stream and emit positioned text runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pypdf.generic import ContentStream

from .glyphmap import FontGlyphMap, font_maps_from_page


@dataclass
class Glyph:
    text: str
    x: float
    y: float
    width: float
    size: float
    font: str
    cid: int
    page: int
    rtl_font: bool


@dataclass
class Run:
    x: float
    y: float
    size: float
    page: int
    rtl_font: bool
    font: str
    glyphs: list[Glyph] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(g.text for g in self.glyphs)

    @property
    def x1(self) -> float:
        if not self.glyphs:
            return self.x
        last = self.glyphs[-1]
        return last.x + last.width


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _iter_operations(page) -> list[tuple[list[Any], bytes]]:
    contents = page.get_contents()
    if contents is None:
        return []
    if not isinstance(contents, ContentStream):
        contents = ContentStream(contents, page)
    return list(contents.operations)


def _decode_string(raw: Any, fmap: FontGlyphMap) -> list[tuple[int, str]]:
    pairs: list[tuple[int, str]] = []
    if raw is None:
        return pairs
    if isinstance(raw, bytes):
        if fmap.identity:
            if len(raw) % 2 == 1:
                raw = raw + b"\x00"
            for i in range(0, len(raw), 2):
                cid = (raw[i] << 8) | raw[i + 1]
                pairs.append((cid, fmap.decode_cid(cid)))
            return pairs
        for b in raw:
            pairs.append((b, fmap.decode_cid(b) or (chr(b) if 32 <= b < 127 else "")))
        return pairs
    if isinstance(raw, str):
        for ch in raw:
            cid = ord(ch)
            if fmap.identity:
                pairs.append((cid, fmap.decode_cid(cid)))
            else:
                pairs.append((cid, fmap.decode_cid(cid) or (ch if cid < 256 else "")))
        return pairs
    return pairs


def _is_rtl_font(fmap: FontGlyphMap | None) -> bool:
    if fmap is None:
        return False
    name = fmap.name.lower()
    if any(tag in name for tag in ("zar", "nazanin", "lotus", "titr", "arabic", "iran", "naskh", "kufi", "traffic", "yekan", "mitra", "kamran")):
        return True
    arabic = 0
    seen = 0
    for info in fmap.glyphs.values():
        if not info.unicode:
            continue
        seen += 1
        if any(0x0600 <= ord(ch) <= 0x06FF or 0xFB50 <= ord(ch) <= 0xFEFF for ch in info.unicode):
            arabic += 1
        if seen >= 80:
            break
    return seen > 0 and arabic / seen > 0.2


def extract_runs(page, page_index: int = 0) -> list[Run]:
    maps = font_maps_from_page(page)
    runs: list[Run] = []
    font_key = "/F1"
    font_size = 12.0
    tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    char_space = 0.0
    word_space = 0.0
    horiz_scale = 1.0
    rise = 0.0
    current: Run | None = None

    def fmap() -> FontGlyphMap | None:
        return maps.get(font_key) or maps.get(str(font_key))

    def start_run() -> Run:
        nonlocal current
        font = fmap()
        current = Run(
            x=tm[4],
            y=tm[5] + rise,
            size=font_size,
            page=page_index,
            rtl_font=_is_rtl_font(font),
            font=font.name if font else font_key,
        )
        runs.append(current)
        return current

    def emit(cid: int, text: str) -> None:
        font = fmap()
        size = font_size
        x = tm[4]
        y = tm[5] + rise
        width_units = 500.0
        if font and cid in font.glyphs:
            width_units = font.glyphs[cid].width
        elif text == " ":
            width_units = 250.0
        w = (width_units / 1000.0) * size * horiz_scale
        extra = char_space * size * horiz_scale
        if text == " ":
            extra += word_space * size * horiz_scale
        if current is None:
            start_run()
        assert current is not None
        current.glyphs.append(
            Glyph(
                text=text,
                x=x,
                y=y,
                width=w,
                size=size,
                font=current.font,
                cid=cid,
                page=page_index,
                rtl_font=current.rtl_font,
            )
        )
        tm[4] += w + extra

    for operands, operator in _iter_operations(page):
        op = operator.decode("latin-1") if isinstance(operator, (bytes, bytearray)) else str(operator)
        if op == "BT":
            tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
            current = None
            continue
        if op == "ET":
            current = None
            continue
        if op == "Tf" and len(operands) >= 2:
            font_key = str(operands[0])
            font_size = _as_float(operands[1], font_size)
            current = None
            continue
        if op == "Tc" and operands:
            char_space = _as_float(operands[0])
            continue
        if op == "Tw" and operands:
            word_space = _as_float(operands[0])
            continue
        if op == "Tz" and operands:
            horiz_scale = _as_float(operands[0], 100.0) / 100.0
            continue
        if op == "Ts" and operands:
            rise = _as_float(operands[0])
            continue
        if op == "Tm" and len(operands) >= 6:
            tm = [_as_float(v) for v in operands[:6]]
            current = None
            continue
        if op in {"Td", "TD"} and len(operands) >= 2:
            tm[4] += _as_float(operands[0])
            tm[5] += _as_float(operands[1])
            current = None
            continue
        if op == "T*":
            tm[5] -= font_size * 1.2
            current = None
            continue
        if op in {"Tj", "'", '"'} and operands:
            if current is None:
                start_run()
            font = fmap()
            if font is None:
                continue
            for cid, text in _decode_string(operands[0], font):
                emit(cid, text)
            continue
        if op == "TJ" and operands:
            if current is None:
                start_run()
            font = fmap()
            if font is None:
                continue
            arr = operands[0]
            if not isinstance(arr, list):
                arr = [arr]
            for item in arr:
                if isinstance(item, (int, float)):
                    tm[4] -= (_as_float(item) / 1000.0) * font_size * horiz_scale
                    continue
                for cid, text in _decode_string(item, font):
                    emit(cid, text)
            continue
    return [run for run in runs if run.glyphs]


def extract_glyphs(page, page_index: int = 0) -> list[Glyph]:
    glyphs: list[Glyph] = []
    for run in extract_runs(page, page_index):
        glyphs.extend(run.glyphs)
    return glyphs


def extract_document_runs(reader) -> tuple[list[Run], dict[str, FontGlyphMap]]:
    all_runs: list[Run] = []
    all_maps: dict[str, FontGlyphMap] = {}
    for i, page in enumerate(reader.pages):
        maps = font_maps_from_page(page)
        for k, v in maps.items():
            all_maps[f"p{i}:{k}"] = v
        all_runs.extend(extract_runs(page, i))
    return all_runs, all_maps
