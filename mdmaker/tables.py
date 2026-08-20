"""Offline table recovery from PDF cell rectangles (Word-style grids)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .arabic import _fix_visual_delimiters
from .layout import build_lines
from .pdf_glyphs import Run, _as_float, _iter_operations


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def contains(self, x: float, y: float, pad: float = 1.0) -> bool:
        return self.x0 - pad <= x <= self.x1 + pad and self.y0 - pad <= y <= self.y1 + pad

    def overlaps(self, other: BBox, pad: float = 0.0) -> bool:
        return not (
            self.x1 + pad < other.x0
            or other.x1 + pad < self.x0
            or self.y1 + pad < other.y0
            or other.y1 + pad < self.y0
        )


@dataclass
class GridCell:
    box: BBox
    r0: int
    r1: int
    c0: int
    c1: int
    runs: list[Run] = field(default_factory=list)

    @property
    def text(self) -> str:
        if not self.runs:
            return ""
        return _fix_visual_delimiters(" ".join(ln.text for ln in build_lines(self.runs) if ln.text))


@dataclass
class DetectedTable:
    page: int
    box: BBox
    rows: list[list[str]]
    ncols: int
    nrows: int

    @property
    def y_top(self) -> float:
        return self.box.y1

    @property
    def y_bot(self) -> float:
        return self.box.y0


def _mul_ctm(m: list[float], n: list[float]) -> list[float]:
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return [
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    ]


def _apply(m: list[float], x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def extract_rects(page) -> list[BBox]:
    identity = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    ctm = identity[:]
    stack: list[list[float]] = []
    boxes: list[BBox] = []
    for operands, operator in _iter_operations(page):
        op = operator.decode("latin-1") if isinstance(operator, (bytes, bytearray)) else str(operator)
        if op == "q":
            stack.append(ctm[:])
        elif op == "Q" and stack:
            ctm = stack.pop()
        elif op == "cm" and len(operands) >= 6:
            ctm = _mul_ctm(ctm, [_as_float(v) for v in operands[:6]])
        elif op == "re" and len(operands) >= 4:
            x, y, w, h = (_as_float(v) for v in operands[:4])
            corners = [
                _apply(ctm, x, y),
                _apply(ctm, x + w, y),
                _apply(ctm, x, y + h),
                _apply(ctm, x + w, y + h),
            ]
            xs = [p[0] for p in corners]
            ys = [p[1] for p in corners]
            boxes.append(BBox(min(xs), min(ys), max(xs), max(ys)))
    return boxes


def _cluster_values(values: list[float], tol: float = 3.0) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    groups: list[list[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if abs(v - groups[-1][-1]) <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _snap(value: float, ticks: list[float]) -> int:
    best_i = 0
    best_d = abs(value - ticks[0])
    for i, tick in enumerate(ticks):
        d = abs(value - tick)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _unique_boxes(boxes: list[BBox], page_w: float, page_h: float) -> list[BBox]:
    kept: list[BBox] = []
    seen: set[tuple[int, int, int, int]] = set()
    for box in boxes:
        if box.width < 18 or box.height < 10:
            continue
        if box.width > page_w * 0.92 and box.height > page_h * 0.92:
            continue
        key = (round(box.x0, 1), round(box.y0, 1), round(box.x1, 1), round(box.y1, 1))
        if key in seen:
            continue
        seen.add(key)
        kept.append(box)
    return kept


def _clusters(boxes: list[BBox], pad: float = 8.0) -> list[list[BBox]]:
    n = len(boxes)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            if boxes[i].overlaps(boxes[j], pad=pad):
                union(i, j)
    groups: dict[int, list[BBox]] = {}
    for i, box in enumerate(boxes):
        groups.setdefault(find(i), []).append(box)
    return [g for g in groups.values() if len(g) >= 6]


def _cluster_extrema(values: list[float], tol: float = 6.0, pick: str = "min") -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    groups: list[list[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if abs(v - groups[-1][-1]) <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    if pick == "max":
        return [max(g) for g in groups]
    return [min(g) for g in groups]


def _near(value: float, ticks: list[float], tol: float = 2.5) -> bool:
    return any(abs(value - tick) <= tol for tick in ticks)


def _drop_contained(boxes: list[BBox], pad: float = 2.0) -> list[BBox]:
    kept: list[BBox] = []
    for box in boxes:
        contained = False
        for other in boxes:
            if other.area <= box.area:
                continue
            if (
                other.x0 <= box.x0 + pad
                and other.y0 <= box.y0 + pad
                and other.x1 >= box.x1 - pad
                and other.y1 >= box.y1 - pad
            ):
                contained = True
                break
        if not contained:
            kept.append(box)
    return kept


def _cell_boxes(boxes: list[BBox]) -> list[BBox]:
    """Keep outer Word cell rects; drop inset fills and wrapped-line bands."""
    if len(boxes) < 6:
        return []
    lefts = _cluster_extrema([b.x0 for b in boxes], tol=6.0, pick="min")
    rights = _cluster_extrema([b.x1 for b in boxes], tol=6.0, pick="max")
    if len(lefts) < 2 or len(rights) < 2:
        return []
    aligned = [b for b in boxes if _near(b.x0, lefts) and _near(b.x1, rights)]
    return _drop_contained(aligned)


def _build_table(boxes: list[BBox], runs: list[Run], page_index: int) -> DetectedTable | None:
    cells_boxes = _cell_boxes(boxes)
    if len(cells_boxes) < 6:
        return None
    xs = _cluster_values([b.x0 for b in cells_boxes] + [b.x1 for b in cells_boxes], tol=4.0)
    ys = _cluster_values([b.y0 for b in cells_boxes] + [b.y1 for b in cells_boxes], tol=4.0)
    if len(xs) < 3 or len(ys) < 3:
        return None
    ncols = len(xs) - 1
    nrows = len(ys) - 1
    if ncols < 2 or nrows < 2:
        return None

    cells: list[GridCell] = []
    for box in cells_boxes:
        c0 = min(_snap(box.x0, xs), ncols - 1)
        c1 = max(_snap(box.x1, xs), c0 + 1)
        # ys are ascending (bottom to top); grid row 0 is the top of the table.
        bottom = _snap(box.y0, ys)
        top = _snap(box.y1, ys)
        r0 = max(0, nrows - top)
        r1 = min(nrows, nrows - bottom)
        if r1 <= r0:
            r1 = r0 + 1
        if c1 <= c0:
            c1 = c0 + 1
        cells.append(GridCell(box=box, r0=r0, r1=min(r1, nrows), c0=c0, c1=min(c1, ncols)))

    for run in runs:
        px = (run.x + run.x1) / 2
        py = run.y + run.size * 0.25
        hits = [cell for cell in cells if cell.box.contains(px, py, pad=4.0)]
        if not hits:
            continue
        pick = min(hits, key=lambda c: c.box.area)
        pick.runs.append(run)

    matrix = [[""] * ncols for _ in range(nrows)]
    for row in range(nrows):
        for col in range(ncols):
            covering = [c for c in cells if c.r0 <= row < c.r1 and c.c0 <= col < c.c1]
            if not covering:
                continue
            pick = min(covering, key=lambda c: c.box.area)
            matrix[row][col] = pick.text

    nonempty = sum(1 for row in matrix for val in row if val.strip())
    slots = nrows * ncols
    if nonempty < 4:
        return None
    if nonempty / slots < 0.25:
        return None
    if len(cells_boxes) < max(6, slots * 0.45):
        return None
    x0_hits = Counter(round(b.x0) for b in cells_boxes)
    if max(x0_hits.values()) < min(3, nrows):
        return None

    # Logical RTL: rightmost PDF column first.
    logical = [list(reversed(row)) for row in matrix]
    region = BBox(
        min(b.x0 for b in cells_boxes),
        min(b.y0 for b in cells_boxes),
        max(b.x1 for b in cells_boxes),
        max(b.y1 for b in cells_boxes),
    )
    return DetectedTable(page=page_index, box=region, rows=logical, ncols=ncols, nrows=nrows)


def detect_tables(page, runs: list[Run], page_index: int = 0) -> list[DetectedTable]:
    mediabox = page.mediabox
    page_w = float(mediabox.width)
    page_h = float(mediabox.height)
    boxes = _unique_boxes(extract_rects(page), page_w, page_h)
    tables: list[DetectedTable] = []
    for group in _clusters(boxes):
        table = _build_table(group, runs, page_index)
        if table is not None:
            tables.append(table)
    tables.sort(key=lambda t: -t.y_top)
    return tables


def detect_document_tables(reader, runs: list[Run]) -> list[DetectedTable]:
    by_page: dict[int, list[Run]] = {}
    for run in runs:
        by_page.setdefault(run.page, []).append(run)
    tables: list[DetectedTable] = []
    for i, page in enumerate(reader.pages):
        tables.extend(detect_tables(page, by_page.get(i, []), i))
    return tables


def run_in_tables(run: Run, tables: list[DetectedTable]) -> bool:
    for table in tables:
        if run.page == table.page and table.box.contains(run.x, run.y, pad=3.0):
            return True
    return False


def _escape_cell(text: str) -> str:
    return text.replace("\x00", "").replace("|", "\\|").replace("\n", " ").strip()


def rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    cleaned = [[_escape_cell(c) for c in row] for row in rows]
    width = max(len(row) for row in cleaned)
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    header = padded[0]
    body = padded[1:] or [[""] * width]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def table_to_markdown(table: DetectedTable) -> str:
    return rows_to_markdown(table.rows)
