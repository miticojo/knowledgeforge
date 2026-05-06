"""Graph navigation: list/search/neighborhood queries for the UI graph explorer.

All queries are tenant-scoped using `tenant_sql_filter_for(database, table)` so
they degrade gracefully on databases that have not yet had the tenant_id
migration applied (T14 fix). Each helper exposes a small, dynamic-SQL builder
that respects optional layer / type / confidence / document filters.
"""
from __future__ import annotations

import logging
from typing import Iterable

from services.schema_registry import (
    ENTITY_TABLE_MAP,
    EDGE_TABLE_MAP,
    ARCHIMATE_LAYER_MAP,
)
from services.tenant_context import (
    get_tenant,
    tenant_sql_filter_for,
)

logger = logging.getLogger(__name__)

# Hard cap on a single page of nodes to keep the UI responsive and avoid
# accidentally pulling the full tenant graph in one request.
_MAX_LIMIT = 5000


def _string_param_type():
    from google.cloud.spanner_v1 import param_types
    return param_types.STRING


def _normalize_csv(values: Iterable[str] | None) -> list[str] | None:
    """Strip / dedupe csv-style filter values; return None when empty."""
    if not values:
        return None
    out = [v.strip() for v in values if v and v.strip()]
    return out or None


def _entity_types_for_layers(layers: list[str]) -> list[str]:
    """Translate ArchiMate layer names to the entity types they contain."""
    layer_set = {l for l in layers}
    return [etype for etype, layer in ARCHIMATE_LAYER_MAP.items() if layer in layer_set]


def list_entities(
    database,
    *,
    layers: list[str] | None = None,
    entity_types: list[str] | None = None,
    confidences: list[str] | None = None,  # accepted for symmetry; unused on entity rows
    document_id: str | None = None,
    limit: int = 500,
    offset: int = 0,
    tenant_id: str | None = None,
) -> dict:
    """List entities across (filtered) entity tables.

    Returns ``{nodes: [...], total, has_more}``. Each node carries
    ``{entity_id, name, type, layer, source_doc_id, description}``.

    The tables iterated are:
      - all 22 ENTITY_TABLE_MAP tables, OR
      - the subset whose entity_type is in ``entity_types``, OR
      - the subset whose layer is in ``layers`` (when entity_types not given).

    Both layer and entity_type filters are intersected when both are passed.
    """
    layers = _normalize_csv(layers)
    entity_types = _normalize_csv(entity_types)
    _ = _normalize_csv(confidences)  # entity rows have no confidence; accepted but ignored

    if limit <= 0:
        limit = 500
    if limit > _MAX_LIMIT:
        limit = _MAX_LIMIT
    if offset < 0:
        offset = 0

    # Decide which entity types to scan
    candidate_types = list(ENTITY_TABLE_MAP.keys())
    if entity_types:
        candidate_types = [t for t in candidate_types if t in set(entity_types)]
    if layers:
        layer_types = set(_entity_types_for_layers(layers))
        candidate_types = [t for t in candidate_types if t in layer_types]

    tid = tenant_id if tenant_id is not None else get_tenant()
    base_params = {"_tid": tid}
    base_types = {"_tid": _string_param_type()}
    if document_id:
        base_params["doc_id"] = document_id
        base_types["doc_id"] = _string_param_type()

    nodes: list[dict] = []
    total = 0

    for etype in candidate_types:
        tinfo = ENTITY_TABLE_MAP[etype]
        layer = ARCHIMATE_LAYER_MAP.get(etype, "")
        where_extra = ""
        if document_id:
            where_extra = " AND source_doc_id = @doc_id"
        # Count first so the caller can paginate properly across the union.
        try:
            with database.snapshot() as snap:
                count_sql = (
                    f"SELECT COUNT(*) FROM {tinfo['table']} "
                    f"WHERE {tenant_sql_filter_for(database, tinfo['table'])}"
                    f"{where_extra}"
                )
                for r in snap.execute_sql(count_sql, params=base_params, param_types=base_types):
                    total += int(r[0] or 0)
        except Exception as e:
            logger.debug(f"list_entities count failed for {tinfo['table']}: {e}")

    # Now fetch actual rows with global limit/offset across the union.
    remaining = limit
    skipped = 0
    for etype in candidate_types:
        if remaining <= 0:
            break
        tinfo = ENTITY_TABLE_MAP[etype]
        layer = ARCHIMATE_LAYER_MAP.get(etype, "")
        where_extra = ""
        if document_id:
            where_extra = " AND source_doc_id = @doc_id"
        sql = (
            f"SELECT {tinfo['id_col']}, {tinfo['name_col']}, "
            f"description, source_doc_id "
            f"FROM {tinfo['table']} "
            f"WHERE {tenant_sql_filter_for(database, tinfo['table'])}{where_extra} "
            f"ORDER BY {tinfo['id_col']} "
            f"LIMIT {remaining + offset}"
        )
        try:
            with database.snapshot() as snap:
                rows = list(snap.execute_sql(sql, params=base_params, param_types=base_types))
        except Exception as e:
            logger.debug(f"list_entities fetch failed for {tinfo['table']}: {e}")
            continue
        for r in rows:
            if skipped < offset:
                skipped += 1
                continue
            if remaining <= 0:
                break
            nodes.append({
                "entity_id": r[0],
                "name": r[1] or r[0],
                "type": etype,
                "layer": layer,
                "description": (r[2] or "")[:500],
                "source_doc_id": r[3] or "",
            })
            remaining -= 1

    has_more = (offset + len(nodes)) < total
    return {"nodes": nodes, "total": total, "has_more": has_more}


def list_edges_for_nodes(
    database,
    node_ids: list[str],
    *,
    confidences: list[str] | None = None,
    tenant_id: str | None = None,
) -> list[dict]:
    """Return edges where source_id or target_id is in ``node_ids``.

    Iterates every EDGE_TABLE_MAP table and collects matches, optionally
    filtered by confidence (e.g. ``["EXTRACTED", "INFERRED"]``).
    """
    if not node_ids:
        return []
    confidences = _normalize_csv(confidences)
    tid = tenant_id if tenant_id is not None else get_tenant()
    node_set = set(node_ids)

    # Bind each node id as @nid0..@nidN to keep query plans cacheable.
    id_params = {f"nid{i}": nid for i, nid in enumerate(node_ids)}
    id_types = {f"nid{i}": _string_param_type() for i in range(len(node_ids))}
    id_params["_tid"] = tid
    id_types["_tid"] = _string_param_type()

    in_clause = ", ".join(f"@nid{i}" for i in range(len(node_ids)))
    edges: list[dict] = []

    for rel_type, einfo in EDGE_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                sql = (
                    f"SELECT source_id, target_id, confidence "
                    f"FROM {einfo['table']} "
                    f"WHERE (source_id IN ({in_clause}) OR target_id IN ({in_clause})) "
                    f"AND {tenant_sql_filter_for(database, einfo['table'])}"
                )
                for r in snap.execute_sql(sql, params=id_params, param_types=id_types):
                    src, tgt, conf = r[0], r[1], (r[2] or "EXTRACTED")
                    if confidences and conf not in set(confidences):
                        continue
                    # Only keep edges whose BOTH endpoints are in the requested set
                    # to avoid orphan dangling edges in the UI.
                    if src not in node_set or tgt not in node_set:
                        continue
                    edges.append({
                        "source_id": src,
                        "target_id": tgt,
                        "type": rel_type,
                        "confidence": conf,
                    })
        except Exception as e:
            logger.debug(f"list_edges_for_nodes failed on {einfo['table']}: {e}")
    return edges


def search_entities(
    database,
    q: str,
    *,
    entity_types: list[str] | None = None,
    limit: int = 20,
    tenant_id: str | None = None,
) -> list[dict]:
    """Case-insensitive LIKE search over name/description across entity tables.

    For ``len(q) > 3`` we *attempt* to embed the query and add a vector-similarity
    pass. If the embedder is not available (or fails) we silently fall back to
    LIKE-only — search must remain best-effort and never raise.

    Returns up to ``limit`` matches sorted by score (LIKE-name=1.0, LIKE-desc=0.6,
    vector contributions blended by 1 - distance).
    """
    if not q or not q.strip():
        return []
    q = q.strip()
    if limit <= 0:
        limit = 20
    if limit > 200:
        limit = 200

    entity_types = _normalize_csv(entity_types)
    tid = tenant_id if tenant_id is not None else get_tenant()

    candidate_types = list(ENTITY_TABLE_MAP.keys())
    if entity_types:
        candidate_types = [t for t in candidate_types if t in set(entity_types)]

    pattern = f"%{q.lower()}%"
    base_params = {"q": pattern, "_tid": tid}
    base_types = {"q": _string_param_type(), "_tid": _string_param_type()}

    scored: dict[str, dict] = {}

    for etype in candidate_types:
        tinfo = ENTITY_TABLE_MAP[etype]
        layer = ARCHIMATE_LAYER_MAP.get(etype, "")
        sql = (
            f"SELECT {tinfo['id_col']}, {tinfo['name_col']}, description "
            f"FROM {tinfo['table']} "
            f"WHERE (LOWER({tinfo['name_col']}) LIKE @q OR LOWER(IFNULL(description,'')) LIKE @q) "
            f"AND {tenant_sql_filter_for(database, tinfo['table'])} "
            f"LIMIT {limit}"
        )
        try:
            with database.snapshot() as snap:
                for r in snap.execute_sql(sql, params=base_params, param_types=base_types):
                    eid, name, desc = r[0], r[1] or "", r[2] or ""
                    name_hit = q.lower() in name.lower()
                    score = 1.0 if name_hit else 0.6
                    snippet = (desc or name)[:200]
                    prev = scored.get(eid)
                    if prev is None or prev["score"] < score:
                        scored[eid] = {
                            "entity_id": eid,
                            "type": etype,
                            "name": name or eid,
                            "layer": layer,
                            "snippet": snippet,
                            "score": round(score, 4),
                        }
        except Exception as e:
            logger.debug(f"search_entities LIKE failed on {tinfo['table']}: {e}")

    # Optional vector pass — best-effort, errors are silenced.
    if len(q) > 3:
        try:
            from google import genai
            from services.document_chunker import (
                _get_embedding_client,
                EMBEDDING_MODEL,
                EMBEDDING_DIMENSIONS,
            )
            from google.cloud.spanner_v1 import param_types

            client = _get_embedding_client()
            emb = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=q[:8000],
                config=genai.types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=EMBEDDING_DIMENSIONS,
                ),
            )
            qvec = list(emb.embeddings[0].values)
            for etype in candidate_types:
                tinfo = ENTITY_TABLE_MAP[etype]
                layer = ARCHIMATE_LAYER_MAP.get(etype, "")
                vsql = (
                    f"SELECT {tinfo['id_col']}, {tinfo['name_col']}, description, "
                    f"COSINE_DISTANCE({tinfo['embedding_col']}, @qv) AS d "
                    f"FROM {tinfo['table']} "
                    f"WHERE {tinfo['embedding_col']} IS NOT NULL "
                    f"AND ARRAY_LENGTH({tinfo['embedding_col']}) > 0 "
                    f"AND {tenant_sql_filter_for(database, tinfo['table'])} "
                    f"ORDER BY d LIMIT {limit}"
                )
                with database.snapshot() as snap:
                    for r in snap.execute_sql(
                        vsql,
                        params={"qv": qvec, "_tid": tid},
                        param_types={
                            "qv": param_types.Array(param_types.FLOAT32),
                            "_tid": _string_param_type(),
                        },
                    ):
                        eid, name, desc, d = r[0], r[1] or "", r[2] or "", r[3] or 1.0
                        v_score = max(0.0, 1.0 - float(d)) * 0.8
                        prev = scored.get(eid)
                        if prev is None:
                            scored[eid] = {
                                "entity_id": eid,
                                "type": etype,
                                "name": name or eid,
                                "layer": layer,
                                "snippet": (desc or name)[:200],
                                "score": round(v_score, 4),
                            }
                        else:
                            prev["score"] = round(max(prev["score"], v_score), 4)
        except Exception as e:
            logger.debug(f"search_entities vector pass skipped: {e}")

    results = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
    return results[:limit]


def get_neighborhood(
    database,
    entity_id: str,
    *,
    hops: int = 1,
    max_per_hop: int = 20,
    tenant_id: str | None = None,
) -> dict:
    """BFS expansion around ``entity_id`` returning a ``{nodes, edges, center_id}`` sub-graph.

    Walks edge tables directly (not GQL) so the same code paths and tenant
    filters as the rest of graph_analytics are reused. ``hops`` is capped at 4
    and ``max_per_hop`` at 100 to bound the query budget.
    """
    if not entity_id:
        return {"nodes": [], "edges": [], "center_id": entity_id}
    hops = max(1, min(hops or 1, 4))
    max_per_hop = max(1, min(max_per_hop or 20, 100))

    tid = tenant_id if tenant_id is not None else get_tenant()
    visited_ids: set[str] = {entity_id}
    visited_meta: dict[str, dict] = {}
    edges: list[dict] = []

    frontier = {entity_id}
    for _ in range(hops):
        if not frontier:
            break
        next_frontier: set[str] = set()
        # Build a single IN clause for the whole frontier, per edge table.
        f_list = list(frontier)
        params = {f"nid{i}": nid for i, nid in enumerate(f_list)}
        ptypes = {f"nid{i}": _string_param_type() for i in range(len(f_list))}
        params["_tid"] = tid
        ptypes["_tid"] = _string_param_type()
        in_clause = ", ".join(f"@nid{i}" for i in range(len(f_list)))

        for rel_type, einfo in EDGE_TABLE_MAP.items():
            try:
                sql = (
                    f"SELECT source_id, source_type, target_id, target_type, confidence "
                    f"FROM {einfo['table']} "
                    f"WHERE (source_id IN ({in_clause}) OR target_id IN ({in_clause})) "
                    f"AND {tenant_sql_filter_for(database, einfo['table'])} "
                    f"LIMIT {max_per_hop}"
                )
                with database.snapshot() as snap:
                    for r in snap.execute_sql(sql, params=params, param_types=ptypes):
                        src, src_t, tgt, tgt_t, conf = r[0], r[1] or "", r[2], r[3] or "", r[4] or "EXTRACTED"
                        edges.append({
                            "source_id": src,
                            "target_id": tgt,
                            "type": rel_type,
                            "confidence": conf,
                        })
                        for nid, ntype in ((src, src_t), (tgt, tgt_t)):
                            if nid and nid not in visited_ids:
                                visited_ids.add(nid)
                                visited_meta[nid] = {"type": ntype}
                                next_frontier.add(nid)
            except Exception as e:
                logger.debug(f"get_neighborhood edge query failed on {einfo['table']}: {e}")
        frontier = next_frontier

    # Resolve names for every visited node (best-effort).
    nodes: list[dict] = []
    by_type: dict[str, list[str]] = {}
    for nid, meta in visited_meta.items():
        by_type.setdefault(meta["type"], []).append(nid)
    name_lookup: dict[str, tuple[str, str]] = {}
    for etype, ids in by_type.items():
        tinfo = ENTITY_TABLE_MAP.get(etype)
        if not tinfo:
            continue
        params = {f"id{i}": eid for i, eid in enumerate(ids)}
        ptypes = {f"id{i}": _string_param_type() for i in range(len(ids))}
        params["_tid"] = tid
        ptypes["_tid"] = _string_param_type()
        in_clause = ", ".join(f"@id{i}" for i in range(len(ids)))
        try:
            with database.snapshot() as snap:
                sql = (
                    f"SELECT {tinfo['id_col']}, {tinfo['name_col']} "
                    f"FROM {tinfo['table']} "
                    f"WHERE {tinfo['id_col']} IN ({in_clause}) "
                    f"AND {tenant_sql_filter_for(database, tinfo['table'])}"
                )
                for r in snap.execute_sql(sql, params=params, param_types=ptypes):
                    name_lookup[r[0]] = (r[1] or r[0], etype)
        except Exception:
            pass

    # Always include the center node, even when its row could not be resolved.
    if entity_id not in visited_meta:
        visited_meta[entity_id] = {"type": ""}
    for nid in visited_ids:
        name, etype = name_lookup.get(nid, (nid, visited_meta.get(nid, {}).get("type", "")))
        nodes.append({
            "entity_id": nid,
            "name": name,
            "type": etype,
            "layer": ARCHIMATE_LAYER_MAP.get(etype, ""),
        })

    # Dedupe edges
    seen = set()
    deduped = []
    for e in edges:
        k = (e["source_id"], e["target_id"], e["type"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(e)

    return {"nodes": nodes, "edges": deduped, "center_id": entity_id}
