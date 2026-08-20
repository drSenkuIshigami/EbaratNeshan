"""EbaratNeshan (عبارت‌نشان) — document to LLM-ready Markdown, with Persian glyph recovery."""

from ._vendor import setup as _setup_vendor

_setup_vendor()

from .convert import ConversionResult, convert, convert_docx, convert_pdf

__all__ = ["convert", "convert_pdf", "convert_docx", "ConversionResult"]
