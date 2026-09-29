"""Turn recovered Markdown into HTML, DOCX, or PDF on this computer."""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from .arabic import HARAKAT
from .postprocess import has_persian

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
UL = re.compile(r"^(\s*)[-*+o◦•]\s+(.*)$", re.I)
OL = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
FENCE = re.compile(r"^```")
IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")

# Glue that may stay inside an LTR technical token (ST/PP, FCS_X.1, [IPC_IP]).
_LTR_GLUE = set("._\\-/:@#%+*=[]'")


def export_bytes(
    markdown: str,
    fmt: str,
    title: str = "document",
    base_dir: Path | None = None,
) -> tuple[bytes, str, str]:
    """Return (payload, filename, content_type)."""
    fmt = fmt.lower().strip()
    stem = _stem(title)
    rtl = has_persian(markdown)
    body = _strip_yaml(markdown)
    if base_dir:
        body = _absolutize_images(body, Path(base_dir))
    if fmt == "html":
        data = markdown_to_html(body, title=stem, rtl=rtl).encode("utf-8")
        return data, f"{stem}.html", "text/html; charset=utf-8"
    if fmt == "txt":
        data = body.encode("utf-8")
        return data, f"{stem}.txt", "text/plain; charset=utf-8"
    if fmt in {"docx", "doc"}:
        data = markdown_to_docx(body, title=stem, rtl=rtl)
        return data, f"{stem}.docx", (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    if fmt == "pdf":
        html_text = markdown_to_html(body, title=stem, rtl=rtl, for_print=True)
        pdf = html_to_pdf(html_text)
        if pdf:
            return pdf, f"{stem}.pdf", "application/pdf"
        data = html_text.encode("utf-8")
        return data, f"{stem}.print.html", "text/html; charset=utf-8"
    raise ValueError("Use html, docx, pdf, or txt.")


def markdown_to_html(markdown: str, *, title: str, rtl: bool, for_print: bool = False) -> str:
    lang = "fa" if rtl else "en"
    direction = "rtl" if rtl else "ltr"
    body_md = _prepare_export_text(markdown, rtl=rtl)
    inner = _blocks_to_html(_parse_blocks(body_md), rtl=rtl)
    print_js = (
        "<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},200)});</script>"
        if for_print
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{direction}">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: "Segoe UI", Tahoma, "Noto Naskh Arabic", Arial, sans-serif;
         line-height: 1.65; max-width: 800px; margin: 2rem auto; padding: 0 1.2rem;
         color: #111; }}
  pre, code {{ font-family: Consolas, "Courier New", monospace; direction: ltr; text-align: left;
              unicode-bidi: isolate; }}
  pre {{ background: #f4f4f4; padding: 0.8rem; overflow: auto; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #bbb; padding: 0.4rem 0.55rem; }}
  .ltr {{ direction: ltr; unicode-bidi: isolate; }}
  img {{ max-width: 100%; }}
  @media print {{ body {{ margin: 0; max-width: none; }} }}
</style>
</head>
<body>
{inner}
{print_js}
</body>
</html>
"""


def markdown_to_docx(markdown: str, *, title: str, rtl: bool) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    doc = Document()
    if rtl:
        sect = doc.sections[0]._sectPr
        if sect.find(qn("w:bidi")) is None:
            sect.append(OxmlElement("w:bidi"))

    body_md = _prepare_export_text(markdown, rtl=rtl)

    def style_paragraph(paragraph, *, force_ltr: bool = False) -> None:
        if force_ltr or not rtl:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            return
        pPr = paragraph._p.get_or_add_pPr()
        if pPr.find(qn("w:bidi")) is None:
            pPr.append(OxmlElement("w:bidi"))
        # Match sample tables: paragraph mark itself carries rtl.
        p_rPr = pPr.find(qn("w:rPr"))
        if p_rPr is None:
            p_rPr = OxmlElement("w:rPr")
            pPr.append(p_rPr)
        if p_rPr.find(qn("w:rtl")) is None:
            p_rPr.append(OxmlElement("w:rtl"))
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    def write_text(paragraph, text: str, *, force_ltr: bool = False) -> None:
        style_paragraph(paragraph, force_ltr=force_ltr)
        _clear_paragraph(paragraph)
        if force_ltr or not rtl:
            paragraph.add_run(text)
            return
        for chunk, chunk_rtl in split_bidi_runs(text):
            if not chunk:
                continue
            run = paragraph.add_run(chunk)
            if chunk_rtl:
                _mark_run_rtl(run)

    def write_cell(cell, text: str) -> None:
        cell.text = ""
        paragraph = cell.paragraphs[0]
        write_text(paragraph, text)

    for block in _parse_blocks(body_md):
        kind = block[0]
        if kind == "h":
            _, level, text = block
            p = doc.add_heading("", level=min(max(level, 1), 9))
            write_text(p, _plain(text))
        elif kind == "p":
            p = doc.add_paragraph()
            write_text(p, _plain(block[1]))
        elif kind == "pre":
            p = doc.add_paragraph()
            write_text(p, block[1], force_ltr=True)
        elif kind == "ul":
            for item, level in block[1]:
                p = doc.add_paragraph(style="List Bullet")
                if level:
                    p.paragraph_format.left_indent = Pt(18 * min(level, 4))
                write_text(p, _plain(item))
        elif kind == "ol":
            for item in block[1]:
                p = doc.add_paragraph(style="List Number")
                write_text(p, _plain(item))
        elif kind == "table":
            rows = block[1]
            if not rows:
                continue
            cols = max((len(r) for r in rows), default=1)
            table = doc.add_table(rows=len(rows), cols=cols)
            table.style = "Table Grid"
            if rtl:
                _mark_table_rtl(table)
            for ri, row in enumerate(rows):
                for ci in range(cols):
                    cell_text = row[ci] if ci < len(row) else ""
                    write_cell(table.rows[ri].cells[ci], _plain(cell_text))
        elif kind == "img":
            _, alt, src = block
            path = Path(src)
            if path.is_file():
                try:
                    doc.add_picture(str(path))
                    continue
                except Exception:
                    pass
            p = doc.add_paragraph()
            write_text(p, alt or src)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def split_bidi_runs(text: str) -> list[tuple[str, bool]]:
    """Split mixed Persian/Latin into (chunk, rtl) runs for Word.

    Matches the edited IPC tables: Latin technical islands stay LTR; Persian
    text and separator punctuation such as `` (``, ``) / ``, `` / `` get
    ``w:rtl`` (same Unicode, Persian typing direction).
    """
    if not text:
        return []

    def is_latin(ch: str) -> bool:
        return ("A" <= ch <= "Z") or ("a" <= ch <= "z")

    def is_digit(ch: str) -> bool:
        return "0" <= ch <= "9"

    def is_ltr_atom(ch: str) -> bool:
        return is_latin(ch) or is_digit(ch)

    def starts_ltr_island(idx: int) -> bool:
        ch = text[idx]
        if is_latin(ch):
            return True
        if ch == "[" and idx + 1 < len(text) and is_ltr_atom(text[idx + 1]):
            return True
        # Digits belong to LTR when glued to Latin (TLS 1.2) or placeholders.
        if not is_digit(ch):
            return False
        prev = text[idx - 1] if idx else ""
        if is_latin(prev) or prev in _LTR_GLUE:
            return True
        return False

    runs: list[tuple[str, bool]] = []
    i = 0
    n = len(text)
    while i < n:
        if starts_ltr_island(i):
            j = i + 1
            while j < n:
                c = text[j]
                if is_ltr_atom(c):
                    j += 1
                    continue
                if c in _LTR_GLUE:
                    if c == "/" and (j + 1 >= n or not is_ltr_atom(text[j + 1])):
                        break
                    j += 1
                    continue
                if c == " " and j + 1 < n:
                    nxt = text[j + 1]
                    if is_latin(nxt) or is_digit(nxt) or nxt == "[":
                        j += 1
                        continue
                    # CLI flags: " -connect", paths with " -tls1"
                    if nxt in "-/" and j + 2 < n and is_ltr_atom(text[j + 2]):
                        j += 1
                        continue
                break
            while j > i and text[j - 1] == " ":
                j -= 1
            runs.append((text[i:j], False))
            i = j
            continue
        j = i + 1
        while j < n and not starts_ltr_island(j):
            j += 1
        runs.append((text[i:j], True))
        i = j

    return _merge_runs(runs)


def _merge_runs(runs: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    merged: list[tuple[str, bool]] = []
    for chunk, rtl in runs:
        if not chunk:
            continue
        if merged and merged[-1][1] == rtl:
            merged[-1] = (merged[-1][0] + chunk, rtl)
        else:
            merged.append((chunk, rtl))
    return merged


def _prepare_export_text(markdown: str, *, rtl: bool) -> str:
    """Normalize Markdown body before HTML/DOCX (optional Persian cleanup)."""
    if not rtl:
        return markdown
    return _strip_harakat(markdown)


def _strip_harakat(text: str) -> str:
    return "".join(ch for ch in text if ch not in HARAKAT)


def _mark_run_rtl(run) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:hint"), "cs")
    if rPr.find(qn("w:rtl")) is None:
        rPr.append(OxmlElement("w:rtl"))


def _mark_table_rtl(table) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    if tblPr.find(qn("w:bidiVisual")) is None:
        tblPr.append(OxmlElement("w:bidiVisual"))


def _clear_paragraph(paragraph) -> None:
    from docx.oxml.ns import qn

    element = paragraph._element
    for child in list(element):
        if child.tag == qn("w:r"):
            element.remove(child)


def html_to_pdf(html_text: str) -> bytes | None:
    chrome = _chrome_path()
    if not chrome:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.html"
        dest = Path(tmp) / "doc.pdf"
        src.write_text(html_text, encoding="utf-8")
        try:
            subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-pdf-header-footer",
                    f"--print-to-pdf={dest}",
                    str(src),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            return None
        if dest.is_file() and dest.stat().st_size > 0:
            return dest.read_bytes()
    return None


def _chrome_path() -> str | None:
    env = os.environ.get("CHROME_PATH") or os.environ.get("EDGE_PATH")
    if env and Path(env).is_file():
        return env
    for name in ("msedge", "chrome", "chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    win_paths = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for path in win_paths:
        if path.is_file():
            return str(path)
    return None


def _absolutize_images(markdown: str, base: Path) -> str:
    def repl(match: re.Match) -> str:
        src = match.group(2)
        path = Path(src)
        if not path.is_absolute():
            path = (base / src).resolve()
        return f"![{match.group(1)}]({path.as_posix()})"

    return IMG.sub(repl, markdown)


def _parse_blocks(markdown: str) -> list[tuple]:
    lines = markdown.replace("\r\n", "\n").split("\n")
    blocks: list[tuple] = []
    i = 0
    para: list[str] = []

    def flush_para() -> None:
        text = " ".join(p.strip() for p in para if p.strip()).strip()
        para.clear()
        if text:
            blocks.append(("p", text))

    while i < len(lines):
        line = lines[i]
        if FENCE.match(line.strip()):
            flush_para()
            i += 1
            chunk: list[str] = []
            while i < len(lines) and not FENCE.match(lines[i].strip()):
                chunk.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            blocks.append(("pre", "\n".join(chunk)))
            continue
        if _is_table_row(line) and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            flush_para()
            rows = [_split_row(line)]
            i += 2
            while i < len(lines) and _is_table_row(lines[i]):
                rows.append(_split_row(lines[i]))
                i += 1
            blocks.append(("table", rows))
            continue
        hm = HEADING.match(line)
        if hm:
            flush_para()
            blocks.append(("h", len(hm.group(1)), hm.group(2).strip()))
            i += 1
            continue
        um = UL.match(line)
        if um:
            flush_para()
            indent = len(um.group(1).replace("\t", "    "))
            items = [(um.group(2), indent // 2)]
            i += 1
            while i < len(lines) and UL.match(lines[i]):
                m = UL.match(lines[i])
                ind = len(m.group(1).replace("\t", "    "))
                items.append((m.group(2), ind // 2))
                i += 1
            blocks.append(("ul", items))
            continue
        om = OL.match(line)
        if om:
            flush_para()
            items = [om.group(3)]
            i += 1
            while i < len(lines) and OL.match(lines[i]):
                items.append(OL.match(lines[i]).group(3))
                i += 1
            blocks.append(("ol", items))
            continue
        im = IMG.search(line.strip())
        if im and line.strip().startswith("!"):
            flush_para()
            blocks.append(("img", im.group(1), im.group(2)))
            i += 1
            continue
        if not line.strip():
            flush_para()
            i += 1
            continue
        para.append(line)
        i += 1
    flush_para()
    return blocks


def _blocks_to_html(blocks: list[tuple], *, rtl: bool = False) -> str:
    parts: list[str] = []
    for block in blocks:
        kind = block[0]
        if kind == "h":
            _, level, text = block
            parts.append(f"<h{min(level, 6)}>{_inline_html(text, rtl=rtl)}</h{min(level, 6)}>")
        elif kind == "p":
            parts.append(f"<p>{_inline_html(block[1], rtl=rtl)}</p>")
        elif kind == "pre":
            parts.append(f"<pre><code>{html.escape(block[1])}</code></pre>")
        elif kind == "ul":
            items = "".join(
                f'<li style="margin-inline-start:{min(level, 4) * 1.2}em">{_inline_html(x, rtl=rtl)}</li>'
                for x, level in block[1]
            )
            parts.append(f"<ul>{items}</ul>")
        elif kind == "ol":
            items = "".join(f"<li>{_inline_html(x, rtl=rtl)}</li>" for x in block[1])
            parts.append(f"<ol>{items}</ol>")
        elif kind == "table":
            rows = block[1]
            if not rows:
                continue
            head = "".join(f"<th>{_inline_html(c, rtl=rtl)}</th>" for c in rows[0])
            body = []
            for row in rows[1:]:
                body.append(
                    "<tr>" + "".join(f"<td>{_inline_html(c, rtl=rtl)}</td>" for c in row) + "</tr>"
                )
            dir_attr = ' dir="rtl"' if rtl else ""
            parts.append(
                f"<table{dir_attr}><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(body)}</tbody></table>"
            )
        elif kind == "img":
            _, alt, src = block
            parts.append(
                f'<p><img src="{html.escape(src, quote=True)}" alt="{html.escape(alt)}"></p>'
            )
    return "\n".join(parts)


def _inline_html(text: str, *, rtl: bool = False) -> str:
    def repl_img(m: re.Match) -> str:
        return f'<img src="{html.escape(m.group(2), quote=True)}" alt="{html.escape(m.group(1))}">'

    def repl_link(m: re.Match) -> str:
        return f'<a href="{html.escape(m.group(2), quote=True)}">{html.escape(m.group(1))}</a>'

    text = IMG.sub(repl_img, text)
    text = LINK.sub(repl_link, text)
    pieces = re.split(r"(<[^>]+>)", text)
    out = []
    for piece in pieces:
        if piece.startswith("<"):
            out.append(piece)
            continue
        if rtl:
            out.append(_bidi_html_spans(piece))
        else:
            esc = html.escape(piece)
            esc = BOLD.sub(r"<strong>\1</strong>", esc)
            esc = ITALIC.sub(r"<em>\1</em>", esc)
            out.append(esc)
    return "".join(out)


def _bidi_html_spans(text: str) -> str:
    """Wrap LTR islands so mixed Persian/Latin keeps reading order in HTML."""
    parts: list[str] = []
    for chunk, chunk_rtl in split_bidi_runs(text):
        esc = html.escape(chunk)
        esc = BOLD.sub(r"<strong>\1</strong>", esc)
        esc = ITALIC.sub(r"<em>\1</em>", esc)
        if chunk_rtl:
            parts.append(esc)
        else:
            parts.append(f'<span class="ltr">{esc}</span>')
    return "".join(parts)


def _plain(text: str) -> str:
    text = IMG.sub(r"\1", text)
    text = LINK.sub(r"\1", text)
    text = BOLD.sub(r"\1", text)
    text = ITALIC.sub(r"\1", text)
    return text.replace("`", "")


def _strip_yaml(markdown: str) -> str:
    if markdown.startswith("---"):
        end = markdown.find("\n---", 3)
        if end != -1:
            return markdown[end + 4 :].lstrip("\n")
    return markdown


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_table_sep(line: str) -> bool:
    return _is_table_row(line) and not (
        line.strip().strip("|").replace(":", "").replace("-", "").replace("|", "").replace(" ", "")
    )


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _stem(name: str) -> str:
    raw = Path(name.replace("\\", "/")).name
    stem = Path(raw).stem or "document"
    return re.sub(r'[<>:"/\\|?*]', "_", stem)[:80] or "document"
