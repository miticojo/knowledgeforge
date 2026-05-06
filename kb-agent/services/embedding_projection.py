"""3D PCA projection of entity / chunk embeddings for the embedding-space viewer.

Loads embeddings (768d) from Spanner, fits PCA via numpy SVD, returns 3D points
plus the mean + 3 principal components so the same projection can later be
applied to a query vector ("project_query").

Cached per (tenant, kind) in-process. Caller invalidates by passing
`force_refresh=True` after a new ingestion.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import numpy as np

from services.schema_registry import ENTITY_TABLE_MAP, ARCHIMATE_LAYER_MAP
from services.tenant_context import get_tenant, tenant_sql_filter_for

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768
DEFAULT_LIMIT = 1500
PER_TYPE_CAP = 200          # avoid one type dominating the projection
CACHE_TTL_SECONDS = 600

# In-process cache: key=(tenant, kind) -> {ts, mean, components, points}
_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def _fit_pca(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[float]]:
    """Return (mean, components_3xD, projected_Nx3, variance_explained_3)."""
    mean = matrix.mean(axis=0)
    centered = matrix - mean
    # Truncated SVD on centered data; full_matrices=False is fast enough for N<5000.
    _u, s, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:3]                              # (3, D)
    projected = centered @ components.T              # (N, 3)
    total_var = float((s ** 2).sum()) or 1.0
    var_explained = [float(v) for v in (s[:3] ** 2) / total_var]
    return mean, components, projected, var_explained


def _load_entity_embeddings(database, tenant_id: Optional[str], limit: int) -> list[dict]:
    """Pull embeddings + label/type from every entity table. Caps per-type."""
    rows: list[dict] = []
    per_type = max(20, limit // max(1, len(ENTITY_TABLE_MAP)))
    per_type = min(per_type, PER_TYPE_CAP)
    for etype, info in ENTITY_TABLE_MAP.items():
        table = info["table"]
        id_col = info["id_col"]
        name_col = info["name_col"]
        emb_col = info["embedding_col"]
        sql = (
            f"SELECT {id_col} AS id, {name_col} AS name, {emb_col} AS emb "
            f"FROM {table} "
            f"WHERE {tenant_sql_filter_for(database, table)} "
            f"AND {emb_col} IS NOT NULL "
            f"LIMIT @lim"
        )
        try:
            from google.cloud.spanner_v1 import param_types
            with database.snapshot() as snap:
                results = snap.execute_sql(
                    sql,
                    params={"lim": per_type, "_tid": tenant_id or ""},
                    param_types={"lim": param_types.INT64, "_tid": param_types.STRING},
                )
                for row in results:
                    eid, name, emb = row[0], row[1], row[2]
                    if not emb or len(emb) != EMBEDDING_DIM:
                        continue
                    rows.append({
                        "id": eid,
                        "label": name,
                        "type": etype,
                        "layer": ARCHIMATE_LAYER_MAP.get(etype, "Other"),
                        "_emb": emb,
                    })
        except Exception as e:
            logger.warning("embedding_projection: skip %s (%s)", table, e)
            continue
        if len(rows) >= limit:
            break
    return rows[:limit]


def _load_chunk_embeddings(database, tenant_id: Optional[str], limit: int) -> list[dict]:
    """Pull embeddings + preview text from DocumentChunks."""
    rows: list[dict] = []
    sql = (
        "SELECT chunk_id, doc_id, SUBSTR(chunk_text, 0, 80) AS preview, chunk_embedding "
        "FROM DocumentChunks "
        f"WHERE {tenant_sql_filter_for(database, 'DocumentChunks')} "
        "AND chunk_embedding IS NOT NULL "
        "LIMIT @lim"
    )
    try:
        from google.cloud.spanner_v1 import param_types
        with database.snapshot() as snap:
            results = snap.execute_sql(
                sql,
                params={"lim": limit, "_tid": tenant_id or ""},
                param_types={"lim": param_types.INT64, "_tid": param_types.STRING},
            )
            for row in results:
                cid, did, preview, emb = row[0], row[1], row[2], row[3]
                if not emb or len(emb) != EMBEDDING_DIM:
                    continue
                rows.append({
                    "id": cid,
                    "label": (preview or "").strip() or cid,
                    "type": "Chunk",
                    "layer": did,
                    "_emb": emb,
                })
    except Exception as e:
        logger.warning("embedding_projection: chunks load failed (%s)", e)
    return rows


def compute_projection(
    database,
    *,
    kind: str = "entities",
    limit: int = DEFAULT_LIMIT,
    tenant_id: Optional[str] = None,
    force_refresh: bool = False,
) -> dict:
    """Compute (or fetch from cache) a 3D PCA projection of stored embeddings."""
    tenant = tenant_id or get_tenant() or "default"
    key = (tenant, kind)

    if not force_refresh:
        cached = _CACHE.get(key)
        if cached and (time.time() - cached["ts"]) < CACHE_TTL_SECONDS:
            return _serialize(cached, include_points=True)

    if kind == "chunks":
        rows = _load_chunk_embeddings(database, tenant, limit)
    else:
        rows = _load_entity_embeddings(database, tenant, limit)

    if len(rows) < 4:
        return {
            "kind": kind,
            "tenant": tenant,
            "count": len(rows),
            "points": [],
            "variance_explained": [0.0, 0.0, 0.0],
            "projection_id": None,
            "error": "Not enough embeddings to project (need >=4).",
        }

    matrix = np.asarray([r.pop("_emb") for r in rows], dtype=np.float32)
    mean, components, projected, var = _fit_pca(matrix)

    for i, r in enumerate(rows):
        r["x"] = float(projected[i, 0])
        r["y"] = float(projected[i, 1])
        r["z"] = float(projected[i, 2])

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix_unit = matrix / norms

    payload = {
        "ts": time.time(),
        "kind": kind,
        "tenant": tenant,
        "mean": mean,
        "components": components,
        "matrix_unit": matrix_unit,
        "ids": [r["id"] for r in rows],
        "points": rows,
        "variance_explained": var,
        "projection_id": f"{tenant}:{kind}:{int(time.time())}",
    }
    _CACHE[key] = payload
    return _serialize(payload, include_points=True)


def project_query_vector(
    embedding: list[float],
    *,
    kind: str = "entities",
    tenant_id: Optional[str] = None,
) -> dict:
    """Project a 768d query embedding into the cached PCA space."""
    tenant = tenant_id or get_tenant() or "default"
    cached = _CACHE.get((tenant, kind))
    if cached is None:
        return {"error": "No cached projection. Call /embeddings/projection first."}
    vec = np.asarray(embedding, dtype=np.float32)
    if vec.shape[0] != EMBEDDING_DIM:
        return {"error": f"Expected {EMBEDDING_DIM}d vector, got {vec.shape[0]}d"}
    centered = vec - cached["mean"]
    proj = centered @ cached["components"].T
    return {
        "x": float(proj[0]),
        "y": float(proj[1]),
        "z": float(proj[2]),
        "projection_id": cached["projection_id"],
    }


def nearest_to_query(
    embedding: list[float],
    *,
    kind: str = "entities",
    tenant_id: Optional[str] = None,
    top_k: int = 30,
) -> dict:
    """Cosine-sim top-K against the cached embedding matrix.

    Returns ids + similarity scores (descending). The query is also projected
    into the cached PCA space for overlay rendering.
    """
    tenant = tenant_id or get_tenant() or "default"
    cached = _CACHE.get((tenant, kind))
    if cached is None:
        return {"error": "No cached projection. Call /embeddings/projection first."}
    vec = np.asarray(embedding, dtype=np.float32)
    if vec.shape[0] != EMBEDDING_DIM:
        return {"error": f"Expected {EMBEDDING_DIM}d vector, got {vec.shape[0]}d"}

    n = np.linalg.norm(vec) or 1.0
    sims = cached["matrix_unit"] @ (vec / n)
    k = min(top_k, sims.shape[0])
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]
    ids = cached["ids"]
    hits = [{"id": ids[int(i)], "score": float(sims[int(i)])} for i in idx]

    centered = vec - cached["mean"]
    proj = centered @ cached["components"].T
    return {
        "query": {"x": float(proj[0]), "y": float(proj[1]), "z": float(proj[2])},
        "hits": hits,
        "projection_id": cached["projection_id"],
    }


def invalidate_cache(tenant_id: Optional[str] = None, kind: Optional[str] = None) -> None:
    if tenant_id is None and kind is None:
        _CACHE.clear()
        return
    for k in list(_CACHE.keys()):
        if (tenant_id is None or k[0] == tenant_id) and (kind is None or k[1] == kind):
            _CACHE.pop(k, None)


def _serialize(payload: dict, *, include_points: bool) -> dict:
    out = {
        "kind": payload["kind"],
        "tenant": payload["tenant"],
        "projection_id": payload["projection_id"],
        "variance_explained": payload["variance_explained"],
        "count": len(payload["points"]),
    }
    if include_points:
        out["points"] = payload["points"]
    return out
