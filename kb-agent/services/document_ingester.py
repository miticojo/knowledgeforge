"""Document upload ingestion: bytes -> liteparse|chunked text -> entities -> graph.

The git-side equivalent is `services.git_ingester.GitIngester`. This module
intentionally mirrors its event_callback / artifact_callback contract so the
frontend pipeline UI (AgentTimeline + LiveInspector + GraphDelta) is the same
component for both sources:

    route -> parse_start -> parse_end (entities/edges) -> write_start -> write_end -> complete

A single `parse_end` is emitted per document (not per chunk). For a typical
PDF the entity-extraction step is the expensive part and runs once on the
full extracted text; per-chunk parse_end events would be telemetry noise
without a corresponding per-chunk extraction step. The chunks themselves are
embedded for retrieval but are not separately surfaced in the timeline.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


_PARSER_LABELS_BY_EXT: dict[str, str] = {
    ".pdf": "liteparse",
    ".docx": "liteparse",
    ".md": "text",
    ".markdown": "text",
    ".txt": "text",
}

_LANGUAGE_BY_EXT: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
}


def _parser_label(path: str) -> str:
    return _PARSER_LABELS_BY_EXT.get(Path(path).suffix.lower(), "text")


def _language(path: str) -> str:
    return _LANGUAGE_BY_EXT.get(Path(path).suffix.lower(), "text")


def _route_reason(path: str) -> str:
    ext = Path(path).suffix.lower() or "(no-ext)"
    return f"{ext} -> {_parser_label(path)}"


def _try_pypdf(raw_bytes: bytes | None) -> str | None:
    """Local-only PDF text extraction via pypdf. Returns None when pypdf is
    missing or the bytes are not a parseable PDF (e.g. encrypted)."""
    if not raw_bytes:
        return None
    try:
        import io
        from pypdf import PdfReader
    except Exception:
        return None
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        parts: list[str] = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        out = "\n\n".join(p.strip() for p in parts if p and p.strip())
        return out or None
    except Exception as e:
        logger.warning("pypdf extraction failed: %s", e)
        return None


def _try_liteparse(file_name: str, raw_bytes: bytes | None) -> str | None:
    """Best-effort call to the liteparse / docling microservice.

    Returns the extracted text, or None when the service is unreachable / no
    bytes were provided. Callers fall back to the `text` field when the
    upload is already plain text.
    """
    url = os.getenv("DOCLING_URL") or os.getenv("LITEPARSE_URL")
    if not url or not raw_bytes:
        return None
    try:
        import httpx  # local import: optional dep, present in requirements
    except Exception:
        return None
    try:
        with httpx.Client(timeout=120) as client:
            r = client.post(
                f"{url.rstrip('/')}/parse",
                files={"file": (file_name, raw_bytes, "application/octet-stream")},
                data={"output_format": "markdown"},
            )
        if r.status_code == 200:
            data = r.json()
            return data.get("text") or ""
    except Exception as e:
        logger.warning("liteparse call failed for %s: %s", file_name, e)
    return None


def _chunk_text(text: str, size: int = 1500, overlap: int = 200) -> list[str]:
    """Plain windowed chunker — used for the demo / fallback path.

    `services.document_chunker._split_text_semantically` produces semantically
    cleaner chunks but pulls in genai at import time (and embeds via Gemini),
    which we don't want to require for the lightweight demo path.
    """
    if not text:
        return []
    out: list[str] = []
    step = max(1, size - overlap)
    i = 0
    while i < len(text):
        chunk = text[i:i + size]
        if chunk.strip():
            out.append(chunk)
        i += step
    return out


def _extract_sections(text: str, max_sections: int = 20) -> list[str]:
    """Best-effort extraction of headings from the document text.

    Looks for Markdown-style headings (`# Title`, `## Sub`) — useful for
    PDFs that come back from liteparse formatted as markdown. Returns at
    most `max_sections` headings, each truncated to 120 chars.
    """
    sections: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            heading = s.lstrip("#").strip()
            if heading:
                sections.append(heading[:120])
                if len(sections) >= max_sections:
                    break
    return sections


def _extract_entities_and_edges(text: str) -> tuple[list[str], list[str]]:
    """Run the existing controlled-generation extractor on the document text.

    Falls back to `([], [])` when no Gemini key is configured — the rest of
    the pipeline still produces a useful artifact (chunks, sections) so the
    inspector remains populated and the SSE stream completes cleanly.
    """
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        return [], []
    try:
        from agents.processing import _run_graph_extraction  # type: ignore
        result = _run_graph_extraction(text)
        return result.get("extracted_nodes", []) or [], result.get("extracted_edges", []) or []
    except Exception as e:
        logger.warning("entity extraction failed: %s", e)
        return [], []


def run_document_ingest(
    *,
    job_id: str,
    file_name: str,
    text: str | None,
    raw_bytes: bytes | None,
    tenant_id: str,
    event_callback: Callable[[str, dict], None] | None = None,
    artifact_callback: Callable[[str, dict], None] | None = None,
    raw_callback: Callable[[str, bytes], None] | None = None,
) -> dict:
    """Document ingestion mirror of `GitIngester.ingest`.

    Parameters mirror the git path: callbacks for events + per-file artifacts.
    `raw_callback` is invoked once with the original bytes (PDF/DOCX) so the
    raw store can stash them for later `<embed>` rendering. Returns the same
    `summary` dict shape used by /ingest/git for consistency.

    The function is intentionally synchronous so it can be scheduled from a
    FastAPI BackgroundTask exactly like `_run_git_ingest`.
    """
    def emit(et: str, data: dict) -> None:
        if event_callback is None:
            return
        try:
            event_callback(et, data)
        except Exception as e:
            logger.warning("event_callback failed (%s): %s", et, e)

    def emit_artifact(path: str, data: dict) -> None:
        if artifact_callback is None:
            return
        try:
            artifact_callback(path, data)
        except Exception as e:
            logger.warning("artifact_callback failed for %s: %s", path, e)

    parser = _parser_label(file_name)
    language = _language(file_name)

    emit("route", {
        "file": file_name,
        "parser": parser,
        "reason": _route_reason(file_name),
    })

    # parse_start: we are about to extract text + entities.
    emit("parse_start", {"file": file_name, "parser": parser})

    # Resolve the document text. Order of preference:
    #   1. caller-supplied text (browser already extracted, demo mode);
    #   2. liteparse on raw_bytes;
    #   3. raw_bytes decoded as UTF-8 (last-ditch fallback for .txt).
    extracted_text: str = ""
    if text:
        extracted_text = text
    if not extracted_text and raw_bytes is not None:
        lp = _try_liteparse(file_name, raw_bytes)
        if lp:
            extracted_text = lp
    if not extracted_text and raw_bytes is not None and Path(file_name).suffix.lower() == ".pdf":
        pp = _try_pypdf(raw_bytes)
        if pp:
            extracted_text = pp
    if not extracted_text and raw_bytes is not None:
        try:
            extracted_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            extracted_text = ""

    if raw_bytes is not None and raw_callback is not None:
        try:
            raw_callback(file_name, raw_bytes)
        except Exception as e:
            logger.warning("raw_callback failed for %s: %s", file_name, e)

    chunks = _chunk_text(extracted_text)
    sections = _extract_sections(extracted_text)

    nodes_raw, edges_raw = _extract_entities_and_edges(extracted_text)

    # Convert the same node/edge string shapes git uses into the inspector
    # payload so the frontend renderer is identical.
    from services.git_ingester import _build_entities_edges_payload
    doc_id = f"doc:{tenant_id}:{file_name}"
    graph_json = {"extracted_nodes": nodes_raw, "extracted_edges": edges_raw}
    entities, edges, truncated = _build_entities_edges_payload(
        graph_json, doc_id=doc_id, resolution_map=None,
    )

    parse_end_payload: dict = {
        "file": file_name,
        "parser": parser,
        "entities_added": len(nodes_raw),
        "edges_added": len(edges_raw),
        "chunks": len(chunks),
        "entities": entities,
        "edges": edges,
    }
    if truncated:
        parse_end_payload["truncated"] = True
    emit("parse_end", parse_end_payload)

    # Stash per-file artifact for the Live Inspector (mirrors git layout).
    parsed_view = {
        "title": (sections[0] if sections else file_name),
        "sections": sections,
        "image_count": 0,
    }
    emit_artifact(file_name, {
        "file": file_name,
        "parser": parser,
        "language": language,
        "source": extracted_text,
        "parsed": parsed_view,
        "entities": entities,
        "edges": edges,
    })

    # write_start / write_end: this MVP does not write doc uploads to Spanner
    # from the new endpoint (the legacy ProcessingAgent path still owns that).
    # We still emit the events so the frontend timeline renders consistently
    # for both git and upload sources.
    emit("write_start", {"file": file_name})
    emit("write_end", {
        "file": file_name,
        "entities_total": len(entities),
        "edges_total": len(edges),
        "chunks_total": len(chunks),
    })

    summary = {
        "file": file_name,
        "parser": parser,
        "files_processed": 1,
        "files_skipped": 0,
        "entities_total": len(entities),
        "edges_total": len(edges),
        "chunks_total": len(chunks),
        "errors": [],
    }
    return summary
