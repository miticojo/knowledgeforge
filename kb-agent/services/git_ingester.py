"""Git repository ingestion: clone -> walk -> AST parse -> ArchiMate graph -> Spanner.

Treats source code as a first-class ingestion source for the KnowledgeForge graph.
Per Milestone H of the project plan, this MVP covers Python only; multi-language
support is planned as a follow-up.

Idempotency
-----------
Each file becomes a `Document` row keyed by

    doc_id = f"git:{repo_url}@{commit_sha}:{file_path}"

Re-running on the same commit upserts the same row. Entity reconciliation in
`graph_writer` deduplicates entities across files within a run (and across runs).

Placeholder import targets
--------------------------
Each `import X` produces an `ApplicationComponent:X` node and a `Composition`
edge with qualifier `placeholder`. The qualifier lands in the edge's `details`
column, giving a SQL-queryable audit handle. When the real module is later
ingested, `EntityReconciler` (exact-name match) will dedupe the placeholder
into the real entity.
"""
from __future__ import annotations

import logging
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterator

_SHA_RE = re.compile(r"^[0-9a-fA-F]+$")


def _looks_like_sha(s: str) -> bool:
    """Return True when `s` looks like an abbreviated or full git commit SHA.

    Accepts hex strings of length 7..12 (abbreviated) or exactly 40 (full).
    Branch and tag names are rejected (e.g. "main", "v1.2.3", "release/foo").
    """
    if not s:
        return False
    if not _SHA_RE.match(s):
        return False
    n = len(s)
    return n == 40 or 7 <= n <= 12

import uuid as _uuid

from services.ast_parsers import get_parser
from services.ast_to_archimate import to_graph
from services.schema_registry import ARCHIMATE_LAYER_MAP
from services.tenant_context import SHARED_TENANT

# Stable namespace for deterministic UUID v5 fallback IDs (used only when the
# writer does not return a resolution_map — keeps the inspector usable in
# tests / writer-mocked paths). Real production paths get the Spanner UUIDs.
_ID_NAMESPACE = _uuid.UUID("6f4e8b3c-2a1b-4d5e-9f0a-1c2d3e4f5061")

# Entities/edges per parse_end payload — keep SSE frames bounded.
_MAX_PAYLOAD_ITEMS = 200

logger = logging.getLogger(__name__)

DEFAULT_INCLUDE = ("**/*.py", "**/*.md")
DEFAULT_EXCLUDE = (
    "**/.git/**",
    "**/__pycache__/**",
    "**/tests/**",
    "**/test/**",
    "**/.venv/**",
    "**/venv/**",
    "**/node_modules/**",
)

EMBEDDING_DIM = 768

# Human-readable parser names by file extension. Keep in sync with
# services.ast_parsers.PARSERS — this map is for telemetry only and never
# affects which parser actually runs (that dispatch lives in get_parser).
_PARSER_LABELS: dict[str, str] = {
    ".py": "python-ast",
    ".ts": "tree-sitter-typescript",
    ".tsx": "tree-sitter-typescript",
    ".js": "tree-sitter-typescript",
    ".jsx": "tree-sitter-typescript",
    ".java": "tree-sitter-java",
    ".go": "tree-sitter-go",
    ".sql": "sqlglot",
    ".md": "gemini-markdown",
    ".markdown": "gemini-markdown",
}


def _parser_label(rel_path: Path) -> str:
    return _PARSER_LABELS.get(rel_path.suffix.lower(), "unsupported")


def _route_reason(rel_path: Path) -> str:
    ext = rel_path.suffix.lower()
    label = _PARSER_LABELS.get(ext)
    if label is None:
        return "other → skipped"
    return f"{ext} → {label}"


def _layer_breakdown(extracted_nodes: list) -> dict[str, int]:
    """Aggregate node counts per ArchiMate layer for telemetry.

    Tolerates two node shapes used across the codebase:
    - dict: ``{"entity_type": "ApplicationComponent", ...}``
    - str:  ``"ApplicationComponent:mod.Thing"`` (type prefix before the colon)
    """
    from services.schema_registry import ARCHIMATE_LAYER_MAP
    out: dict[str, int] = {}
    for node in extracted_nodes:
        if isinstance(node, dict):
            et = node.get("entity_type") or node.get("type")
        elif isinstance(node, str):
            et = node.split(":", 1)[0] if ":" in node else node
        else:
            et = None
        layer = ARCHIMATE_LAYER_MAP.get(et, "Unknown")
        out[layer] = out.get(layer, 0) + 1
    return out


_LANGUAGE_FOR_EXT: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".sql": "sql",
    ".md": "markdown",
    ".markdown": "markdown",
}


def _language_for(rel_path: Path) -> str:
    return _LANGUAGE_FOR_EXT.get(rel_path.suffix.lower(), "text")


def _sql_summary(parsed) -> dict:
    """Compact `{tables, foreign_keys}` view of the SQL ParsedFile.

    The SQL parser stores FK targets as `fk:<table>` entries inside each
    class's `bases`. We unpack them so the inspector doesn't need to know
    that internal convention.
    """
    tables: list[str] = []
    fks: list[dict] = []
    for cls in getattr(parsed, "classes", []) or []:
        tables.append(cls.name)
        for b in (cls.bases or []):
            if isinstance(b, str) and b.startswith("fk:"):
                fks.append({"from": cls.name, "to": b[len("fk:"):]})
    return {"tables": tables, "foreign_keys": fks}


def _serialize_parsed(parsed) -> dict:
    """Convert the parser's output into a JSON-safe small dict for the inspector.

    - Markdown parser already returns a dict (extracted_nodes/edges/title/summary).
    - AST parsers return a `ParsedFile` dataclass.
    """
    if parsed is None:
        return {}
    if isinstance(parsed, dict):
        return parsed
    try:
        from dataclasses import asdict, is_dataclass
        if is_dataclass(parsed):
            return asdict(parsed)
    except Exception:
        pass
    # Fallback: best-effort attribute dump.
    try:
        return {k: v for k, v in vars(parsed).items() if not k.startswith("_")}
    except TypeError:
        return {"repr": repr(parsed)}


def _fallback_id(doc_id: str, type_name: str, name: str) -> str:
    """Deterministic UUID v5 used when the writer doesn't expose real IDs.

    Production paths get the actual Spanner UUIDs from the writer's
    `resolution_map`. Fallback exists so test/mock paths still emit a usable
    `entities[].id` for the inspector.
    """
    return str(_uuid.uuid5(_ID_NAMESPACE, f"{doc_id}|{type_name}|{name}"))


def _parse_node_str(raw: str) -> tuple[str, str] | None:
    """Split "Type:name" → (type, name). Returns None if the shape is wrong."""
    if not isinstance(raw, str) or ":" not in raw:
        return None
    t, n = raw.split(":", 1)
    return t, n


def _parse_edge_str(raw: str) -> tuple[str, str, str, str, str, str] | None:
    """Split "SrcType:src->Rel[bracket]->TgtType:tgt".

    Returns (src_type, src_name, rel, confidence, tgt_type, tgt_name).
    """
    if not isinstance(raw, str) or "->" not in raw:
        return None
    # Split into 3 parts on "->"
    parts = raw.split("->")
    if len(parts) != 3:
        return None
    src_part, rel_part, tgt_part = parts
    src = _parse_node_str(src_part)
    tgt = _parse_node_str(tgt_part)
    if not src or not tgt:
        return None
    rel = rel_part
    confidence = "EXTRACTED"
    if "[" in rel and rel.endswith("]"):
        bracket = rel[rel.rfind("[") + 1:-1]
        rel = rel[:rel.rfind("[")]
        for p in (x.strip() for x in bracket.split(",") if x.strip()):
            if p in {"EXTRACTED", "INFERRED", "AMBIGUOUS"} or p.lower() in {"high", "medium", "low"}:
                confidence = p
    return src[0], src[1], rel, confidence, tgt[0], tgt[1]


def _build_entities_edges_payload(
    graph_json: dict,
    doc_id: str,
    resolution_map: dict | None,
) -> tuple[list[dict], list[dict], bool]:
    """Convert the graph_writer-style node/edge strings into the inspector
    payload. Returns (entities, edges, truncated)."""
    raw_nodes = graph_json.get("extracted_nodes", []) or []
    raw_edges = graph_json.get("extracted_edges", []) or []
    truncated = False

    entities: list[dict] = []
    # Track id-by-key so edges can resolve to the same id we emitted.
    id_by_key: dict[str, str] = {}
    for raw in raw_nodes:
        if isinstance(raw, dict):
            t = raw.get("entity_type") or raw.get("type")
            n = raw.get("name")
        else:
            parsed = _parse_node_str(raw)
            t, n = (parsed if parsed else (None, None))
        if not t or not n:
            continue
        key = f"{t}:{n}"
        if resolution_map and key in resolution_map:
            ent_id = resolution_map[key]
        else:
            ent_id = _fallback_id(doc_id, t, n)
        id_by_key[key] = ent_id
        if len(entities) >= _MAX_PAYLOAD_ITEMS:
            truncated = True
            break
        entities.append({
            "id": ent_id,
            "type": t,
            "name": n,
            "layer": ARCHIMATE_LAYER_MAP.get(t, "Unknown"),
            "confidence": "EXTRACTED",
        })

    edges: list[dict] = []
    for raw in raw_edges:
        if isinstance(raw, dict):
            st = raw.get("src_type") or raw.get("source_type")
            sn = raw.get("src_name") or raw.get("source_name")
            tt = raw.get("tgt_type") or raw.get("target_type")
            tn = raw.get("tgt_name") or raw.get("target_name")
            rel = raw.get("rel_type") or raw.get("relationship_type") or ""
            conf = raw.get("confidence") or "EXTRACTED"
            parsed = (st, sn, rel, conf, tt, tn) if all([st, sn, tt, tn]) else None
        else:
            parsed = _parse_edge_str(raw)
        if not parsed:
            continue
        st, sn, rel, conf, tt, tn = parsed
        sk = f"{st}:{sn}"
        tk = f"{tt}:{tn}"
        src_id = id_by_key.get(sk)
        tgt_id = id_by_key.get(tk)
        if not src_id or not tgt_id:
            # Fallback so an edge still has stable refs even if one endpoint
            # was beyond the entity cap.
            src_id = src_id or _fallback_id(doc_id, st, sn)
            tgt_id = tgt_id or _fallback_id(doc_id, tt, tn)
        if len(edges) >= _MAX_PAYLOAD_ITEMS:
            truncated = True
            break
        edges.append({
            "source": src_id,
            "target": tgt_id,
            "rel": rel,
            "confidence": conf,
        })

    return entities, edges, truncated


def _confidence_breakdown(extracted_edges: list) -> dict[str, int]:
    """Aggregate edge counts per confidence label.

    Tolerates dict edges and string-encoded edges. Confidence may live on the
    edge dict directly or be embedded as a bracketed suffix on the
    relationship label (see ast_to_archimate._edge).
    """
    out: dict[str, int] = {}
    for edge in extracted_edges:
        if isinstance(edge, dict):
            conf = edge.get("confidence")
            rel = edge.get("relationship_type") or ""
        elif isinstance(edge, str):
            conf = None
            rel = edge
        else:
            conf = None
            rel = ""
        if not conf:
            if "[" in rel and rel.endswith("]"):
                payload = rel[rel.rfind("[") + 1:-1]
                # payload may be "qualifier,confidence" or just one of them
                parts = [p.strip() for p in payload.split(",") if p.strip()]
                # Heuristic: known confidence labels
                for p in parts:
                    if p.lower() in {"high", "medium", "low"}:
                        conf = p.lower()
                        break
        conf = conf or "unspecified"
        out[conf] = out.get(conf, 0) + 1
    return out


def _default_writer(*args, **kwargs):
    """Lazy import of write_graph_to_spanner to avoid pulling Spanner deps at import time."""
    from services.graph_writer import write_graph_to_spanner
    return write_graph_to_spanner(*args, **kwargs)


def _default_embedder(items: list[dict]) -> list[list[float]]:
    """Lazy import of compute_entity_embeddings to avoid pulling genai at import time."""
    from services.document_chunker import compute_entity_embeddings
    return compute_entity_embeddings(items)


class GitIngester:
    """Clone a Git repo, walk its files, AST-parse, and write to the KF graph.

    Parameters
    ----------
    repo_url:
        HTTPS or SSH URL of the repository to ingest.
    ref:
        Optional branch/tag/commit ref. Defaults to the repo's default branch.
    include:
        Iterable of glob patterns (relative to clone root). Default: `("**/*.py",)`.
    exclude:
        Iterable of glob patterns to subtract. Default skips .git, __pycache__,
        tests, virtualenvs, and node_modules.
    workdir:
        Directory to clone into. If None, a tmp directory is created and removed
        on success. If supplied, the caller is responsible for cleanup.
    tenant_id:
        Spanner tenant. Defaults to `SHARED_TENANT`.
    writer:
        Injection point for tests. Callable with the same signature as
        `services.graph_writer.write_graph_to_spanner`.
    embedder:
        Injection point for tests. Callable with the same signature as
        `services.document_chunker.compute_entity_embeddings`.
    """

    def __init__(
        self,
        repo_url: str,
        ref: str | None = None,
        include: list[str] | tuple[str, ...] | None = None,
        exclude: list[str] | tuple[str, ...] | None = None,
        workdir: Path | None = None,
        tenant_id: str = SHARED_TENANT,
        writer: Callable | None = None,
        embedder: Callable | None = None,
        event_callback: Callable[[str, dict], None] | None = None,
        artifact_callback: Callable[[str, dict], None] | None = None,
    ):
        self.repo_url = repo_url
        self.ref = ref
        self.include = tuple(include) if include else DEFAULT_INCLUDE
        self.exclude = tuple(exclude) if exclude else DEFAULT_EXCLUDE
        self._user_workdir = workdir is not None
        self.workdir = Path(workdir) if workdir else None
        self.tenant_id = tenant_id
        self._writer = writer or _default_writer
        self._embedder = embedder or _default_embedder
        self._event_cb = event_callback
        self._artifact_cb = artifact_callback
        self._clone_path: Path | None = None
        self._commit_sha: str | None = None

    def _emit(self, event_type: str, data: dict) -> None:
        if self._event_cb is None:
            return
        try:
            self._event_cb(event_type, data)
        except Exception as e:  # never let telemetry break ingestion
            logger.warning("event_callback failed (%s): %s", event_type, e)

    def _emit_artifact(self, file_path: str, data: dict) -> None:
        if self._artifact_cb is None:
            return
        try:
            self._artifact_cb(file_path, data)
        except Exception as e:  # never let telemetry break ingestion
            logger.warning("artifact_callback failed for %s: %s", file_path, e)

    # ------------------------------------------------------------------ clone
    def clone(self) -> Path:
        """Shallow-clone the repo into self.workdir; return the clone root."""
        from git import Repo  # local import: gitpython is an optional runtime dep

        if self.workdir is None:
            self.workdir = Path(tempfile.mkdtemp(prefix="kf-git-"))
        dest = self.workdir / "repo"
        if dest.exists():
            shutil.rmtree(dest)
        logger.info("Cloning %s ref=%s -> %s", self.repo_url, self.ref, dest)

        if self.ref and _looks_like_sha(self.ref):
            # Shallow clones don't fetch arbitrary SHAs by default; clone
            # without --branch, then fetch the specific commit and check it out.
            repo = Repo.clone_from(self.repo_url, str(dest), depth=1)
            try:
                repo.git.fetch("--depth=1", "origin", self.ref)
            except Exception as e:
                logger.warning("shallow fetch of %s failed (%s); retrying full fetch", self.ref, e)
                repo.git.fetch("origin", self.ref)
            repo.git.checkout(self.ref)
        elif self.ref:
            repo = Repo.clone_from(self.repo_url, str(dest), depth=1, branch=self.ref)
        else:
            repo = Repo.clone_from(self.repo_url, str(dest), depth=1)

        self._commit_sha = repo.head.commit.hexsha
        self._clone_path = dest
        return dest

    # ------------------------------------------------------------------- walk
    def walk(self, root: Path | None = None) -> Iterator[Path]:
        """Yield files under `root` matching include globs minus exclude globs.

        Returns paths *relative to root*.
        """
        base = root if root is not None else self._clone_path
        if base is None:
            raise RuntimeError("walk() called before clone() and without an explicit root")

        included: set[Path] = set()
        for pattern in self.include:
            for p in base.glob(pattern):
                if p.is_file():
                    included.add(p)

        excluded: set[Path] = set()
        for pattern in self.exclude:
            for p in base.glob(pattern):
                if p.is_file():
                    excluded.add(p)

        for p in sorted(included - excluded):
            yield p.relative_to(base)

    # ----------------------------------------------------------------- ingest
    def ingest(self) -> dict:
        """Full pipeline: clone -> walk -> parse -> to_graph -> writer.

        Returns a summary dict with file/entity/edge counts plus repo metadata.
        """
        cleanup = False
        if self._clone_path is None:
            self.clone()
            cleanup = not self._user_workdir
        assert self._clone_path is not None
        assert self._commit_sha is not None

        files_processed = 0
        files_skipped = 0
        entities_total = 0
        edges_total = 0
        errors: list[str] = []

        write_t0 = time.perf_counter()
        self._emit("write_start", {
            "repo_url": self.repo_url,
            "commit_sha": self._commit_sha,
        })
        try:
            for rel_path in self.walk():
                abs_path = self._clone_path / rel_path
                parser_label = _parser_label(rel_path)
                self._emit("route", {
                    "file": str(rel_path),
                    "parser": parser_label,
                    "reason": _route_reason(rel_path),
                })
                parser = get_parser(rel_path)
                if parser is None:
                    files_skipped += 1
                    continue
                try:
                    source = abs_path.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    errors.append(f"{rel_path}: read error: {e}")
                    self._emit("parse_error", {
                        "file": str(rel_path),
                        "parser": parser_label,
                        "stage": "read",
                        "error": str(e),
                    })
                    continue
                file_t0 = time.perf_counter()
                self._emit("parse_start", {
                    "file": str(rel_path),
                    "parser": parser_label,
                })
                try:
                    parsed = parser(source, str(rel_path))
                except SyntaxError as e:
                    errors.append(f"{rel_path}: syntax error: {e}")
                    self._emit("parse_error", {
                        "file": str(rel_path),
                        "parser": parser_label,
                        "stage": "parse",
                        "error": f"syntax error: {e}",
                    })
                    continue
                except Exception as e:  # parser bug — log but keep going
                    errors.append(f"{rel_path}: parser error: {e}")
                    self._emit("parse_error", {
                        "file": str(rel_path),
                        "parser": parser_label,
                        "stage": "parse",
                        "error": str(e),
                    })
                    continue

                doc_id = f"git:{self.repo_url}@{self._commit_sha}:{rel_path}"

                # Markdown parser returns graph_json dict directly (with title/summary),
                # bypassing the ParsedFile -> to_graph step used by AST parsers.
                if isinstance(parsed, dict):
                    graph_json = {
                        "extracted_nodes": parsed.get("extracted_nodes", []),
                        "extracted_edges": parsed.get("extracted_edges", []),
                    }
                    md_title = parsed.get("title") or str(rel_path)
                    md_summary = parsed.get("summary", "")
                    embed_text = md_title + ("\n" + md_summary if md_summary else "")
                    _md_doc_title = md_title
                    _md_doc_summary = md_summary
                    _md_module_name = md_title
                else:
                    graph_json = to_graph(parsed, doc_id=doc_id)
                    embed_text = parsed.module_name
                    if parsed.module_doc:
                        embed_text = f"{parsed.module_name}\n{parsed.module_doc}"
                    _md_doc_title = str(rel_path)
                    _md_doc_summary = parsed.module_doc or ""
                    _md_module_name = parsed.module_name
                try:
                    doc_embedding = self._embedder([{"name": embed_text}])[0]
                except Exception as e:  # never fail ingestion on embed errors
                    logger.warning("embedding failed for %s: %s", rel_path, e)
                    doc_embedding = [0.0] * EMBEDDING_DIM

                # Build chunks from the source so retrieval has text to find.
                # One chunk per ~1500 char window with module summary as context prefix.
                from services.document_chunker import Chunk
                chunks: list[Chunk] = []
                CHUNK_SIZE = 1500
                ctx_prefix = (
                    f"File: {rel_path}\nModule: {_md_module_name}"
                    + (f"\nSummary: {_md_doc_summary}" if _md_doc_summary else "")
                )
                for i in range(0, len(source), CHUNK_SIZE):
                    chunk_text = source[i:i + CHUNK_SIZE]
                    if not chunk_text.strip():
                        continue
                    try:
                        chunk_emb = self._embedder([{"name": chunk_text[:800]}])[0]
                    except Exception:
                        chunk_emb = [0.0] * EMBEDDING_DIM
                    import hashlib as _hl
                    _cid = _hl.md5(f"{doc_id}:c{len(chunks)}".encode()).hexdigest()
                    chunks.append(Chunk(
                        chunk_id=_cid,
                        chunk_index=len(chunks),
                        chunk_text=chunk_text,
                        chunk_type="text",
                        page_number=None,
                        context_prefix=ctx_prefix,
                        embedding=chunk_emb,
                    ))

                try:
                    writer_result = self._writer(
                        graph_json,
                        doc_id=doc_id,
                        doc_title=_md_doc_title,
                        doc_summary=_md_doc_summary,
                        doc_embedding=doc_embedding,
                        chunks=chunks,
                        tenant_id=self.tenant_id,
                    )
                except Exception as e:
                    errors.append(f"{rel_path}: writer error: {e}")
                    self._emit("parse_error", {
                        "file": str(rel_path),
                        "parser": parser_label,
                        "stage": "write",
                        "error": str(e),
                    })
                    continue

                files_processed += 1
                nodes = graph_json.get("extracted_nodes", [])
                edges = graph_json.get("extracted_edges", [])
                entities_total += len(nodes)
                edges_total += len(edges)

                # Build the inspector payload (entities + edges with stable
                # IDs). Prefer real Spanner UUIDs from the writer if it
                # exposed a resolution_map; otherwise fall back to UUID v5.
                resolution_map = None
                if isinstance(writer_result, dict):
                    resolution_map = writer_result.get("resolution_map")
                payload_entities, payload_edges, truncated = _build_entities_edges_payload(
                    graph_json, doc_id=doc_id, resolution_map=resolution_map,
                )

                parse_end_payload = {
                    "file": str(rel_path),
                    "parser": parser_label,
                    "entities_added": len(nodes),
                    "edges_added": len(edges),
                    "layer_breakdown": _layer_breakdown(nodes),
                    "confidence_breakdown": _confidence_breakdown(edges),
                    "duration_ms": int((time.perf_counter() - file_t0) * 1000),
                    "entities": payload_entities,
                    "edges": payload_edges,
                }
                if truncated:
                    parse_end_payload["truncated"] = True
                self._emit("parse_end", parse_end_payload)

                # Stash the per-file artifact for the live inspector.
                if self._artifact_cb is not None:
                    language = _language_for(rel_path)
                    if language == "sql":
                        parsed_view = _sql_summary(parsed)
                    else:
                        parsed_view = _serialize_parsed(parsed)
                    self._emit_artifact(str(rel_path), {
                        "file": str(rel_path),
                        "parser": parser_label,
                        "language": language,
                        "source": source,
                        "parsed": parsed_view,
                        "entities": payload_entities,
                        "edges": payload_edges,
                    })

            summary = {
                "repo_url": self.repo_url,
                "commit_sha": self._commit_sha,
                "files_processed": files_processed,
                "files_skipped": files_skipped,
                "entities_total": entities_total,
                "edges_total": edges_total,
                "errors": errors,
            }
            self._emit("write_end", {
                **summary,
                "duration_ms": int((time.perf_counter() - write_t0) * 1000),
            })
            return summary
        finally:
            if cleanup and self.workdir and self.workdir.exists():
                try:
                    shutil.rmtree(self.workdir)
                except OSError:
                    pass
