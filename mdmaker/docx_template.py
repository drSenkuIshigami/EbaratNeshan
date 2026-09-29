"""Use an existing Word file as the shell for Markdown → DOCX export."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

# Preferred style names (first match wins). Tuned for Iranian thesis templates
# like "MSc Thesis Template" while still working on plain Word defaults.
DEFAULT_STYLE_MAP: dict[str, list[str]] = {
    "title": ["Title2", "Title", "عنوان1", "سرعنوان"],
    "h1": ["سرعنوان اصلی(1)", "Heading 1", "عنوان1"],
    "h2": ["سرعنوان فرعی(Heading2)", "هدینگ2", "Heading 2", "head 2"],
    "h3": ["هدینگ 3", "Heading 3"],
    "h4": ["Heading 4"],
    "h5": ["Heading 5"],
    "h6": ["Heading 6"],
    "p": ["Body Text,متن پایان نامه", "Body Text", "متن", "matn", "MATN", "Normal"],
    "p_cont": ["Body Text First Indent", "Body Text,متن پایان نامه", "Body Text", "متن", "Normal"],
    "quote": ["Block Quote", "Quote", "Intense Quote"],
    "caption": ["Cap_figure", "Caption"],
    "list_bullet": ["List Paragraph", "List Bullet", "Normal"],
    "list_number": ["List Number", "List Paragraph", "Normal"],
    "pre": ["HTML Preformatted", "No Spacing", "Normal"],
    "table": ["Table Grid", "Table Normal"],
    "table_text": ["table_content", "Body Text,متن پایان نامه", "Normal"],
}


def ensure_docx_template(path: str | Path) -> Path:
    """Return a .docx path; convert legacy .doc via Word when needed."""
    src = Path(path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Word template not found: {src}")
    suffix = src.suffix.lower()
    if suffix == ".docx":
        return src
    if suffix != ".doc":
        raise ValueError("Word template must be .docx or .doc")
    return _convert_doc_to_docx(src)


def open_template_document(path: str | Path):
    """Copy template, clear body text, keep sections/headers/footers/styles."""
    import os
    from docx import Document

    template = ensure_docx_template(path)
    fd, name = tempfile.mkstemp(prefix="ebarat-tpl-", suffix=".docx")
    os.close(fd)
    tmp = Path(name)
    shutil.copy2(template, tmp)
    doc = Document(str(tmp))
    clear_document_body(doc)
    return doc, tmp


def clear_document_body(document) -> None:
    """Remove body content but keep the final sectPr (margins/headers)."""
    from docx.oxml.ns import qn

    body = document.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def build_style_resolver(document, style_map: dict[str, list[str]] | None = None):
    """Return callable role -> best available style name (or None)."""
    available = {}
    for style in document.styles:
        try:
            name = style.name
        except Exception:
            continue
        if name:
            available[name] = name
            available[name.lower()] = name

    mapping = style_map or DEFAULT_STYLE_MAP

    def resolve(role: str) -> str | None:
        for candidate in mapping.get(role, []):
            if candidate in available:
                return available[candidate]
            low = candidate.lower()
            if low in available:
                return available[low]
            # Aliased Word styles often look like "Body Text,متن پایان نامه"
            for name, canon in available.items():
                if candidate in name:
                    return canon
        return None

    return resolve


def apply_paragraph_style(paragraph, style_name: str | None) -> None:
    if not style_name:
        return
    try:
        paragraph.style = style_name
    except Exception:
        try:
            paragraph.style = paragraph.part.document.styles[style_name]
        except Exception:
            pass


def inspect_template_styles(path: str | Path) -> dict:
    """Return paragraph styles from a Word template for a gallery preview."""
    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn

    docx_path = ensure_docx_template(path)
    document = Document(str(docx_path))
    resolve = build_style_resolver(document)
    mapped = {role: resolve(role) for role in DEFAULT_STYLE_MAP}
    mapped_names = {name for name in mapped.values() if name}

    align_map = {
        WD_ALIGN_PARAGRAPH.LEFT: "left",
        WD_ALIGN_PARAGRAPH.CENTER: "center",
        WD_ALIGN_PARAGRAPH.RIGHT: "right",
        WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
    }

    def style_chain(style):
        seen: set[int] = set()
        cur = style
        while cur is not None and id(cur) not in seen:
            yield cur
            seen.add(id(cur))
            try:
                cur = cur.base_style
            except Exception:
                break

    def first(style, getter):
        for item in style_chain(style):
            try:
                value = getter(item)
            except Exception:
                value = None
            if value is not None and value != "":
                return value
        return None

    def run_props(style):
        ascii_name = None
        cs_name = None
        size_pt = None
        size_cs_pt = None
        bold = None
        italic = None
        for item in style_chain(style):
            r_pr = item.element.find(qn("w:rPr"))
            if r_pr is None:
                continue
            fonts = r_pr.find(qn("w:rFonts"))
            if fonts is not None:
                if ascii_name is None:
                    ascii_name = fonts.get(qn("w:ascii")) or fonts.get(qn("w:hAnsi"))
                if cs_name is None:
                    cs_name = fonts.get(qn("w:cs"))
            if size_pt is None:
                sz = r_pr.find(qn("w:sz"))
                if sz is not None and sz.get(qn("w:val")):
                    size_pt = int(sz.get(qn("w:val"))) / 2
            if size_cs_pt is None:
                sz_cs = r_pr.find(qn("w:szCs"))
                if sz_cs is not None and sz_cs.get(qn("w:val")):
                    size_cs_pt = int(sz_cs.get(qn("w:val"))) / 2
            if bold is None and (
                r_pr.find(qn("w:b")) is not None or r_pr.find(qn("w:bCs")) is not None
            ):
                bold = True
            if italic is None and (
                r_pr.find(qn("w:i")) is not None or r_pr.find(qn("w:iCs")) is not None
            ):
                italic = True
        if ascii_name is None:
            ascii_name = first(style, lambda s: s.font.name)
        if size_pt is None:
            size = first(style, lambda s: s.font.size)
            if size is not None:
                size_pt = float(size.pt)
        if bold is None:
            bold = first(style, lambda s: s.font.bold)
        if italic is None:
            italic = first(style, lambda s: s.font.italic)
        return {
            "font": ascii_name,
            "font_cs": cs_name,
            "size_pt": size_pt,
            "size_cs_pt": size_cs_pt,
            "bold": bool(bold) if bold is not None else False,
            "italic": bool(italic) if italic is not None else False,
        }

    def para_props(style):
        alignment = first(style, lambda s: s.paragraph_format.alignment)
        rtl = False
        for item in style_chain(style):
            p_pr = item.element.find(qn("w:pPr"))
            if p_pr is not None and p_pr.find(qn("w:bidi")) is not None:
                rtl = True
                break
        space_before = first(style, lambda s: s.paragraph_format.space_before)
        space_after = first(style, lambda s: s.paragraph_format.space_after)
        return {
            "align": align_map.get(alignment) if alignment is not None else None,
            "rtl": rtl,
            "space_before_pt": float(space_before.pt) if space_before is not None else None,
            "space_after_pt": float(space_after.pt) if space_after is not None else None,
        }

    styles = []
    for style in document.styles:
        try:
            if style.type != WD_STYLE_TYPE.PARAGRAPH:
                continue
            name = style.name
        except Exception:
            continue
        if not name:
            continue
        try:
            if style.hidden:
                continue
        except Exception:
            pass
        base = None
        try:
            base = style.base_style.name if style.base_style is not None else None
        except Exception:
            base = None
        props = {**run_props(style), **para_props(style)}
        styles.append(
            {
                "name": name,
                "base": base,
                "mapped": name in mapped_names,
                **props,
            }
        )

    styles.sort(key=lambda item: (not item["mapped"], item["name"].lower()))
    return {
        "file": Path(path).name,
        "docx": docx_path.name,
        "count": len(styles),
        "mapped": {role: name for role, name in mapped.items() if name},
        "styles": styles,
    }


def _convert_doc_to_docx(src: Path) -> Path:
    import os
    import time

    try:
        import win32com.client as win32  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Legacy .doc templates need Microsoft Word + pywin32, or save the template as .docx."
        ) from exc

    cache = src.with_name(src.stem + ".ebarat-template.docx")
    try:
        if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime and cache.stat().st_size > 1000:
            return cache
    except OSError:
        pass

    fd, name = tempfile.mkstemp(prefix="ebarat-tpl-conv-", suffix=".docx")
    os.close(fd)
    out = Path(name)
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = None
    try:
        # Positional args for late-bound Word COM.
        doc = word.Documents.Open(str(src), False, True)
        save = getattr(doc, "SaveAs2", None) or doc.SaveAs
        save(str(out), 16)
        doc.Close(False)
        doc = None
    finally:
        try:
            if doc is not None:
                doc.Close(False)
        except Exception:
            pass
        try:
            word.Quit()
        except Exception:
            pass
        time.sleep(0.3)
    if not out.is_file() or out.stat().st_size < 1000:
        raise RuntimeError(f"Failed to convert template to .docx: {src}")
    try:
        shutil.copy2(out, cache)
        return cache
    except OSError:
        return out
