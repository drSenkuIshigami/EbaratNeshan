"""Convert documents to LLM-ready Markdown with recovered RTL glyph maps."""

from __future__ import annotations

import shutil
from pathlib import Path

from pypdf import PdfReader

from .figures import crop_figure_png, crop_region_png, figure_band
from .glyphmap import FontGlyphMap
from .headings import atx, heading_level_from_style, heading_level_from_text, list_item, looks_numbered
from .layout import PlacedTable, build_lines, drop_running_headers, lines_to_markdown
from .pdf_glyphs import extract_document_runs
from .tables import detect_document_tables, rows_to_markdown, run_in_tables, table_to_markdown


class ConversionResult:
    def __init__(self, markdown: str, maps: dict[str, FontGlyphMap], warnings: list[str]):
        self.markdown = markdown
        self.maps = maps
        self.warnings = warnings

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.markdown, encoding="utf-8")
        return out


def convert_pdf(
    path: str | Path,
    title: str | None = None,
    asset_dir: str | Path | None = None,
    purpose: str = "llm",
    images_rel: str = "assets",
    table_images: bool = True,
    figure_images: bool = True,
) -> ConversionResult:
    jobs = {}
    if asset_dir is not None:
        jobs[purpose] = Path(asset_dir)
    bundle = convert_pdf_purposes(
        path,
        title=title,
        jobs=jobs,
        images_rel=images_rel,
        table_images=table_images,
        figure_images=figure_images,
    )
    markdown = bundle["texts"].get(purpose, "")
    return ConversionResult(markdown, bundle["maps"], bundle["warnings"])


def convert_pdf_purposes(
    path: str | Path,
    title: str | None = None,
    jobs: dict[str, Path] | None = None,
    images_rel: str = "assets",
    table_images: bool = True,
    figure_images: bool = True,
) -> dict:
    """Parse the PDF once; copy figures into each purpose's assets folder."""
    pdf_path = Path(path)
    reader = PdfReader(str(pdf_path))
    runs, maps = extract_document_runs(reader)
    tables = detect_document_tables(reader, runs)
    body_runs = [run for run in runs if not run_in_tables(run, tables)]
    lines = drop_running_headers(build_lines(body_runs))
    warnings: list[str] = _font_warnings(maps)
    md_title = None
    jobs = jobs or {}
    purposes = tuple(jobs) or ("llm", "reading")
    figure_names: list[str] = []
    table_names: list[str] = []
    first_dir: Path | None = None
    exported = False
    for purpose in purposes:
        assets = jobs.get(purpose)
        if assets is None:
            continue
        assets.mkdir(parents=True, exist_ok=True)
        if not exported:
            if figure_images:
                figure_names = _export_figures(pdf_path, reader, lines, tables, assets, warnings)
            if table_images:
                table_names = _export_tables(pdf_path, reader, tables, assets, warnings)
            first_dir = assets
            exported = True
        elif first_dir is not None and assets.resolve() != first_dir.resolve():
            for name in figure_names + table_names:
                shutil.copy2(first_dir / name, assets / name)
            copied = len(figure_names) + len(table_names)
            if copied:
                warnings.append(f"Copied {copied} image(s) into {assets}")
    figure_rels = [f"{images_rel}/{name}" for name in figure_names] if figure_images else []
    placed = _placed_tables(tables, table_names, images_rel, table_images)
    texts: dict[str, str] = {}
    for purpose in purposes:
        markdown = lines_to_markdown(lines, title=md_title, purpose=purpose, tables=placed)
        markdown = _insert_figure_links(markdown, figure_rels, purpose)
        if not markdown.strip():
            warnings.append(f"No text glyphs were decoded ({purpose}).")
        texts[purpose] = markdown
    if tables:
        warnings.append(f"Reconstructed {len(tables)} table(s) as Markdown")
    return {
        "texts": texts,
        "maps": maps,
        "warnings": warnings,
        "figure_names": figure_names,
        "table_names": table_names,
        "table_count": len(tables),
    }


def _font_warnings(maps) -> list[str]:
    warnings: list[str] = []
    for fmap in maps.values():
        if fmap.broken_tounicode:
            warnings.append(
                f"{fmap.name}: ignored broken ToUnicode CMap; used embedded font glyph map ({fmap.method})"
            )
        unnamed = [g for g in fmap.glyphs.values() if g.unicode is None and g.name not in {".notdef", ".null"}]
        used_identity = fmap.identity and fmap.glyphs and sum(1 for g in fmap.glyphs.values() if g.unicode) / len(fmap.glyphs) < 0.4
        if unnamed and used_identity and "Symbol" not in fmap.name:
            warnings.append(f"{fmap.name}: {len(unnamed)} glyphs still unmapped")
    return warnings


def _export_figures(pdf_path, reader, lines, tables, asset_dir: Path, warnings: list[str]) -> list[str]:
    skip_by_page: dict[int, list[tuple[float, float]]] = {}
    for table in tables:
        skip_by_page.setdefault(table.page, []).append((table.box.y0, table.box.y1))
    names: list[str] = []
    for page_index, page in enumerate(reader.pages):
        try:
            page_height = float(page.mediabox.height)
        except Exception:
            page_height = 842.0
        band = figure_band(lines, page_index, page_height, skip_ranges=skip_by_page.get(page_index, []))
        if band is None:
            continue
        dest = asset_dir / f"page-{page_index + 1:02d}-figure.png"
        saved = crop_figure_png(pdf_path, page_index, band[0], band[1], page_height, dest)
        if saved is None:
            warnings.append("pypdfium2 is missing; figure image was skipped.")
            break
        names.append(saved.name)
    if names:
        warnings.append(f"Saved {len(names)} figure image(s) under {asset_dir}")
    return names


def _table_image_names(tables) -> list[str]:
    counts: dict[int, int] = {}
    names: list[str] = []
    for table in tables:
        counts[table.page] = counts.get(table.page, 0) + 1
        n = counts[table.page]
        suffix = "" if n == 1 else str(n)
        names.append(f"page-{table.page + 1:02d}-table{suffix}.png")
    return names


def _export_tables(pdf_path, reader, tables, asset_dir: Path, warnings: list[str]) -> list[str]:
    names = _table_image_names(tables)
    saved_names: list[str] = []
    for table, name in zip(tables, names):
        page = reader.pages[table.page]
        page_w = float(page.mediabox.width)
        page_h = float(page.mediabox.height)
        dest = asset_dir / name
        saved = crop_region_png(
            pdf_path,
            table.page,
            table.box.x0,
            table.box.y0,
            table.box.x1,
            table.box.y1,
            page_w,
            page_h,
            dest,
        )
        if saved is None:
            warnings.append("pypdfium2 is missing; table image was skipped.")
            break
        saved_names.append(saved.name)
    if saved_names:
        warnings.append(f"Saved {len(saved_names)} table image(s) under {asset_dir}")
    return saved_names


def _placed_tables(
    tables, table_names: list[str], images_rel: str, table_images: bool = True
) -> list[PlacedTable]:
    placed: list[PlacedTable] = []
    for i, table in enumerate(tables):
        rel = None
        if table_images and i < len(table_names):
            rel = f"{images_rel}/{table_names[i]}"
        placed.append(
            PlacedTable(
                page=table.page,
                y=table.y_top,
                markdown=table_to_markdown(table),
                image_rel=rel,
            )
        )
    return placed


def _insert_figure_links(markdown: str, figure_rels: list[str], purpose: str) -> str:
    for i, rel in enumerate(figure_rels):
        alt = f"Figure page {i + 1}"
        if purpose == "llm":
            image_md = f"\n![{alt}]({rel})\n\n_Diagram image (Markdown has no native shapes; use this image or the labels above.)_\n"
        else:
            image_md = f"\n![{alt}]({rel})\n"
        needle = "**شکل"
        if needle in markdown:
            markdown = markdown.replace(needle, image_md + "\n" + needle, 1)
        elif "</div>" in markdown:
            markdown = markdown.replace("</div>", image_md + "\n</div>", 1)
        else:
            markdown = markdown.rstrip() + "\n" + image_md + "\n"
    return markdown


def convert_docx(
    path: str | Path,
    title: str | None = None,
    purpose: str = "llm",
    asset_dir: str | Path | None = None,
    images_rel: str = "assets",
) -> ConversionResult:
    try:
        import docx  # type: ignore
        from docx.oxml.ns import qn  # type: ignore
        from docx.table import Table  # type: ignore
        from docx.text.paragraph import Paragraph  # type: ignore
    except ImportError as exc:
        raise RuntimeError("python-docx is required for Word files") from exc
    src = Path(path)
    document = docx.Document(str(src))
    parts: list[str] = []
    rtl = False
    saved_images: list[str] = []
    assets = Path(asset_dir) if asset_dir is not None else None
    if assets is not None:
        assets.mkdir(parents=True, exist_ok=True)
    ol_n = 0

    def note_rtl(text: str) -> None:
        nonlocal rtl
        if any("\u0600" <= ch <= "\u06FF" for ch in text):
            rtl = True

    def _ppr(para):
        return para._p.find(qn("w:pPr"))

    def _outline_level(para) -> int | None:
        pPr = _ppr(para)
        if pPr is None:
            return None
        ol = pPr.find(qn("w:outlineLvl"))
        if ol is None or ol.get(qn("w:val")) is None:
            return None
        return int(ol.get(qn("w:val"))) + 1

    def _num_ilvl(para) -> int | None:
        pPr = _ppr(para)
        if pPr is None:
            return None
        np = pPr.find(qn("w:numPr"))
        if np is None:
            return None
        ilvl = np.find(qn("w:ilvl"))
        if ilvl is None or ilvl.get(qn("w:val")) is None:
            return 0
        return int(ilvl.get(qn("w:val")))

    def emit_paragraph(para) -> None:
        nonlocal ol_n
        raw = para.text.strip()
        for rel in _save_docx_blips(para, document, assets, images_rel, saved_images):
            parts.append(f"![image]({rel})")
            parts.append("")
        if not raw:
            return
        note_rtl(raw)
        style = (para.style.name or "") if para.style is not None else ""
        level = heading_level_from_style(style)
        if level is None:
            level = _outline_level(para)
        if level is None:
            level = heading_level_from_text(raw)
        if level:
            ol_n = 0
            parts.append(atx(level, raw))
            parts.append("")
            return
        ilvl = _num_ilvl(para)
        if ilvl is not None:
            chunks = [c.strip() for c in raw.splitlines() if c.strip()]
            numbered = any(looks_numbered(c) for c in chunks)
            for chunk in chunks:
                mapped = list_item(chunk)
                if mapped:
                    parts.append(mapped)
                elif numbered:
                    if ilvl == 0:
                        ol_n += 1
                        parts.append(f"{ol_n}. {chunk}")
                    else:
                        parts.append(("  " * ilvl) + f"{ilvl + 1}. {chunk}")
                else:
                    parts.append(("  " * ilvl) + "- " + chunk)
            parts.append("")
            return
        if "List" in style:
            parts.append(f"- {raw}")
            parts.append("")
            return
        parts.append(_runs_to_markdown(para) or raw)
        parts.append("")

    def emit_table(table) -> None:
        rows: list[list[str]] = []
        for row in table.rows:
            cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
            for cell_text in cells:
                note_rtl(cell_text)
            rows.append(cells)
        md = rows_to_markdown(rows)
        if md:
            parts.append(md.rstrip())
            parts.append("")

    for child in document.element.body:
        if child.tag == qn("w:p"):
            emit_paragraph(Paragraph(child, document))
        elif child.tag == qn("w:tbl"):
            emit_table(Table(child, document))

    markdown = "\n".join(parts).strip() + "\n"
    if rtl and purpose == "reading":
        markdown = f'<div dir="rtl">\n\n{markdown}\n</div>\n'
    warnings = []
    if saved_images:
        warnings.append(f"Saved {len(saved_images)} Word image(s)")
    return ConversionResult(markdown, {}, warnings)


_A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def _runs_to_markdown(para) -> str:
    bits: list[str] = []
    for run in para.runs:
        text = (run.text or "").replace("\n", " ")
        if not text:
            continue
        if run.bold and run.italic:
            bits.append(f"***{text}***")
        elif run.bold:
            bits.append(f"**{text}**")
        elif run.italic:
            bits.append(f"*{text}*")
        else:
            bits.append(text)
    return "".join(bits).strip()


def _save_docx_blips(para, document, assets: Path | None, images_rel: str, saved: list[str]) -> list[str]:
    if assets is None:
        return []
    rels: list[str] = []
    for blip in para._p.iter(_A_BLIP):
        embed = blip.get(_R_EMBED)
        if not embed:
            continue
        try:
            part = document.part.related_parts[embed]
        except Exception:
            continue
        blob = part.blob
        ext = Path(part.partname).suffix.lower() or ".png"
        if ext not in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".wmf", ".emf"}:
            ext = ".png"
        name = f"image-{len(saved) + 1:02d}{ext}"
        dest = assets / name
        dest.write_bytes(blob)
        saved.append(name)
        rels.append(f"{images_rel}/{name}")
    return rels


def convert(
    path: str | Path,
    title: str | None = None,
    asset_dir: str | Path | None = None,
    purpose: str = "llm",
    images_rel: str = "assets",
    table_images: bool = True,
    figure_images: bool = True,
) -> ConversionResult:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return convert_pdf(
            path,
            title=title,
            asset_dir=asset_dir,
            purpose=purpose,
            images_rel=images_rel,
            table_images=table_images,
            figure_images=figure_images,
        )
    if suffix == ".docx":
        return convert_docx(
            path, title=title, purpose=purpose, asset_dir=asset_dir, images_rel=images_rel
        )
    if suffix == ".doc":
        raise RuntimeError(".doc (Word 97-2003) support is next; convert to .docx or PDF for now.")
    raise RuntimeError(f"Unsupported file type: {suffix}")


def convert_both(
    path: str | Path,
    title: str | None = None,
    jobs: dict[str, Path] | None = None,
    images_rel: str = "assets",
    purposes: tuple[str, ...] | None = None,
    table_images: bool = True,
    figure_images: bool = True,
) -> dict:
    suffix = Path(path).suffix.lower()
    wanted = tuple(purposes or (jobs or {"llm": None, "reading": None}))
    if suffix == ".pdf":
        asset_jobs = {p: Path(d) for p, d in (jobs or {}).items()}
        bundle = convert_pdf_purposes(
            path,
            title=title,
            jobs=asset_jobs,
            images_rel=images_rel,
            table_images=table_images,
            figure_images=figure_images,
        )
        return {
            "texts": {p: bundle["texts"][p] for p in wanted if p in bundle["texts"]},
            "maps": bundle["maps"],
            "warnings": bundle["warnings"],
            "table_count": bundle.get("table_count", 0),
            "figure_names": bundle.get("figure_names", []),
            "table_names": bundle.get("table_names", []),
        }
    if suffix == ".docx":
        texts: dict[str, str] = {}
        warnings: list[str] = []
        figure_names: list[str] = []
        first_dir: Path | None = None
        for purpose in wanted:
            assets = Path(jobs[purpose]) if jobs and purpose in jobs else None
            if assets is not None:
                assets.mkdir(parents=True, exist_ok=True)
            result = convert_docx(
                path,
                title=title,
                purpose=purpose,
                asset_dir=assets,
                images_rel=images_rel,
            )
            texts[purpose] = result.markdown
            warnings.extend(result.warnings)
            if assets is not None and not figure_names:
                figure_names = sorted(p.name for p in assets.glob("image-*"))
                first_dir = assets
            elif (
                first_dir is not None
                and assets is not None
                and assets.resolve() != first_dir.resolve()
            ):
                for name in figure_names:
                    shutil.copy2(first_dir / name, assets / name)
        return {
            "texts": texts,
            "maps": {},
            "warnings": warnings,
            "table_count": 0,
            "figure_names": figure_names,
            "table_names": [],
        }
    if suffix == ".doc":
        raise RuntimeError(".doc (Word 97-2003) support is next; convert to .docx or PDF for now.")
    raise RuntimeError(f"Unsupported file type: {suffix}")
