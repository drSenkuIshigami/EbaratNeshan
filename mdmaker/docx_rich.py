"""Extra DOCX → Markdown extraction: notes, headers/footers, page setup, bibliography cues."""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

from docx.opc.constants import RELATIONSHIP_TYPE as RT

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_REF_STYLE = re.compile(
    r"(bibentr|bibliograph|reference|مراجع|منابع|فهرست\s*منابع)",
    re.I,
)
_REF_HEADING = re.compile(
    r"^(مراجع|منابع|فهرست\s*منابع|references|bibliography|works\s+cited)\b",
    re.I,
)


def extract_docx_extras(document) -> dict[str, Any]:
    """Collect Word structures that plain body walk misses."""
    footnotes = _load_notes(document, RT.FOOTNOTES, "footnote")
    endnotes = _load_notes(document, RT.ENDNOTES, "endnote")
    page = _page_setup(document)
    headers, footers = _headers_footers(document)
    return {
        "footnotes": footnotes,
        "endnotes": endnotes,
        "page": page,
        "headers": headers,
        "footers": footers,
    }


def paragraph_to_markdown(para) -> str:
    """Runs plus footnote/endnote markers as Markdown references."""
    from docx.oxml.ns import qn

    bits: list[str] = []
    for run in para.runs:
        r_el = run._r
        fn = r_el.find(qn("w:footnoteReference"))
        if fn is not None:
            nid = fn.get(qn("w:val")) or fn.get(qn("w:id"))
            if nid is not None:
                bits.append(f"[^{nid}]")
            continue
        en = r_el.find(qn("w:endnoteReference"))
        if en is not None:
            nid = en.get(qn("w:val")) or en.get(qn("w:id"))
            if nid is not None:
                bits.append(f"[^e{nid}]")
            continue
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


def is_bibliography_style(style_name: str) -> bool:
    return bool(style_name and _REF_STYLE.search(style_name))


def is_bibliography_heading(text: str) -> bool:
    return bool(text and _REF_HEADING.match(text.strip()))


def format_notes_markdown(
    footnotes: dict[int, str],
    endnotes: dict[int, str],
    *,
    rtl: bool,
) -> str:
    chunks: list[str] = []
    if footnotes:
        title = "پاورقی‌ها" if rtl else "Footnotes"
        chunks.append(f"## {title}")
        chunks.append("")
        for nid in sorted(footnotes):
            chunks.append(f"[^{nid}]: {footnotes[nid]}")
        chunks.append("")
    if endnotes:
        title = "پی‌نوشت‌ها" if rtl else "Endnotes"
        chunks.append(f"## {title}")
        chunks.append("")
        for nid in sorted(endnotes):
            chunks.append(f"[^e{nid}]: {endnotes[nid]}")
        chunks.append("")
    return "\n".join(chunks)


def format_chrome_markdown(
    headers: dict[str, str],
    footers: dict[str, str],
    *,
    rtl: bool,
) -> str:
    """Optional appendix appendix dump of header/footer text for archival Markdown."""
    if not any(headers.values()) and not any(footers.values()):
        return ""
    chunks: list[str] = []
    h_title = "سربرگ" if rtl else "Headers"
    f_title = "پاورقی صفحه" if rtl else "Footers"
    if any(headers.values()):
        chunks.append(f"## {h_title}")
        chunks.append("")
        for key, text in headers.items():
            if text:
                chunks.append(f"- **{key}:** {text}")
        chunks.append("")
    if any(footers.values()):
        chunks.append(f"## {f_title}")
        chunks.append("")
        for key, text in footers.items():
            if text:
                chunks.append(f"- **{key}:** {text}")
        chunks.append("")
    return "\n".join(chunks)


def page_meta_for_yaml(page: dict[str, Any]) -> dict[str, Any]:
    """Flatten page setup into YAML-friendly scalars."""
    out: dict[str, Any] = {}
    if not page:
        return out
    for key in (
        "page_width_cm",
        "page_height_cm",
        "orientation",
        "margin_top_cm",
        "margin_bottom_cm",
        "margin_left_cm",
        "margin_right_cm",
        "gutter_cm",
        "header_distance_cm",
        "footer_distance_cm",
        "different_first_page_header_footer",
    ):
        if key in page and page[key] is not None:
            out[key] = page[key]
    if page.get("header_default"):
        out["header"] = page["header_default"]
    if page.get("footer_default"):
        out["footer"] = page["footer_default"]
    if page.get("footnote_count"):
        out["footnotes"] = page["footnote_count"]
    if page.get("endnote_count"):
        out["endnotes"] = page["endnote_count"]
    return out


def _load_notes(document, reltype: str, tag: str) -> dict[int, str]:
    part = _related_part(document, reltype)
    if part is None:
        return {}
    try:
        root = ET.fromstring(part.blob)
    except Exception:
        return {}
    notes: dict[int, str] = {}
    for el in root:
        if el.tag != f"{W}{tag}":
            continue
        typ = el.get(f"{W}type")
        if typ in {"separator", "continuationSeparator"}:
            continue
        raw_id = el.get(f"{W}id")
        if raw_id is None:
            continue
        try:
            nid = int(raw_id)
        except ValueError:
            continue
        if nid < 1:
            continue
        text = _xml_text(el).strip()
        if text:
            notes[nid] = text
    return notes


def _related_part(document, reltype: str):
    for rel in document.part.rels.values():
        if rel.reltype == reltype:
            try:
                return rel.target_part
            except Exception:
                return None
    return None


def _xml_text(el: ET.Element) -> str:
    parts: list[str] = []
    for node in el.iter():
        if node.tag == f"{W}tab":
            parts.append("\t")
        elif node.tag == f"{W}br":
            parts.append("\n")
        elif node.tag == f"{W}t" and node.text:
            parts.append(node.text)
    return "".join(parts)


def _page_setup(document) -> dict[str, Any]:
    if not document.sections:
        return {}
    section = document.sections[0]

    def cm(value) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value.cm), 2)
        except Exception:
            return None

    orient = "portrait"
    try:
        # 0 = portrait, 1 = landscape in WD_ORIENT
        orient = "landscape" if int(section.orientation) == 1 else "portrait"
    except Exception:
        pass

    header_default = _block_text(section.header)
    footer_default = _block_text(section.footer)
    return {
        "page_width_cm": cm(section.page_width),
        "page_height_cm": cm(section.page_height),
        "orientation": orient,
        "margin_top_cm": cm(section.top_margin),
        "margin_bottom_cm": cm(section.bottom_margin),
        "margin_left_cm": cm(section.left_margin),
        "margin_right_cm": cm(section.right_margin),
        "gutter_cm": cm(section.gutter),
        "header_distance_cm": cm(section.header_distance),
        "footer_distance_cm": cm(section.footer_distance),
        "different_first_page_header_footer": bool(section.different_first_page_header_footer),
        "header_default": header_default,
        "footer_default": footer_default,
    }


def _headers_footers(document) -> tuple[dict[str, str], dict[str, str]]:
    headers: dict[str, str] = {}
    footers: dict[str, str] = {}
    if not document.sections:
        return headers, footers
    section = document.sections[0]
    mapping_h = {
        "default": section.header,
        "first": section.first_page_header,
        "even": section.even_page_header,
    }
    mapping_f = {
        "default": section.footer,
        "first": section.first_page_footer,
        "even": section.even_page_footer,
    }
    for key, block in mapping_h.items():
        text = _block_text(block)
        if text:
            headers[key] = text
    for key, block in mapping_f.items():
        text = _block_text(block)
        if text:
            footers[key] = text
    return headers, footers


def _block_text(block) -> str:
    if block is None:
        return ""
    try:
        if getattr(block, "is_linked_to_previous", False):
            return ""
    except Exception:
        pass
    lines: list[str] = []
    try:
        paragraphs = block.paragraphs
    except Exception:
        return ""
    for para in paragraphs:
        text = (para.text or "").strip()
        if text:
            lines.append(text)
    return " | ".join(lines)
