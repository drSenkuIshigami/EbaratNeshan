"""YAML header, digit folding, and optional LLM chapter split."""

from __future__ import annotations

import re
from pathlib import Path

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_H1 = re.compile(r"^# ([^\n#].*)$", re.M)
_LINK = re.compile(r"(\[[^\]]*\]\([^)]+\))")


def has_persian(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in text)


def yaml_header(
    *,
    title: str,
    source: str | Path,
    purpose: str,
    tables: int = 0,
    figures: int = 0,
    lang: str | None = None,
) -> str:
    lang = lang or "und"
    src = Path(source).name
    return (
        "---\n"
        f"title: { _yaml_scalar(title) }\n"
        f"source: { _yaml_scalar(src) }\n"
        f"lang: {lang}\n"
        f"purpose: {purpose}\n"
        f"tables: {tables}\n"
        f"figures: {figures}\n"
        "---\n\n"
    )


def _yaml_scalar(value: str) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    if any(ch in text for ch in ":#{}[],&*?|>!%@`"):
        return f'"{text}"'
    return text


def to_persian_digits(markdown: str) -> str:
    parts = _LINK.split(markdown)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
        else:
            out.append(part.translate(_FA_DIGITS))
    return "".join(out)


def split_by_h1(markdown: str) -> list[tuple[str, str]]:
    """Return (slug, chapter_markdown) for each H1 body section. YAML stays on each part."""
    yaml, body = _split_yaml(markdown)
    matches = list(_H1.finditer(body))
    if len(matches) < 2:
        return []
    parts: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        title = match.group(1).strip()
        slug = f"{i + 1:02d}-{_slug(title)}"
        chunk = yaml + body[start:end].strip() + "\n"
        parts.append((slug, chunk))
    return parts


def write_llm_parts(markdown: str, job_dir: Path) -> list[Path]:
    parts = split_by_h1(markdown)
    if not parts:
        return []
    dest = job_dir / "parts"
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    index = ["# Parts", ""]
    for slug, chunk in parts:
        path = dest / f"{slug}.md"
        path.write_text(chunk, encoding="utf-8")
        written.append(path)
        heading = _H1.search(chunk)
        label = heading.group(1).strip() if heading else slug
        index.append(f"- [{label}](parts/{slug}.md)")
    index_path = dest / "README.md"
    index_path.write_text("\n".join(index) + "\n", encoding="utf-8")
    written.append(index_path)
    return written


def _split_yaml(markdown: str) -> tuple[str, str]:
    if markdown.startswith("---\n"):
        end = markdown.find("\n---\n", 4)
        if end != -1:
            return markdown[: end + 5] + "\n", markdown[end + 5 :].lstrip("\n")
    return "", markdown


def _slug(title: str) -> str:
    text = re.sub(r"[^\w\u0600-\u06FF]+", "-", title, flags=re.UNICODE).strip("-")
    return (text[:40] or "section").lower()
