"""Graph writer: persists extracted ArchiMate graph to Cloud Spanner.

Orchestrates the full write pipeline:
1. Parse normalized nodes and edges from extract_graph output
2. Compute entity-level embeddings (batch)
3. Reconcile entities against existing graph (exact match → vector similarity → new)
4. Upsert Document + DocumentChunks + Entities + Edges + Mentions in one atomic batch
"""
import math
import re
import uuid
import logging
from services.schema_registry import (
    ENTITY_TABLE_MAP,
    EDGE_TABLE_MAP,
    ARCHIMATE_LAYER_MAP,
)
from services.spanner_client import get_database, batch_write
from services.entity_reconciler import EntityReconciler
from services.document_chunker import compute_entity_embeddings, Chunk
from services.tenant_context import SHARED_TENANT

logger = logging.getLogger(__name__)

# Regex for parsing extract_graph output
_NODE_RE = re.compile(r"^([A-Za-z]+):(.+)$")
_EDGE_RE = re.compile(
    r"^([A-Za-z]+):(.+?)->"
    r"([A-Za-z]+)"
    r"(?:\[([^\]]*)\])?"
    r"->"
    r"([A-Za-z]+):(.+)$"
)

_VALID_CONFIDENCE = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}

# Control characters invalid in Spanner STRING columns (keep \t, \n, \r)
_INVALID_CTRL_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f]"
)


def _sanitize_for_spanner(text: str | None) -> str:
    """Strip characters that Spanner STRING columns reject (NULL bytes, control chars)."""
    if not text:
        return ""
    clean = _INVALID_CTRL_RE.sub("", text)
    # Roundtrip encode/decode to ensure valid UTF-8
    return clean.encode("utf-8", errors="replace").decode("utf-8")


def _sanitize_embedding(embedding: list[float] | None, expected_dim: int = 768) -> list[float]:
    """Ensure embedding is a valid FLOAT32 array with correct dimensions.

    Spanner rejects empty ARRAY<FLOAT32> in insert_or_update. If the embedding
    is missing or has wrong dimensions, returns a zero vector.
    """
    if not embedding or len(embedding) != expected_dim:
        if embedding and len(embedding) != expected_dim:
            logger.warning(f"Embedding has {len(embedding)} dims, expected {expected_dim} — using zero vector")
        return [0.0] * expected_dim
    has_invalid = False
    sanitized = []
    for v in embedding:
        if math.isfinite(v):
            sanitized.append(v)
        else:
            sanitized.append(0.0)
            has_invalid = True
    if has_invalid:
        logger.warning(f"Sanitized {sum(1 for v in embedding if not math.isfinite(v))} invalid float(s) in embedding")
    return sanitized


def _parse_qualifier_confidence(bracket_content: str | None) -> tuple[str, str]:
    """Parse bracket content like 'Read,EXTRACTED' or 'INFERRED' into (qualifier, confidence)."""
    if not bracket_content:
        return "", "EXTRACTED"
    parts = [p.strip() for p in bracket_content.split(",")]
    qualifier = ""
    confidence = "EXTRACTED"
    for part in parts:
        if part.upper() in _VALID_CONFIDENCE:
            confidence = part.upper()
        elif part:
            qualifier = part
    return qualifier, confidence


def write_graph_to_spanner(
    graph_json: dict,
    doc_id: str,
    doc_title: str,
    doc_summary: str,
    doc_embedding: list[float],
    chunks: list[Chunk] | None = None,
    document_date: str = "",
    tenant_id: str = SHARED_TENANT,
) -> dict:
    """Persist the extracted ArchiMate graph to Cloud Spanner.

    Args:
        graph_json: Output of extract_graph with extracted_nodes and extracted_edges
        doc_id: UUID for the source document
        doc_title: Document title
        doc_summary: Document summary text (for content_chunk field)
        doc_embedding: Pre-computed document embedding (768 dim)
        chunks: Optional list of Chunk objects with embeddings
        document_date: Publication/creation date of the document (ISO string or free-form)

    Returns:
        Summary dict with counts and reconciliation stats
    """
    nodes_raw = graph_json.get("extracted_nodes", [])
    edges_raw = graph_json.get("extracted_edges", [])

    # 1. Parse nodes
    parsed_nodes: list[dict] = []
    for raw in nodes_raw:
        m = _NODE_RE.match(raw.strip())
        if m:
            parsed_nodes.append({"type": m.group(1), "name": m.group(2)})

    # 2. Parse edges
    parsed_edges: list[dict] = []
    for raw in edges_raw:
        m = _EDGE_RE.match(raw.strip())
        if m:
            qualifier, confidence = _parse_qualifier_confidence(m.group(4))
            parsed_edges.append({
                "src_type": m.group(1), "src_name": m.group(2),
                "rel_type": m.group(3), "qualifier": qualifier,
                "confidence": confidence,
                "tgt_type": m.group(5), "tgt_name": m.group(6),
            })

    # 3. Compute entity embeddings (batch call)
    unique_entities = {f"{n['type']}:{n['name']}": n for n in parsed_nodes}
    entity_list = list(unique_entities.values())
    embeddings = compute_entity_embeddings(entity_list)
    for ent, emb in zip(entity_list, embeddings):
        ent["embedding"] = emb

    # 4. Reconcile entities
    database = get_database()
    reconciler = EntityReconciler(database, tenant_id=tenant_id)
    resolution_map: dict[str, str] = {}  # "Type:Name" → uuid

    for ent in entity_list:
        key = f"{ent['type']}:{ent['name']}"
        entity_id, is_new = reconciler.reconcile(
            ent["type"], ent["name"], ent.get("embedding", [])
        )
        resolution_map[key] = entity_id

    # 5. Build mutations
    mutations: list[tuple[str, list[str], list[list]]] = []

    # 5a. Document row
    doc_columns = ["doc_id", "tenant_id", "title", "content_chunk", "chunk_embedding"]
    doc_values = [doc_id, tenant_id, _sanitize_for_spanner(doc_title), _sanitize_for_spanner(doc_summary[:10000] if doc_summary else ""), _sanitize_embedding(doc_embedding)]
    if document_date:
        doc_columns.append("document_date")
        doc_values.append(document_date)
    mutations.append((
        "Documents",
        doc_columns,
        [doc_values],
    ))

    # 5b. DocumentChunks
    if chunks:
        chunk_columns = [
            "doc_id", "chunk_id", "tenant_id", "chunk_index", "chunk_text",
            "chunk_type", "image_uri", "page_number", "chunk_embedding",
        ]
        chunk_rows = []
        for c in chunks:
            # Store context_prefix + chunk_text for Contextual Retrieval
            stored_text = c.chunk_text
            if getattr(c, "context_prefix", ""):
                stored_text = f"{c.context_prefix}\n---\n{c.chunk_text}"
            chunk_rows.append([
                doc_id, c.chunk_id, tenant_id, c.chunk_index,
                _sanitize_for_spanner(stored_text[:10000] if stored_text else ""),
                c.chunk_type, c.image_uri, c.page_number,
                _sanitize_embedding(c.embedding),
            ])
        if chunk_rows:
            mutations.append(("DocumentChunks", chunk_columns, chunk_rows))

    # 5c. Entity rows (one mutation group per table)
    entities_by_table: dict[str, list[list]] = {}
    for ent in entity_list:
        table_info = ENTITY_TABLE_MAP.get(ent["type"])
        if not table_info:
            continue
        entity_id = resolution_map.get(f"{ent['type']}:{ent['name']}")
        if not entity_id:
            continue
        layer = ARCHIMATE_LAYER_MAP.get(ent["type"], "")
        table_name = table_info["table"]
        columns = [
            table_info["id_col"], "tenant_id", table_info["name_col"],
            "description", "archimate_layer", "source_doc_id",
            table_info["embedding_col"],
        ]
        values = [
            entity_id, tenant_id, _sanitize_for_spanner(ent["name"]),
            "", layer, doc_id,
            _sanitize_embedding(ent.get("embedding", [])),
        ]
        entities_by_table.setdefault(table_name, {"columns": columns, "rows": []})
        entities_by_table[table_name]["rows"].append(values)

    for table_name, data in entities_by_table.items():
        mutations.append((table_name, data["columns"], data["rows"]))

    # 5d. Edge rows (with confidence label)
    #
    # ArchiMate canonical direction enforcement: many extracted edges arrive
    # in inverted form (e.g. LLM emits "BusinessService realizes ApplicationComponent"
    # whereas ArchiMate convention is the more concrete element realizes the
    # more abstract one). The Spanner PROPERTY GRAPH definition has edge alias
    # rows like `Realization SOURCE=ApplicationComponents DESTINATION=BusinessServices`,
    # so an inverted (src,tgt) pair fails alias resolution and the edge is
    # invisible to GQL traversal even though the row exists in the table.
    # We normalize before writing.
    LAYER_RANK = {
        "Motivation": 0, "Strategy": 1, "Business": 2,
        "Application": 3, "Technology": 4, "Physical": 5,
    }
    # Canonical direction by relationship type, expressed as src_rank vs tgt_rank.
    # "concrete_to_abstract" means src is at a lower (more concrete) layer than tgt.
    CANONICAL_DIRECTION = {
        "Realization": "concrete_to_abstract",   # Component -> Service, Service -> Process
        "Serving":     "concrete_to_abstract",   # Service -> Process / Actor
        "Access":      "concrete_to_abstract",   # Process -> DataObject
        "Assignment":  "abstract_to_concrete",   # Actor -> Process, Component -> Node
        # Composition / Aggregation / Triggering / Flow are inherent — leave as-is.
    }

    def _maybe_swap(rel_type: str, src_type: str, tgt_type: str) -> tuple[bool, str, str]:
        rule = CANONICAL_DIRECTION.get(rel_type)
        if rule is None:
            return False, src_type, tgt_type
        s_rank = LAYER_RANK.get(ARCHIMATE_LAYER_MAP.get(src_type, ""), -1)
        t_rank = LAYER_RANK.get(ARCHIMATE_LAYER_MAP.get(tgt_type, ""), -1)
        if s_rank < 0 or t_rank < 0 or s_rank == t_rank:
            return False, src_type, tgt_type
        if rule == "concrete_to_abstract" and s_rank < t_rank:
            return True, tgt_type, src_type
        if rule == "abstract_to_concrete" and s_rank > t_rank:
            return True, tgt_type, src_type
        return False, src_type, tgt_type

    edges_by_table: dict[str, list[list]] = {}
    for edge in parsed_edges:
        src_type = edge["src_type"]
        tgt_type = edge["tgt_type"]
        src_name = edge["src_name"]
        tgt_name = edge["tgt_name"]
        swapped, norm_src_type, norm_tgt_type = _maybe_swap(edge["rel_type"], src_type, tgt_type)
        if swapped:
            src_type, tgt_type = norm_src_type, norm_tgt_type
            src_name, tgt_name = tgt_name, src_name

        src_key = f"{src_type}:{src_name}"
        tgt_key = f"{tgt_type}:{tgt_name}"
        src_id = resolution_map.get(src_key)
        tgt_id = resolution_map.get(tgt_key)
        if not src_id or not tgt_id:
            continue

        edge_info = EDGE_TABLE_MAP.get(edge["rel_type"])
        if not edge_info:
            continue

        table_name = edge_info["table"]
        detail_col = edge_info["detail_col"]
        confidence_col = edge_info.get("confidence_col", "confidence")
        columns = ["source_id", "target_id", "tenant_id", "source_type", "target_type", detail_col, confidence_col]
        confidence = edge.get("confidence", "EXTRACTED")
        values = [src_id, tgt_id, tenant_id, src_type, tgt_type, _sanitize_for_spanner(edge.get("qualifier", "")), confidence]
        edges_by_table.setdefault(table_name, {"columns": columns, "rows": []})
        edges_by_table[table_name]["rows"].append(values)

    for table_name, data in edges_by_table.items():
        mutations.append((table_name, data["columns"], data["rows"]))

    # 5e. DocumentMentions
    mention_rows = []
    for key, entity_id in resolution_map.items():
        entity_type = key.split(":", 1)[0]
        mention_rows.append([doc_id, entity_id, tenant_id, entity_type, ""])
    if mention_rows:
        mutations.append((
            "DocumentMentions",
            ["doc_id", "target_id", "tenant_id", "target_type", "mention_context"],
            mention_rows,
        ))

    # 5f. ChunkMentions (which chunk mentions which entity)
    if chunks:
        chunk_mention_rows = []
        for c in chunks:
            if c.chunk_type != "text" or not c.chunk_text:
                continue
            chunk_text_lower = c.chunk_text.lower()
            for ent in entity_list:
                if ent["name"].lower() in chunk_text_lower:
                    entity_id = resolution_map.get(f"{ent['type']}:{ent['name']}")
                    if entity_id:
                        chunk_mention_rows.append([
                            doc_id, c.chunk_id, entity_id, tenant_id, ent["type"], "",
                        ])
        if chunk_mention_rows:
            mutations.append((
                "ChunkMentions",
                ["doc_id", "chunk_id", "entity_id", "tenant_id", "entity_type", "mention_context"],
                chunk_mention_rows,
            ))

    # 6. Execute atomic batch write.
    # Spanner errors must surface to the caller — never silently return success
    # with empty counts. We capture the exception text into result["errors"]
    # *and* re-raise so per-file callers (e.g. GitIngester) can decide whether
    # to keep going or abort the whole run.
    errors: list[str] = []
    try:
        batch_write(mutations)
    except Exception as e:  # noqa: BLE001 — propagated below
        err_msg = f"batch_write failed for doc_id={doc_id}: {e}"
        logger.error(err_msg)
        errors.append(err_msg)
        # Re-raise so the caller sees the failure. The caller is responsible
        # for catching and recording it in its own summary["errors"].
        raise

    result = {
        "doc_id": doc_id,
        "entities_total": len(entity_list),
        "edges_total": len(parsed_edges),
        "chunks_total": len(chunks) if chunks else 0,
        "reconciliation": reconciler.stats,
        "errors": errors,
        # Maps "Type:Name" -> Spanner UUID. Consumers (e.g. GitIngester ->
        # Live Inspector) need these IDs to deep-link entities back to the
        # graph view. Order matches `entity_list`.
        "resolution_map": dict(resolution_map),
    }
    logger.info(f"Graph written to Spanner: {result}")
    return result
