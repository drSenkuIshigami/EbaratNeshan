"""Optional page/figure rasterization for Markdown image embeds."""

from __future__ import annotations

from pathlib import Path

from .layout import Line


def render_page_png(pdf_path: str | Path, page_index: int, dest: Path, scale: float = 2.0) -> Path | None:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[page_index]
    bitmap = page.render(scale=scale)
    image = bitmap.to_pil()
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest


def _range_overlaps(y0: float, y1: float, skip_ranges: list[tuple[float, float]]) -> bool:
    lo, hi = min(y0, y1), max(y0, y1)
    for a, b in skip_ranges:
        sa, sb = min(a, b), max(a, b)
        if not (hi < sa or sb < lo):
            overlap = min(hi, sb) - max(lo, sa)
            if overlap > (hi - lo) * 0.35:
                return True
    return False


def figure_band(
    lines: list[Line],
    page_index: int,
    page_height: float = 842.0,
    skip_ranges: list[tuple[float, float]] | None = None,
) -> tuple[float, float] | None:
    page_lines = [ln for ln in lines if ln.page == page_index and not re_pageish(ln)]
    if len(page_lines) < 4:
        return None
    ordered = sorted(page_lines, key=lambda ln: -ln.y)
    best: tuple[float, float, float] | None = None
    for a, b in zip(ordered, ordered[1:]):
        gap = a.y - b.y
        mid = (a.y + b.y) / 2
        y0, y1 = b.y + 8, a.y - 8
        if y1 <= y0:
            continue
        if _range_overlaps(y0, y1, skip_ranges or []):
            continue
        if 80 < mid < page_height - 80 and (best is None or gap > best[0]):
            best = (gap, y0, y1)
    if best is None or best[0] < 70:
        return None
    return best[1], best[2]


def re_pageish(line: Line) -> bool:
    t = line.text.strip()
    return t.isdigit() and len(t) <= 4 and line.y < 90


def crop_figure_png(
    pdf_path: str | Path,
    page_index: int,
    y0: float,
    y1: float,
    page_height: float,
    dest: Path,
    scale: float = 2.0,
) -> Path | None:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[page_index]
    bitmap = page.render(scale=scale)
    image = bitmap.to_pil()
    w, h = image.size
    top = max(0, int((page_height - y1) / page_height * h))
    bot = min(h, int((page_height - y0) / page_height * h))
    if bot - top < 40:
        return None
    crop = image.crop((0, top, w, bot))
    dest.parent.mkdir(parents=True, exist_ok=True)
    crop.save(dest)
    return dest


def crop_region_png(
    pdf_path: str | Path,
    page_index: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    page_width: float,
    page_height: float,
    dest: Path,
    scale: float = 2.0,
    pad: float = 6.0,
) -> Path | None:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[page_index]
    bitmap = page.render(scale=scale)
    image = bitmap.to_pil()
    w, h = image.size
    left = max(0, int((x0 - pad) / page_width * w))
    right = min(w, int((x1 + pad) / page_width * w))
    top = max(0, int((page_height - y1 - pad) / page_height * h))
    bot = min(h, int((page_height - y0 + pad) / page_height * h))
    if right - left < 20 or bot - top < 20:
        return None
    crop = image.crop((left, top, right, bot))
    dest.parent.mkdir(parents=True, exist_ok=True)
    crop.save(dest)
    return dest
