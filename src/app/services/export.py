"""Document export. Markdown is the canonical format; exports convert it to md/docx/pdf.

Like the LLM layer, the renderer is config-driven: a real Pandoc renderer in production
and a deterministic ``fake`` renderer for tests/CI (no pandoc binary, no PDF engine)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Protocol

from ..config import Settings

EXPORT_FORMATS = ("md", "docx", "pdf")

CONTENT_TYPES = {
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


class ExportError(Exception):
    pass


def content_type_for(fmt: str) -> str:
    if fmt not in CONTENT_TYPES:
        raise ExportError(f"unsupported export format: {fmt}")
    return CONTENT_TYPES[fmt]


class ExportRenderer(Protocol):
    def render(self, markdown_text: str, fmt: str, *, title: str = "") -> bytes: ...


class FakeRenderer:
    """Deterministic bytes without any external binary. Test/dev only."""

    kind = "fake"

    def render(self, markdown_text: str, fmt: str, *, title: str = "") -> bytes:
        if fmt == "md":
            return markdown_text.encode("utf-8")
        if fmt == "pdf":
            # Minimal, deterministic PDF-looking payload (enough for tests/plumbing).
            body = f"%PDF-1.4\n% fake export: {title}\n{markdown_text}".encode()
            return body
        if fmt == "docx":
            return f"FAKE-DOCX::{title}::\n{markdown_text}".encode()
        raise ExportError(f"unsupported export format: {fmt}")


class PandocRenderer:
    """Real renderer via pypandoc. Requires the pandoc binary (and a PDF engine for pdf)."""

    kind = "pandoc"

    def __init__(self, pdf_engine: str = "weasyprint") -> None:
        self._pdf_engine = pdf_engine

    def render(self, markdown_text: str, fmt: str, *, title: str = "") -> bytes:
        if fmt == "md":
            return markdown_text.encode("utf-8")
        try:
            import pypandoc
        except ImportError as exc:  # pragma: no cover
            raise ExportError("pypandoc is not installed") from exc

        extra_args = [f"--metadata=title:{title}"] if title else []
        if fmt == "pdf":
            extra_args.append(f"--pdf-engine={self._pdf_engine}")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"review.{fmt}"
            try:
                pypandoc.convert_text(
                    markdown_text,
                    to=fmt,
                    format="markdown",
                    outputfile=str(out),
                    extra_args=extra_args,
                )
            except Exception as exc:  # pragma: no cover - pandoc raises broad errors
                raise ExportError(f"pandoc failed for {fmt}: {exc}") from exc
            return out.read_bytes()


def build_renderer(settings: Settings) -> ExportRenderer:
    if settings.export_renderer == "fake":
        return FakeRenderer()
    return PandocRenderer(pdf_engine=settings.pandoc_pdf_engine)
