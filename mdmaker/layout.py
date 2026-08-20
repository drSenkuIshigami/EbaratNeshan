"""Turn positioned text runs into reading-order Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .arabic import clean_persian_text, rtl_ratio
from .headings import (
    atx,
    heading_level_from_size,
    is_noise_line,
    is_smashed_number,
    list_item,
    smashed_number_body,
)
from .pdf_glyphs import Run


@dataclass
class PlacedTable:
    page: int
    y: float
    markdown: str
    image_rel: str | None = None


@dataclass
class Line:
    y: float
    size: float
    text: str
    rtl: bool
    x0: float
    x1: float
    page: int
    sparse: bool = False


_NUM = re.compile(r"\d+")
_PUA_BULLETS = {
    "\uf0b7": "•",
    "\uf0a7": "•",
    "\u2022": "•",
}


def _fix_mixed_numbers(text: str) -> str:
    return _NUM.sub(lambda m: m.group(0)[::-1], text)


def _run_text(run: Run, reverse: bool) -> str:
    raw = run.text
    if len(raw) == 1 and raw in "اٱ" and (run.x1 - run.x) < max(2.0, run.size * 0.22):
        raw = "|"
    if reverse:
        raw = raw[::-1]
        raw = _fix_mixed_numbers(raw)
    for src, dst in _PUA_BULLETS.items():
        raw = raw.replace(src, dst)
    return raw


def _cluster_run_lines(runs: list[Run]) -> list[list[Run]]:
    if not runs:
        return []
    median_size = sorted(r.size for r in runs)[len(runs) // 2]
    tol = max(2.5, median_size * 0.45)
    ordered = sorted(runs, key=lambda r: (r.page, -r.y, r.x))
    lines: list[list[Run]] = []
    current: list[Run] = []
    current_y = None
    current_page = None
    for run in ordered:
        if current and (run.page != current_page or abs(run.y - (current_y or 0)) > tol):
            lines.append(current)
            current = []
        if not current:
            current_y = run.y
            current_page = run.page
        current.append(run)
    if current:
        lines.append(current)
    return lines


def _merge_close_runs(group: list[Run]) -> list[Run]:
    """Keep PDF text objects separate; sort left-to-right by origin."""
    return sorted(group, key=lambda r: r.x)


def line_from_runs(group: list[Run]) -> Line:
    group = _merge_close_runs(group)
    sample = "".join(r.text for r in group)
    rtl = rtl_ratio(clean_persian_text(sample)) >= 0.30 or (
        sum(1 for r in group if r.rtl_font) > len(group) / 2
    )
    pieces: list[str] = []
    ordered = list(reversed(group)) if rtl else group
    prev: Run | None = None
    for run in ordered:
        if prev is not None:
            if rtl:
                gap = prev.x - run.x1
            else:
                gap = run.x - prev.x1
            if gap > max(run.size, prev.size) * 0.35:
                pieces.append(" ")
        pieces.append(_run_text(run, reverse=rtl and run.rtl_font))
        prev = run
    text = clean_persian_text("".join(pieces))
    ordered = sorted(group, key=lambda r: r.x)
    sparse = False
    if len(ordered) >= 6 and len(text) < 48:
        gaps = [b.x - a.x1 for a, b in zip(ordered, ordered[1:])]
        if gaps:
            mid_gap = sorted(gaps)[len(gaps) // 2]
            sparse = mid_gap > group[0].size * 1.6
    return Line(
        y=sum(r.y for r in group) / len(group),
        size=max(r.size for r in group),
        text=text,
        rtl=rtl,
        x0=min(r.x for r in group),
        x1=max(r.x1 for r in group),
        page=group[0].page,
        sparse=sparse,
    )


def _keep_run(run: Run) -> bool:
    width = run.x1 - run.x
    text = run.text.replace("\x00", "")
    if text.strip():
        return True
    return width >= 1.0


def build_lines(runs: list[Run]) -> list[Line]:
    runs = [run for run in runs if _keep_run(run)]
    return [ln for ln in (line_from_runs(g) for g in _cluster_run_lines(runs)) if ln.text]


def drop_running_headers(lines: list[Line]) -> list[Line]:
    """Drop short lines that repeat on multiple pages in the header/footer band."""
    if len({ln.page for ln in lines}) < 2:
        return lines
    pages: dict[int, float] = {}
    counts: dict[str, set[int]] = {}
    for ln in lines:
        pages[ln.page] = max(pages.get(ln.page, 0.0), ln.y)
        key = ln.text.strip()
        if 6 <= len(key) <= 70:
            counts.setdefault(key, set()).add(ln.page)
    repeats = {key for key, seen in counts.items() if len(seen) >= 2}
    if not repeats:
        return lines
    kept: list[Line] = []
    for ln in lines:
        key = ln.text.strip()
        top = pages.get(ln.page, 842.0)
        header = ln.y > top - 55
        footer = ln.y < 85
        if key in repeats and (header or footer):
            continue
        kept.append(ln)
    return kept or lines


def _is_page_number(line: Line, page_height: float = 842.0) -> bool:
    digits = re.sub(r"\D", "", line.text)
    if not re.fullmatch(r"\d{1,4}", digits):
        return False
    if digits != line.text.strip() and len(line.text.strip()) > 6:
        return False
    return line.y < 90 or line.y > page_height - 80


def _is_caption(text: str) -> bool:
    return bool(re.match(r"^(شکل|جدول|نمودار|تصویر|Figure|Table|Chart)\b", text.strip()))


def _is_heading(line: Line, body_size: float) -> bool:
    return line.size >= body_size * 1.25 and len(line.text) < 90


def lines_to_markdown(
    lines: list[Line],
    title: str | None = None,
    purpose: str = "llm",
    tables: list[PlacedTable] | None = None,
) -> str:
    if not lines and not tables:
        return ""
    reading = purpose == "reading"
    sized = lines or []
    body_size = sorted(ln.size for ln in sized)[len(sized) // 2] if sized else 12.0
    rtl_doc = bool(sized) and sum(1 for ln in sized if ln.rtl) >= max(1, len(sized) // 3)
    rtl_doc = rtl_doc or bool(tables)
    chunks: list[str] = []
    if reading and rtl_doc:
        chunks.append('<div dir="rtl">')
        chunks.append("")

    events: list[tuple[str, int, float, object]] = []
    for ln in lines:
        events.append(("line", ln.page, ln.y, ln))
    for table in tables or []:
        events.append(("table", table.page, table.y, table))
    events.sort(key=lambda e: (e[1], -e[2]))

    para: list[str] = []
    prev: Line | None = None
    in_figure = False
    ol_n = 0

    def flush_para() -> None:
        nonlocal para
        if para:
            chunks.append(" ".join(para).strip())
            chunks.append("")
            para = []

    wrap_gap = max(body_size * 2.4, 36)

    for kind, _page, _y, payload in events:
        if kind == "table":
            flush_para()
            in_figure = False
            table = payload
            assert isinstance(table, PlacedTable)
            if table.image_rel:
                chunks.append(f"![Table]({table.image_rel})")
                chunks.append("")
            chunks.append(table.markdown)
            chunks.append("")
            prev = None
            continue
        ln = payload
        assert isinstance(ln, Line)
        if _is_page_number(ln):
            continue
        text = ln.text.strip()
        if not text or is_noise_line(text):
            continue
        level = heading_level_from_size(text, ln.size, body_size)
        if level:
            flush_para()
            in_figure = False
            ol_n = 0
            chunks.append(atx(level, text))
            chunks.append("")
            prev = ln
            continue
        if is_smashed_number(text):
            flush_para()
            in_figure = False
            ol_n += 1
            chunks.append(f"{ol_n}. {smashed_number_body(text)}")
            prev = ln
            continue
        item = list_item(text, ln.x0)
        if item:
            flush_para()
            in_figure = False
            chunks.append(item)
            prev = ln
            continue
        if ln.sparse:
            flush_para()
            if not in_figure:
                heading = "برچسب‌های شکل" if reading else "Figure labels (for the diagram)"
                chunks.append(f"**{heading}**" if reading else f"### {heading}")
                in_figure = True
            chunks.append(f"- {text}")
            prev = ln
            continue
        in_figure = False
        if _is_caption(text):
            flush_para()
            chunks.append(f"**{text}**")
            chunks.append("")
            prev = ln
            continue
        if text.startswith(("•", "●", "·")):
            flush_para()
            item = re.sub(r"^[•●·]\s*", "", text)
            chunks.append(f"- {item}")
            prev = ln
            continue
        if prev is not None and (
            prev.page != ln.page
            or abs(prev.size - ln.size) > 1.5
            or abs(prev.y - ln.y) > wrap_gap
        ):
            flush_para()
        para.append(text)
        prev = ln
    flush_para()

    if reading and rtl_doc:
        chunks.append("</div>")
    md = "\n".join(chunks).strip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", md)
