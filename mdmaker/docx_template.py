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
