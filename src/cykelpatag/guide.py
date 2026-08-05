"""Fetch and convert Naturskyddsföreningen's bicycle-on-train guide.

The stable source is the guide landing page, not the versioned PDF itself. The landing
page is fetched through r.jina.ai because it exposes links as straightforward Markdown;
the actual PDF is always downloaded from Naturskyddsföreningen's own domain.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol, cast
from urllib.parse import unquote, urljoin, urlparse

import httpx

GUIDE_PAGE_URL = "https://lund.naturskyddsforeningen.se/cykling/cykel-pa-tag/"
DEFAULT_MARKDOWN_PAGE_URL = f"https://r.jina.ai/{GUIDE_PAGE_URL}"
PDF_MAGIC = b"%PDF-"

# Markdown links emitted by r.jina.ai. The destination may contain an optional title.
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+[^)]*)?\)")

# PyMuPDF4LLM correctly reads this guide's columns, but leaves a blank paragraph
# boundary where a sentence continues from one column into the next. Only join a
# lower-case continuation when the preceding text has no sentence-ending punctuation.
COLUMN_CONTINUATION_RE = re.compile(r"([^\s.!?:;])\s*\n{2,}(?=[a-zåäö])")


class GuideError(RuntimeError):
    """Raised when the current guide cannot be safely retrieved or converted."""


@dataclass(frozen=True)
class GuideUpdateResult:
    """Paths emitted by a successful guide update."""

    pdf_path: Path
    markdown_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class _Candidate:
    url: str
    label: str
    score: int


class _MarkdownRenderer(Protocol):
    """The narrow optional PyMuPDF4LLM interface used by this project."""

    def __call__(
        self,
        document: str,
        *,
        header: bool,
        footer: bool,
        ignore_images: bool,
    ) -> str: ...


def _normalise_for_matching(value: str) -> str:
    return unquote(value).casefold().replace("\u00a0", " ")


def _candidate_score(label: str, url: str) -> int | None:
    """Return a confidence score for a Swedish guide candidate, or reject it."""
    parsed = urlparse(url)
    if not parsed.path.casefold().endswith(".pdf"):
        return None

    label_key = _normalise_for_matching(label)
    url_key = _normalise_for_matching(parsed.path)
    combined = f"{label_key} {url_key}"

    # Do not accidentally download the German translation, map images, or promotional poster.
    if any(word in combined for word in ("fahrrad", "affisch", "poster", "karta")):
        return None
    if "cykel" not in combined or "tag" not in combined:
        return None

    score = 0
    if "cykel_pa_tag" in url_key or "cykel-pa-tag" in url_key:
        score += 100
    if "beskrivning" in label_key:
        score += 20
    if "kartor" in label_key:
        score += 10
    if "cykel p\u00e5 t\u00e5g" in label_key:
        score += 10
    if "/wp-content/uploads/" in url_key:
        score += 5
    return score


def extract_guide_pdf_url(page_markdown: str, *, base_url: str = GUIDE_PAGE_URL) -> str:
    """Extract exactly one Swedish guide PDF URL from page Markdown.

    The selector deliberately relies on the document name and link label rather than a
    year-specific path. It fails loudly if the page structure becomes ambiguous.
    """
    candidates: dict[str, _Candidate] = {}
    for match in MARKDOWN_LINK_RE.finditer(page_markdown):
        label, raw_url = match.groups()
        url = urljoin(base_url, raw_url)
        score = _candidate_score(label, url)
        if score is None:
            continue
        previous = candidates.get(url)
        if previous is None or score > previous.score:
            candidates[url] = _Candidate(url=url, label=label, score=score)

    if not candidates:
        raise GuideError(
            "No Swedish 'Cykel p\u00e5 t\u00e5g' PDF link was found on the guide page."
        )

    ranked = sorted(candidates.values(), key=lambda item: item.score, reverse=True)
    if len(ranked) > 1 and ranked[0].score == ranked[1].score:
        choices = ", ".join(
            candidate.url for candidate in ranked if candidate.score == ranked[0].score
        )
        raise GuideError(f"More than one equally likely guide PDF was found: {choices}")
    return ranked[0].url


def _download(url: str) -> tuple[bytes, dict[str, str]]:
    try:
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise GuideError(f"Could not download {url}: {error}") from error
    return response.content, dict(response.headers)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def normalise_markdown_layout(markdown: str) -> str:
    """Repair an incomplete sentence split only by a two-column page boundary."""
    clean_markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    return COLUMN_CONTINUATION_RE.sub(r"\1 ", clean_markdown).strip()


def _parse_pdf_to_markdown(pdf_path: Path) -> str:
    """Parse the guide with the optional, layout-aware PyMuPDF4LLM renderer."""
    try:
        module = import_module("pymupdf4llm")
    except ModuleNotFoundError as error:
        raise GuideError(
            "PyMuPDF4LLM is not installed. Run 'uv sync --extra guide' before using guide update."
        ) from error

    try:
        to_markdown = cast(_MarkdownRenderer, module.to_markdown)
        markdown = to_markdown(
            str(pdf_path),
            header=False,
            footer=False,
            ignore_images=True,
        )
    except Exception as error:
        raise GuideError(f"PyMuPDF4LLM failed while reading {pdf_path}: {error}") from error

    markdown = normalise_markdown_layout(markdown)
    if not markdown:
        raise GuideError("PyMuPDF4LLM completed without producing readable Markdown.")
    return markdown


def add_markdown_provenance(markdown: str, *, pdf_url: str, pdf_sha256: str) -> str:
    """Prefix generated Markdown with the provenance needed for policy review."""
    clean_markdown = normalise_markdown_layout(markdown)
    if not clean_markdown:
        raise GuideError("Refusing to write an empty Markdown guide.")
    return (
        "> Generated from the current Naturskyddsföreningen PDF. Review this file before "
        "creating or publishing rules.\n\n"
        f"- Source PDF: {pdf_url}\n"
        f"- PDF SHA-256: `{pdf_sha256}`\n\n"
        "---\n\n"
        f"{clean_markdown}\n"
    )


def update_guide(
    *,
    page_url: str = DEFAULT_MARKDOWN_PAGE_URL,
    source_dir: Path = Path("data/source"),
    output_dir: Path = Path("data/generated"),
) -> GuideUpdateResult:
    """Fetch the current guide from its stable page and convert it to Markdown."""
    page_markdown, page_headers = _download(page_url)
    try:
        page_text = page_markdown.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GuideError(f"Guide page {page_url} was not UTF-8 Markdown.") from error

    pdf_url = extract_guide_pdf_url(page_text)
    pdf_bytes, pdf_headers = _download(pdf_url)
    if not pdf_bytes.startswith(PDF_MAGIC):
        content_type = pdf_headers.get("content-type", "unknown")
        raise GuideError(f"Guide URL did not return a PDF (content type: {content_type}).")

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    pdf_path = source_dir / "cykel-pa-tag.pdf"
    markdown_path = output_dir / "guide.md"
    metadata_path = output_dir / "guide-source.json"
    _atomic_write_bytes(pdf_path, pdf_bytes)
    parsed_markdown = _parse_pdf_to_markdown(pdf_path)
    markdown = add_markdown_provenance(parsed_markdown, pdf_url=pdf_url, pdf_sha256=pdf_sha256)
    _atomic_write_text(markdown_path, markdown)

    metadata = {
        "retrieved_at": datetime.now(UTC).isoformat(),
        "page_url": page_url,
        "canonical_page_url": GUIDE_PAGE_URL,
        "page_etag": page_headers.get("etag"),
        "pdf_url": pdf_url,
        "pdf_content_type": pdf_headers.get("content-type"),
        "pdf_sha256": pdf_sha256,
        "pdf_bytes": len(pdf_bytes),
        "extractor": {
            "package": "pymupdf4llm",
            "format": "markdown",
            "images": False,
            "header": False,
            "footer": False,
        },
    }
    _atomic_write_text(metadata_path, f"{json.dumps(metadata, ensure_ascii=False, indent=2)}\n")
    return GuideUpdateResult(pdf_path, markdown_path, metadata_path)
