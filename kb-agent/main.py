import os
from pathlib import Path
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["GOOGLE_API_USE_MTLS_ENDPOINT"] = "never"
from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.background import BackgroundTask
import uvicorn

from agents.coordinator import coordinator_agent
from models.ontology import KnowledgeExtractionInput
from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
from services.tenant_context import get_tenant, set_tenant, set_search_scope, SHARED_TENANT, tenant_sql_filter, set_entity_scope
from services.cost_tracker import start_tracking, stop_tracking, save_cost_log, get_tracker

app = FastAPI(title="KnowledgeForge API", description="Graph RAG Backend Services via ADK")


# Demo mode banner — printed at import time so it shows in container logs.
_DEMO_MODE = (
    os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes")
    or bool(os.getenv("SPANNER_EMULATOR_HOST"))
)
if _DEMO_MODE:
    print("=" * 70)
    print("🧪 DEMO MODE ENABLED")
    print(f"   SPANNER_EMULATOR_HOST = {os.getenv('SPANNER_EMULATOR_HOST', '(unset)')}")
    print(f"   PROJECT/INSTANCE/DB   = "
          f"{os.getenv('SPANNER_PROJECT', os.getenv('GOOGLE_CLOUD_PROJECT', '?'))}/"
          f"{os.getenv('SPANNER_INSTANCE', '?')}/{os.getenv('SPANNER_DATABASE', '?')}")
    print(f"   GEMINI_API_KEY        = {'set' if os.getenv('GEMINI_API_KEY') else 'unset (LLM features degraded)'}")
    print("   Model Armor checks    = SKIPPED")
    print("=" * 70)
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        print("!" * 70)
        print("WARNING: DEMO_MODE is enabled but GEMINI_API_KEY/GOOGLE_API_KEY is not set.")
        print("         Git ingestion will be REJECTED with HTTP 503 until you export one.")
        print("         export GEMINI_API_KEY=... before docker compose up")
        print("!" * 70)


def _gemini_key_present() -> bool:
    """True iff a Gemini-compatible API key is exported. Used to gate LLM features."""
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


@app.get("/health")
def health():
    """Lightweight liveness endpoint used by the demo seed script."""
    return {"status": "ok", "demo_mode": _DEMO_MODE}


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract X-Tenant-Id and X-Search-Scope headers, set context for each request."""

    async def dispatch(self, request: Request, call_next):
        tenant_id = request.headers.get("X-Tenant-Id", "demo@local").split(",")[0].strip()
        scope = request.headers.get("X-Search-Scope", "all").split(",")[0].strip()
        datasets_raw = request.headers.get("X-Shared-Datasets", "")
        entity_scope_raw = request.headers.get("X-Entity-Scope", "")
        entity_scope_ids = [e.strip() for e in entity_scope_raw.split(",") if e.strip()] if entity_scope_raw else []
        set_entity_scope(entity_scope_ids)
        if request.url.path == "/copilotkit":
            print(f"[Middleware] {request.method} {request.url.path} | tenant={tenant_id} scope={scope} datasets={datasets_raw}")
        
        # Only update fallback tenant for CopilotKit requests to prevent clobbering by polling.
        update_fallback = "/copilotkit" in request.url.path
        set_tenant(tenant_id, update_fallback=update_fallback)
        
        # Only update search scope for CopilotKit requests (which carry the header).
        # Other endpoints (e.g. /tenant/costs polling) must NOT overwrite the scope,
        # because ADK's ThreadPoolExecutor doesn't propagate contextvars — the search
        # tool reads the global fallback, which would be clobbered by concurrent polls.
        if "/copilotkit" in request.url.path:
            if scope not in ("all", "mine", "shared"):
                scope = "all"
            set_search_scope(scope)
            datasets_header = request.headers.get("X-Shared-Datasets", "")
            if datasets_header.strip():
                from services.tenant_context import SHARED_ARCHISURANCE, SHARED_HOTPOTQA, set_shared_datasets
                dataset_map = {"archisurance": SHARED_ARCHISURANCE, "hotpotqa": SHARED_HOTPOTQA}
                selected = [dataset_map[d.strip()] for d in datasets_header.split(",") if d.strip() in dataset_map]
                set_shared_datasets(selected)
            else:
                from services.tenant_context import set_shared_datasets, ALL_SHARED_DATASETS
                set_shared_datasets(list(ALL_SHARED_DATASETS))

        # Start per-request cost tracking
        start_tracking()

        response = await call_next(request)

        # Save cost log for POST operations in a background task (non-blocking)
        tracker = stop_tracking()
        if tracker and request.method == "POST" and tracker.total_cost_usd > 0:
            path = request.url.path
            if "/copilotkit/ingestion" in path or "/upload-document" in path:
                op_type = "ingestion"
            elif "/copilotkit" in path:
                op_type = "query"
            else:
                op_type = "other"

            # Chain background task so it runs after the response is sent
            existing_bg = response.background
            async def _save_cost(tid, otype, trk, prev_bg):
                try:
                    save_cost_log(tid, otype, "", trk)
                except Exception:
                    pass
                # Run any pre-existing background task
                if prev_bg:
                    await prev_bg()
            response.background = BackgroundTask(_save_cost, tenant_id, op_type, tracker, existing_bg)

        return response


app.add_middleware(TenantMiddleware)

# Spanner connection (lazy init on first use via services/spanner_client.py)

# Initialize Agents
from agents.processing import processing_agent

adk_coordinator_agent = ADKAgent(
    adk_agent=coordinator_agent,
    app_name="knowledgeforge_app",
    user_id="demo_user",
    session_timeout_seconds=3600,
    use_in_memory_services=True
)

adk_ingestion_agent = ADKAgent(
    adk_agent=processing_agent,
    app_name="knowledgeforge_ingestion_app",
    user_id="demo_user",
    session_timeout_seconds=3600,
    use_in_memory_services=True
)

# Register ADK agent endpoints
add_adk_fastapi_endpoint(
    app, 
    adk_coordinator_agent, 
    path="/copilotkit", 
    extract_headers=["X-Tenant-Id", "X-Search-Scope", "X-Shared-Datasets", "X-Entity-Scope"]
)
add_adk_fastapi_endpoint(app, adk_ingestion_agent, path="/copilotkit/ingestion")

class QueryRequest(BaseModel):
    query: str

class DocumentUpload(BaseModel):
    text: str
    fileName: str = ""
    images: list = []

# In-memory store for the full document text (used by chunker, bypasses LLM token limit)
_uploaded_document: dict | None = None

@app.post("/upload-document")
def upload_document(doc: DocumentUpload):
    """Receive full document text for chunking (pre-LLM)."""
    global _uploaded_document
    _uploaded_document = {
        "text": doc.text,
        "fileName": doc.fileName,
        "images": doc.images,
        "tenant_id": get_tenant(),
    }
    # Make it available to processing.py
    from agents import processing
    processing._full_document_text = doc.text
    processing._full_document_images = doc.images
    return {"status": "ok", "chars": len(doc.text), "images": len(doc.images)}

class ParseRequest(BaseModel):
    gcs_uri: str = ""          # gs://bucket/path for GCS-based parsing
    output_prefix: str = "parsed/"

DOCLING_URL = os.getenv("DOCLING_URL")

@app.post("/parse-document")
async def parse_document_via_docling(file: bytes = None):
    """Parse a document via the Docling microservice.

    Accepts multipart file upload, forwards to Docling, returns structured text.
    For GCS-based parsing, use /parse-document/gcs.
    """
    import httpx
    import google.auth.transport.requests
    import google.auth

    # Get identity token for service-to-service auth
    try:
        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token
    except Exception:
        token = None

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Forward request to Docling
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            # Re-read from the uploaded document store
            if _uploaded_document:
                # Send as text (Docling will handle it)
                response = await client.post(
                    f"{DOCLING_URL}/parse",
                    files={"file": (_uploaded_document.get("fileName", "doc.txt"),
                                   _uploaded_document["text"].encode(), "text/plain")},
                    data={"output_format": "markdown"},
                    headers=headers,
                )
            else:
                return {"error": "No document uploaded. Use /upload-document first."}

            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "ok",
                    "text": data.get("text", ""),
                    "tables": data.get("tables", []),
                    "metadata": data.get("metadata", {}),
                }
            else:
                return {"error": f"Docling returned {response.status_code}: {response.text[:200]}"}
    except Exception as e:
        return {"error": f"Docling call failed: {str(e)[:200]}"}

@app.post("/parse-document/gcs")
async def parse_from_gcs(req: ParseRequest):
    """Parse a document from GCS via Docling, write result back to GCS."""
    import httpx
    import google.auth.transport.requests
    import google.auth

    if not req.gcs_uri.startswith("gs://"):
        raise HTTPException(400, "gcs_uri must start with gs://")

    try:
        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        headers = {"Authorization": f"Bearer {credentials.token}"}
    except Exception:
        headers = {}

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{DOCLING_URL}/parse/gcs",
                data={"gcs_uri": req.gcs_uri, "output_prefix": req.output_prefix},
                headers=headers,
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(response.status_code, response.text[:200])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Docling GCS parse failed: {str(e)[:200]}")

@app.post("/reset-graph")
def reset_knowledge_graph():
    """Clear Knowledge Graph data for the current tenant from Spanner (testing only)."""
    try:
        from services.spanner_client import get_database
        from google.cloud.spanner_v1 import param_types
        database = get_database()
        tenant_id = get_tenant()
        if tenant_id == SHARED_TENANT:
            raise HTTPException(status_code=403, detail="Cannot reset shared tenant data")
        tables_ordered = [
            "ChunkMentions", "DocumentChunks", "DocumentMentions",
            "Composition", "Aggregation", "Assignment", "Realization",
            "Serving", "Access", "Influence", "Association",
            "Triggering", "Flow", "Specialization",
            "ApplicationComponents", "ApplicationServices", "ApplicationInterfaces",
            "DataObjects", "BusinessActors", "BusinessRoles", "BusinessProcesses",
            "BusinessFunctions", "BusinessServices", "BusinessObjects", "Contracts",
            "Nodes", "Devices", "SystemSoftwares", "TechnologyServices",
            "Artifacts", "CommunicationNetworks",
            "Goals", "Requirements", "Constraints", "Stakeholders", "Capabilities",
            "Documents",
        ]
        def delete_tenant_data(transaction):
            for table in tables_ordered:
                transaction.execute_update(
                    f"DELETE FROM {table} WHERE tenant_id = @tenant_id",
                    params={"tenant_id": tenant_id},
                    param_types={"tenant_id": param_types.STRING},
                )
        database.run_in_transaction(delete_tenant_data)
        return {"status": "success", "message": f"Knowledge Graph reset for tenant {tenant_id} ({len(tables_ordered)} tables)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/image/{doc_id}/{chunk_id}")
def get_chunk_image(doc_id: str, chunk_id: str):
    """Retrieve the binary image for a specific image chunk from Spanner."""
    from services.spanner_client import get_database
    from google.cloud.spanner_v1 import param_types
    import base64

    tenant_id = get_tenant()
    database = get_database()
    with database.snapshot() as snapshot:
        result = snapshot.execute_sql(
            "SELECT image_uri FROM DocumentChunks "
            "WHERE doc_id = @doc_id AND chunk_id = @chunk_id AND chunk_type = 'image' "
            f"AND {tenant_sql_filter()}",
            params={"doc_id": doc_id, "chunk_id": chunk_id, "_tid": tenant_id},
            param_types={
                "doc_id": param_types.STRING,
                "chunk_id": param_types.STRING,
                "_tid": param_types.STRING,
            },
        )
        rows = list(result)
        if not rows or not rows[0][0]:
            raise HTTPException(status_code=404, detail="Image not found")

        image_uri = rows[0][0]  # data:image/png;base64,...
        try:
            header, b64data = image_uri.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0]
        except (ValueError, IndexError):
            mime_type = "image/png"
            b64data = image_uri

        image_bytes = base64.b64decode(b64data)
        from fastapi.responses import Response
        return Response(
            content=image_bytes,
            media_type=mime_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )


# ── Graph Analytics Endpoints ──

@app.get("/graph/god-nodes")
def god_nodes(top_n: int = 10):
    """Return the most-connected entities in the knowledge graph."""
    from services.spanner_client import get_database
    from services.graph_analytics import get_god_nodes
    return get_god_nodes(get_database(), top_n, tenant_id=get_tenant())


@app.get("/graph/stats")
def graph_stats():
    """Return aggregate statistics for the knowledge graph."""
    from services.spanner_client import get_database
    from services.graph_analytics import get_graph_stats
    return get_graph_stats(get_database(), tenant_id=get_tenant())


@app.get("/graph/brief")
def knowledge_brief():
    """Generate a structured knowledge brief for AI agent consumption."""
    from services.spanner_client import get_database
    from services.knowledge_brief import generate_brief
    return {"brief": generate_brief(get_database(), tenant_id=get_tenant())}


@app.get("/graph/entity/{entity_type}/{entity_name}")
def get_entity(entity_type: str, entity_name: str):
    """Look up an entity by type and name."""
    from services.spanner_client import get_database
    from services.schema_registry import ENTITY_TABLE_MAP, ARCHIMATE_LAYER_MAP
    from google.cloud.spanner_v1 import param_types

    tinfo = ENTITY_TABLE_MAP.get(entity_type)
    if not tinfo:
        raise HTTPException(404, f"Unknown entity type: {entity_type}")

    tenant_id = get_tenant()
    database = get_database()
    with database.snapshot() as snap:
        rows = snap.execute_sql(
            f"SELECT {tinfo['id_col']}, {tinfo['name_col']}, description, archimate_layer, source_doc_id "
            f"FROM {tinfo['table']} WHERE LOWER({tinfo['name_col']}) = LOWER(@name) "
            f"AND {tenant_sql_filter()} LIMIT 1",
            params={"name": entity_name, "_tid": tenant_id},
            param_types={"name": param_types.STRING, "_tid": param_types.STRING},
        )
        for r in rows:
            return {
                "entity_id": r[0], "name": r[1], "type": entity_type,
                "description": r[2] or "", "layer": r[3] or ARCHIMATE_LAYER_MAP.get(entity_type, ""),
                "source_doc_id": r[4] or "",
            }
    raise HTTPException(404, f"Entity not found: {entity_type}:{entity_name}")


@app.get("/graph/connections/{entity_id}")
def get_connections(entity_id: str):
    """Get 1-hop connections for an entity across all edge tables."""
    from services.spanner_client import get_database
    from services.schema_registry import EDGE_TABLE_MAP
    from google.cloud.spanner_v1 import param_types

    tenant_id = get_tenant()
    database = get_database()
    connections = []
    for rel_type, einfo in EDGE_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                # Outgoing
                rows = snap.execute_sql(
                    f"SELECT target_id, target_type, {einfo['detail_col']}, confidence "
                    f"FROM {einfo['table']} WHERE source_id = @eid "
                    f"AND {tenant_sql_filter()}",
                    params={"eid": entity_id, "_tid": tenant_id},
                    param_types={"eid": param_types.STRING, "_tid": param_types.STRING},
                )
                for r in rows:
                    connections.append({
                        "direction": "outgoing", "relationship": rel_type,
                        "target_id": r[0], "target_type": r[1],
                        "detail": r[2] or "", "confidence": r[3] or "EXTRACTED",
                    })
            with database.snapshot() as snap:
                # Incoming
                rows = snap.execute_sql(
                    f"SELECT source_id, source_type, {einfo['detail_col']}, confidence "
                    f"FROM {einfo['table']} WHERE target_id = @eid "
                    f"AND {tenant_sql_filter()}",
                    params={"eid": entity_id, "_tid": tenant_id},
                    param_types={"eid": param_types.STRING, "_tid": param_types.STRING},
                )
                for r in rows:
                    connections.append({
                        "direction": "incoming", "relationship": rel_type,
                        "source_id": r[0], "source_type": r[1],
                        "detail": r[2] or "", "confidence": r[3] or "EXTRACTED",
                    })
        except Exception:
            pass
    return {"entity_id": entity_id, "connections": connections, "total": len(connections)}


@app.get("/graph/conformance")
def conformance_check():
    """Validate the knowledge graph against architecture and data governance rules."""
    from services.spanner_client import get_database
    from services.graph_analytics import check_conformance
    return check_conformance(get_database(), tenant_id=get_tenant())


@app.get("/graph/impact/{entity_type}/{entity_name}")
def impact_analysis_endpoint(entity_type: str, entity_name: str, max_hops: int = 4):
    """Calculate blast radius from an entity through all relationship layers."""
    from services.spanner_client import get_database
    from services.graph_analytics import impact_analysis
    return impact_analysis(get_database(), entity_name, entity_type, max_hops, tenant_id=get_tenant())


# ── Graph Navigation Endpoints (UI graph explorer) ──

@app.get("/graph/all")
def graph_all(
    layer: str = "",
    entity_type: str = "",
    confidence: str = "",
    document_id: str = "",
    limit: int = 500,
    offset: int = 0,
):
    """Page through the tenant's graph with optional layer/type/document filters.

    All filters are comma-separated CSVs. ``limit`` is hard-capped at 5000 to
    keep the UI responsive; the response carries ``has_more`` so the caller
    can paginate.
    """
    from services.spanner_client import get_database
    from services.graph_navigation import list_entities, list_edges_for_nodes

    if limit > 5000:
        limit = 5000
    if limit <= 0:
        limit = 500
    if offset < 0:
        offset = 0

    layers = [l.strip() for l in layer.split(",") if l.strip()] or None
    types = [t.strip() for t in entity_type.split(",") if t.strip()] or None
    confs = [c.strip() for c in confidence.split(",") if c.strip()] or None
    doc_id = document_id.strip() or None

    database = get_database()
    page = list_entities(
        database,
        layers=layers,
        entity_types=types,
        confidences=confs,
        document_id=doc_id,
        limit=limit,
        offset=offset,
        tenant_id=get_tenant(),
    )
    node_ids = [n["entity_id"] for n in page["nodes"]]
    edges = list_edges_for_nodes(database, node_ids, confidences=confs, tenant_id=get_tenant())
    return {
        "nodes": page["nodes"],
        "edges": edges,
        "total_nodes": page["total"],
        "total_edges": len(edges),
        "has_more": page["has_more"],
    }


@app.get("/graph/search")
def graph_search(q: str, entity_type: str = "", limit: int = 20):
    """Case-insensitive entity search. Supports CSV ``entity_type`` filter."""
    from services.spanner_client import get_database
    from services.graph_navigation import search_entities

    if not q or not q.strip():
        return {"matches": []}
    types = [t.strip() for t in entity_type.split(",") if t.strip()] or None
    matches = search_entities(
        get_database(), q, entity_types=types, limit=limit, tenant_id=get_tenant()
    )
    return {"matches": matches}


@app.get("/graph/neighborhood/{entity_id}")
def graph_neighborhood(entity_id: str, hops: int = 2, max_per_hop: int = 20):
    """Return a sub-graph of all nodes reachable from ``entity_id`` within ``hops`` steps."""
    from services.spanner_client import get_database
    from services.graph_navigation import get_neighborhood

    return get_neighborhood(
        get_database(), entity_id, hops=hops, max_per_hop=max_per_hop, tenant_id=get_tenant()
    )


@app.get("/embeddings/projection")
def embeddings_projection(kind: str = "entities", limit: int = 1500, refresh: bool = False):
    """3D PCA projection of stored embeddings (entities or chunks).

    Caches per (tenant, kind). Pass ``refresh=true`` after a fresh ingest.
    """
    from services.spanner_client import get_database
    from services.embedding_projection import compute_projection

    if kind not in ("entities", "chunks"):
        raise HTTPException(status_code=400, detail="kind must be 'entities' or 'chunks'")
    return compute_projection(
        get_database(),
        kind=kind,
        limit=max(20, min(limit, 5000)),
        tenant_id=get_tenant(),
        force_refresh=refresh,
    )


@app.post("/embeddings/project_query")
def embeddings_project_query(payload: dict):
    """Embed ``payload['q']`` and project into the cached PCA space (same kind)."""
    from services.embedding_projection import project_query_vector
    from services.document_chunker import compute_entity_embeddings

    q = (payload or {}).get("q", "").strip()
    kind = (payload or {}).get("kind", "entities")
    if not q:
        raise HTTPException(status_code=400, detail="missing 'q'")
    try:
        emb = compute_entity_embeddings([{"name": q}])[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"embed failed: {e}")
    return project_query_vector(emb, kind=kind, tenant_id=get_tenant())


@app.post("/embeddings/nearest")
def embeddings_nearest(payload: dict):
    """Embed ``payload['q']`` and return projected query + cosine top-K hits."""
    from services.embedding_projection import nearest_to_query
    from services.document_chunker import compute_entity_embeddings

    q = (payload or {}).get("q", "").strip()
    kind = (payload or {}).get("kind", "entities")
    top_k = int((payload or {}).get("top_k", 30))
    if not q:
        raise HTTPException(status_code=400, detail="missing 'q'")
    try:
        emb = compute_entity_embeddings([{"name": q}])[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"embed failed: {e}")
    return nearest_to_query(emb, kind=kind, tenant_id=get_tenant(), top_k=top_k)


@app.get("/documents/list")
def documents_list():
    """Return distinct documents (id + title) for the current tenant.

    Used by the document picker in the graph navigation UI.
    """
    from services.spanner_client import get_database
    from services.tenant_context import tenant_sql_filter_for
    from google.cloud.spanner_v1 import param_types

    tenant_id = get_tenant()
    database = get_database()
    docs: list[dict] = []
    try:
        with database.snapshot() as snap:
            sql = (
                "SELECT doc_id, title FROM Documents "
                f"WHERE {tenant_sql_filter_for(database, 'Documents')} "
                "ORDER BY title"
            )
            for r in snap.execute_sql(
                sql,
                params={"_tid": tenant_id},
                param_types={"_tid": param_types.STRING},
            ):
                docs.append({"doc_id": r[0], "title": r[1] or r[0]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"documents": docs, "total": len(docs)}


@app.get("/tenant/stats")
def tenant_stats():
    """Return lightweight counts of documents, chunks, entities, and edges for the current tenant."""
    from services.spanner_client import get_database
    from services.tenant_context import _has_tenant_id_column
    from google.cloud.spanner_v1 import param_types

    tenant_id = get_tenant()
    database = get_database()

    entity_tables = ["ApplicationComponents", "BusinessProcesses", "SystemSoftwares"]

    try:
        def _count(sql, params=None, param_types_map=None):
            with database.snapshot() as snap:
                return list(snap.execute_sql(sql, params=params or {}, param_types=param_types_map or {}))[0][0]

        _p = {"tid": tenant_id}
        _pt = {"tid": param_types.STRING}
        _sp = {"prefix": "__shared__"}
        _spt = {"prefix": param_types.STRING}

        # Build per-table count safely: when a target table has not yet had the
        # tenant_id migration applied (e.g. a fresh emulator schema), fall back
        # to an unfiltered COUNT(*) instead of crashing with
        # "Unrecognized name: tenant_id".
        def _count_tenant(table: str) -> int:
            if _has_tenant_id_column(database, table):
                return _count(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = @tid", _p, _pt)
            return _count(f"SELECT COUNT(*) FROM {table}")

        def _count_shared(table: str) -> int:
            if _has_tenant_id_column(database, table):
                return _count(
                    f"SELECT COUNT(*) FROM {table} WHERE STARTS_WITH(tenant_id, @prefix)",
                    _sp, _spt,
                )
            return 0

        documents = _count_tenant("Documents")
        chunks = _count_tenant("DocumentChunks")

        entities = 0
        for tbl in entity_tables:
            entities += _count_tenant(tbl)

        edges = _count_tenant("Composition")
        shared_documents = _count_shared("Documents")
        shared_chunks = _count_shared("DocumentChunks")

        return {
            "tenant_id": tenant_id,
            "documents": documents,
            "chunks": chunks,
            "entities": entities,
            "edges": edges,
            "shared_documents": shared_documents,
            "shared_chunks": shared_chunks,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tenant/latest-metadata")
def tenant_latest_metadata():
    """Retrieve the last turn's structured metadata out-of-band."""
    from services.tenant_context import get_tenant
    import agents.coordinator as _coord
    tenant_id = get_tenant()
    meta = getattr(_coord, "_LATEST_TURN_METADATA", {}).get(tenant_id)
    if not meta:
        meta = getattr(_coord, "_LATEST_TURN_METADATA", {}).get("LATEST", {})
    return meta


@app.get("/tenant/costs")
def tenant_costs():
    """Return cost breakdown for the current tenant (all-time and last 30 days)."""
    from services.spanner_client import get_database
    from google.cloud.spanner_v1 import param_types

    tenant_id = get_tenant()
    database = get_database()

    base_sql = (
        "SELECT operation_type, COUNT(*) AS ops, "
        "SUM(total_cost_usd) AS cost, "
        "SUM(input_tokens) AS input_tok, "
        "SUM(output_tokens) AS output_tok "
        "FROM CostLog WHERE tenant_id = @tid"
    )
    group_by = " GROUP BY operation_type"

    def _parse_rows(rows) -> dict:
        """Build cost summary dict from grouped rows."""
        total_cost = 0.0
        by_type = {}
        for row in rows:
            op_type = row[0] or "other"
            ops = row[1] or 0
            cost = float(row[2] or 0)
            input_tok = row[3] or 0
            output_tok = row[4] or 0
            total_cost += cost
            by_type[op_type] = {
                "operations": ops,
                "cost_usd": round(cost, 6),
                "input_tokens": input_tok,
                "output_tokens": output_tok,
            }
        return {"total_cost_usd": round(total_cost, 6), **by_type}

    try:
        with database.snapshot() as snapshot:
            # All-time costs
            all_time_rows = list(snapshot.execute_sql(
                base_sql + group_by,
                params={"tid": tenant_id},
                param_types={"tid": param_types.STRING},
            ))

            # Last 30 days
            last30_rows = list(snapshot.execute_sql(
                base_sql
                + " AND created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)"
                + group_by,
                params={"tid": tenant_id},
                param_types={"tid": param_types.STRING},
            ))

            # Per-day series (last 30 days)
            by_day_rows = list(snapshot.execute_sql(
                "SELECT EXTRACT(DATE FROM created_at) AS day, "
                "SUM(total_cost_usd) AS cost, COUNT(*) AS ops "
                "FROM CostLog WHERE tenant_id = @tid "
                "AND created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY) "
                "GROUP BY day ORDER BY day",
                params={"tid": tenant_id},
                param_types={"tid": param_types.STRING},
            ))
            by_day = [
                {"day": str(r[0]), "cost_usd": round(float(r[1] or 0), 6), "operations": r[2] or 0}
                for r in by_day_rows
            ]

        return {
            "tenant_id": tenant_id,
            "all_time": _parse_rows(all_time_rows),
            "last_30_days": _parse_rows(last30_rows),
            "by_day": by_day,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tenant/dashboard")
def tenant_dashboard():
    """Aggregated multi-tenant cost dashboard.

    Returns:
      - top_tenants: top 10 tenants by total cost (last 30d)
      - daily_trend: per-day total cost for the last 7 days
      - op_type_breakdown: cost grouped by operation_type for the current tenant
      - tenant_id: the calling tenant (for context)

    Note: top_tenants and daily_trend aggregate across ALL tenants — this
    endpoint is intended for administrative dashboards. Per-tenant scoping
    of /tenant/costs remains the right call for end-user views.
    """
    from services.spanner_client import get_database
    from google.cloud.spanner_v1 import param_types

    tenant_id = get_tenant()
    database = get_database()

    try:
        with database.snapshot(multi_use=True) as snapshot:
            # Top 10 tenants by cost over last 30 days
            top_rows = list(snapshot.execute_sql(
                "SELECT tenant_id, SUM(total_cost_usd) AS cost, COUNT(*) AS ops "
                "FROM CostLog "
                "WHERE created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY) "
                "GROUP BY tenant_id ORDER BY cost DESC LIMIT 10"
            ))
            top_tenants = [
                {"tenant_id": r[0], "cost_usd": round(float(r[1] or 0), 6), "operations": r[2] or 0}
                for r in top_rows
            ]

            # Daily trend (last 7 days, all tenants)
            daily_rows = list(snapshot.execute_sql(
                "SELECT EXTRACT(DATE FROM created_at) AS day, "
                "SUM(total_cost_usd) AS cost, COUNT(*) AS ops "
                "FROM CostLog "
                "WHERE created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) "
                "GROUP BY day ORDER BY day"
            ))
            daily_trend = [
                {"day": str(r[0]), "cost_usd": round(float(r[1] or 0), 6), "operations": r[2] or 0}
                for r in daily_rows
            ]

            # Op-type breakdown for the calling tenant
            op_rows = list(snapshot.execute_sql(
                "SELECT operation_type, SUM(total_cost_usd) AS cost, COUNT(*) AS ops "
                "FROM CostLog WHERE tenant_id = @tid GROUP BY operation_type",
                params={"tid": tenant_id},
                param_types={"tid": param_types.STRING},
            ))
            op_breakdown = [
                {"op_type": r[0] or "other", "cost_usd": round(float(r[1] or 0), 6), "operations": r[2] or 0}
                for r in op_rows
            ]

        return {
            "tenant_id": tenant_id,
            "top_tenants": top_tenants,
            "daily_trend": daily_trend,
            "op_type_breakdown": op_breakdown,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Git Repository Ingestion ─────────────────────────────────────────────

# In-memory job registry. Job state lives only for the lifetime of the
# process; durable progress flows through the existing AG-UI SSE channel
# emitted by ProcessingAgent (matched on tool-call name in the frontend).
_GIT_INGEST_JOBS: dict[str, dict] = {}
# Document upload jobs (POST /ingest/document). Same shape as _GIT_INGEST_JOBS
# so the unified /ingest/{job_id}/* handlers can serve either source.
_DOC_INGEST_JOBS: dict[str, dict] = {}


def _lookup_job(job_id: str) -> dict | None:
    """Return the job entry from whichever registry holds it.

    Used by the source-agnostic /ingest/{job_id}/* handlers so callers can
    use the same SSE / artifact endpoints regardless of whether the job
    came in via /ingest/git or /ingest/document.
    """
    return _GIT_INGEST_JOBS.get(job_id) or _DOC_INGEST_JOBS.get(job_id)

DEFAULT_GIT_INCLUDE = [
    "**/*.py", "**/*.ts", "**/*.tsx",
    "**/*.java", "**/*.go", "**/*.sql",
]
DEFAULT_GIT_EXCLUDE = [
    "node_modules/**", "dist/**", "build/**",
    ".git/**", "**/__pycache__/**",
    "vendor/**", "target/**",
]

_GIT_URL_RE = None

def _looks_like_git_url(url: str) -> bool:
    import re
    global _GIT_URL_RE
    if _GIT_URL_RE is None:
        _GIT_URL_RE = re.compile(
            r"^(https?://[^\s]+|git@[^\s:]+:[^\s]+|ssh://[^\s]+|file://[^\s]+)$"
        )
    return bool(_GIT_URL_RE.match(url.strip()))


class GitIngestRequest(BaseModel):
    """Request body for POST /ingest/git.

    Fields
    ------
    repo_url:
        HTTPS or SSH URL of the repository to clone. Required.
    ref:
        Optional branch / tag / commit. Defaults to the repo default branch.
    include:
        Glob patterns (relative to clone root) of files to ingest.
        Defaults to a polyglot set covering Python/TS/Java/Go/SQL.
    exclude:
        Glob patterns to subtract. Defaults skip vendor / build dirs.
    """
    repo_url: str = Field(..., min_length=4)
    ref: str | None = None
    include: list[str] | None = None
    exclude: list[str] | None = None

    @field_validator("repo_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip()
        if not _looks_like_git_url(v):
            raise ValueError(
                "repo_url must be an http(s)://, ssh://, or git@host:path URL"
            )
        return v


def _run_git_ingest(job_id: str, body: "GitIngestRequest", tenant_id: str) -> None:
    """Background runner: instantiate GitIngester and persist the summary.

    Progress events from downstream tool calls (graph extraction, Spanner
    writes) are emitted on the existing AG-UI SSE channel, so the UI can
    reuse the same pipeline component used for PDF ingestion.
    """
    from services.git_ingester import GitIngester
    from services.tenant_context import set_tenant
    from services import event_bus
    from services.artifact_store import store as _artifact_store
    set_tenant(tenant_id, update_fallback=True)
    job = _GIT_INGEST_JOBS.setdefault(job_id, {})
    job.update({"status": "running", "repo_url": body.repo_url, "ref": body.ref})
    try:
        summary = GitIngester(
            repo_url=body.repo_url,
            ref=body.ref,
            include=body.include or DEFAULT_GIT_INCLUDE,
            exclude=body.exclude or DEFAULT_GIT_EXCLUDE,
            tenant_id=tenant_id,
            event_callback=lambda et, d: event_bus.publish(job_id, et, d),
            artifact_callback=lambda fp, payload: _artifact_store.put(job_id, fp, payload),
        ).ingest()
        # Per-file failures are collected into summary["errors"] rather than
        # raised. If any are present, treat the whole job as failed so the
        # caller does not see status=complete on a silently-empty graph.
        errors = summary.get("errors") or []
        if errors:
            job.update({
                "status": "failed",
                "summary": summary,
                "error_count": len(errors),
                "error": f"{len(errors)} file(s) failed during ingestion",
                "error_samples": errors[:3],
            })
            event_bus.publish(job_id, "failed", {
                "error": f"{len(errors)} file(s) failed during ingestion",
                "error_samples": errors[:3],
                "summary": summary,
            })
        else:
            job.update({"status": "complete", "summary": summary})
            event_bus.publish(job_id, "complete", {"summary": summary})
    except Exception as e:  # noqa: BLE001 — surface error in job status
        job.update({"status": "failed", "error": str(e)})
        event_bus.publish(job_id, "failed", {"error": str(e)})
    finally:
        event_bus.close(job_id)
        _artifact_store.mark_closed(job_id)


@app.post("/ingest/git", status_code=202)
def ingest_git(body: GitIngestRequest, background_tasks: BackgroundTasks):
    """Trigger asynchronous Git repository ingestion.

    Contract
    --------
    Request JSON:
        {
          "repo_url": "https://github.com/org/repo.git",   # required
          "ref":      "main",                              # optional
          "include":  ["**/*.py", "**/*.ts", ...],         # optional
          "exclude":  ["node_modules/**", ...]             # optional
        }

    Response (202 Accepted):
        {"job_id": "<uuid>", "status": "queued"}

    The actual pipeline runs in a FastAPI BackgroundTask. Per-step progress
    is broadcast on the existing AG-UI SSE channel under /copilotkit/ingestion;
    the frontend already taps that stream to drive the pipeline UI.
    Poll GET /ingest/git/{job_id} for terminal status + summary dict.
    """
    # In DEMO_MODE, entity extraction requires a Gemini key. Reject the job
    # up-front rather than accept-and-silently-produce-zero-entities.
    if _DEMO_MODE and not _gemini_key_present():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "GEMINI_API_KEY required for entity extraction in DEMO_MODE",
                "hint": "set GEMINI_API_KEY in your shell before docker compose up",
            },
        )
    import uuid
    job_id = uuid.uuid4().hex
    _GIT_INGEST_JOBS[job_id] = {"status": "queued", "repo_url": body.repo_url}
    background_tasks.add_task(_run_git_ingest, job_id, body, get_tenant())
    return {"job_id": job_id, "status": "queued"}


@app.get("/ingest/git/{job_id}")
def ingest_git_status(job_id: str):
    """Return the current status / summary for a Git ingestion job."""
    job = _GIT_INGEST_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    return {"job_id": job_id, **job}


async def _ingest_events_handler(job_id: str, request: Request):
    """Source-agnostic SSE handler for /ingest/{job_id}/events.

    Both /ingest/git/{job_id}/events (legacy) and /ingest/{job_id}/events
    delegate here. The job_id may belong to either the git or document
    upload registry; lookup is done via `_lookup_job`.
    """
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    from services import event_bus

    if _lookup_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

    HEARTBEAT_S = 15.0

    async def gen():
        agen = event_bus.subscribe(job_id).__aiter__()
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    et, data = await asyncio.wait_for(agen.__anext__(), timeout=HEARTBEAT_S)
                except asyncio.TimeoutError:
                    # SSE comment line — keeps proxies (nginx, cloudflare) from
                    # closing the connection on idle.
                    yield ": heartbeat\n\n"
                    continue
                except StopAsyncIteration:
                    return
                yield f"event: {et}\ndata: {json.dumps(data)}\n\n"
        finally:
            await agen.aclose()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


def _ingest_file_handler(job_id: str, path: str):
    """Source-agnostic per-file artifact handler.

    Returns the inspector payload (source + parsed + entities/edges) for the
    given (job_id, path). Used by both /ingest/git/{job_id}/file and
    /ingest/{job_id}/file.
    """
    from services.artifact_store import store as _artifact_store
    if _lookup_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    payload = _artifact_store.get(job_id, path)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"No artifact for path={path!r} in job {job_id}",
        )
    return payload


@app.get("/ingest/git/{job_id}/events")
async def ingest_git_events(job_id: str, request: Request):
    """SSE stream — legacy alias kept for clients that hardcoded /ingest/git."""
    return await _ingest_events_handler(job_id, request)


@app.get("/ingest/git/{job_id}/file")
def ingest_git_file(job_id: str, path: str):
    """Per-file artifact — legacy alias kept for clients that hardcoded /ingest/git."""
    return _ingest_file_handler(job_id, path)


@app.get("/ingest/{job_id}/events")
async def ingest_events(job_id: str, request: Request):
    """Source-agnostic SSE stream of ingestion progress (git or document)."""
    return await _ingest_events_handler(job_id, request)


@app.get("/ingest/{job_id}/file")
def ingest_file(job_id: str, path: str):
    """Source-agnostic per-file artifact (source + parsed + entities/edges)."""
    return _ingest_file_handler(job_id, path)


@app.get("/ingest/{job_id}/file/raw")
def ingest_file_raw(job_id: str, path: str):
    """Stream the raw uploaded bytes (e.g. PDF) for `<embed>` rendering.

    Only populated for binary uploads (PDF/DOCX) ingested via /ingest/document;
    git artifacts are text and accessible via the standard /file endpoint.
    """
    from fastapi.responses import FileResponse
    from services import raw_artifact_store
    if _lookup_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    fp = raw_artifact_store.get_path(job_id, path)
    if fp is None:
        raise HTTPException(
            status_code=404,
            detail=f"No raw bytes for path={path!r} in job {job_id}",
        )
    suffix = fp.suffix.lower()
    media_type = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(suffix, "application/octet-stream")
    return FileResponse(str(fp), media_type=media_type, filename=Path(path).name)


# ── Document Upload Ingestion (POST /ingest/document) ────────────────────

class DocumentIngestRequest(BaseModel):
    """JSON body for POST /ingest/document (text-only path).

    Multipart uploads with a `file` field are handled separately and do not
    go through this model. When using JSON, supply at minimum `text` and
    `fileName`; `images` is accepted for compatibility with /upload-document
    but is currently not propagated to the new pipeline.
    """
    text: str = ""
    fileName: str = "document.txt"
    images: list = Field(default_factory=list)


def _run_document_ingest(
    job_id: str,
    file_name: str,
    text: str | None,
    raw_bytes: bytes | None,
    tenant_id: str,
) -> None:
    """Background runner for POST /ingest/document.

    Mirrors `_run_git_ingest`: publishes route/parse_start/parse_end/
    write_start/write_end/complete (or failed) on the unified event_bus and
    stashes the per-file artifact in artifact_store. Raw bytes (PDF/DOCX)
    additionally land in raw_artifact_store so the frontend can `<embed>`
    the original.
    """
    from services import event_bus, raw_artifact_store
    from services.artifact_store import store as _artifact_store
    from services.document_ingester import run_document_ingest
    from services.tenant_context import set_tenant
    set_tenant(tenant_id, update_fallback=True)
    job = _DOC_INGEST_JOBS.setdefault(job_id, {})
    job.update({"status": "running", "file": file_name})
    try:
        summary = run_document_ingest(
            job_id=job_id,
            file_name=file_name,
            text=text,
            raw_bytes=raw_bytes,
            tenant_id=tenant_id,
            event_callback=lambda et, d: event_bus.publish(job_id, et, d),
            artifact_callback=lambda fp, payload: _artifact_store.put(job_id, fp, payload),
            raw_callback=lambda fp, data: raw_artifact_store.put(job_id, fp, data),
        )
        job.update({"status": "complete", "summary": summary})
        event_bus.publish(job_id, "complete", {"summary": summary})
    except Exception as e:  # noqa: BLE001
        job.update({"status": "failed", "error": str(e)})
        event_bus.publish(job_id, "failed", {"error": str(e)})
    finally:
        event_bus.close(job_id)
        _artifact_store.mark_closed(job_id)
        raw_artifact_store.mark_closed(job_id)


@app.post("/ingest/document", status_code=202)
async def ingest_document(request: Request, background_tasks: BackgroundTasks):
    """Trigger asynchronous document ingestion (PDF/DOCX/MD/TXT).

    Accepts either:
      - multipart/form-data with a `file` field (binary upload), or
      - application/json `{text, fileName, images?}` (browser-extracted text).

    Returns 202 with `{job_id, status}` immediately; progress is delivered on
    GET /ingest/{job_id}/events using the same event names as /ingest/git so
    the frontend AgentTimeline component is reused unchanged.
    """
    import uuid
    job_id = uuid.uuid4().hex

    file_name = "document"
    text: str | None = None
    raw_bytes: bytes | None = None

    ctype = (request.headers.get("content-type") or "").lower()
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=400, detail="multipart request missing 'file'")
        raw_bytes = await upload.read()
        file_name = getattr(upload, "filename", None) or "document"
        # Optional caller-supplied text (when the browser already extracted it).
        text_field = form.get("text")
        if text_field:
            text = str(text_field)
    else:
        try:
            body = DocumentIngestRequest(**(await request.json()))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid request body: {e}")
        if not body.text and not body.fileName:
            raise HTTPException(status_code=400, detail="provide text or upload a file")
        file_name = body.fileName or "document.txt"
        text = body.text or None

    _DOC_INGEST_JOBS[job_id] = {"status": "queued", "file": file_name}
    background_tasks.add_task(
        _run_document_ingest, job_id, file_name, text, raw_bytes, get_tenant(),
    )
    return {"job_id": job_id, "status": "queued"}


@app.get("/ingest/document/{job_id}")
def ingest_document_status(job_id: str):
    """Return current status / summary for a document ingestion job."""
    job = _DOC_INGEST_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    return {"job_id": job_id, **job}


@app.post("/ingest")
def trigger_ingestion(input_data: KnowledgeExtractionInput):
    """
    Trigger the ingestion pipeline for a document. 
    il documento. The ProcessingAgent handles extraction and parsing.
    """
    try:
        entities = processing_agent.process_document(input_data)
        return {"status": "success", "entities_extracted": entities.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
def handle_chat_query(request: QueryRequest):
    """
    Legacy endpoint. Use /copilotkit for the CopilotKit UI instead.
    """
    try:
        response_json = {"message": f"Endpoint legacy invocato per {request.query}. Usa l'aggiornato /copilotkit per integrare AG-UI."}
        return {"status": "success", "agent_response": response_json}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print("Starting KnowledgeForge...")
    is_dev = os.getenv("ENV", "development") != "production"
    uvicorn.run(
        "main:app" if is_dev else app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=is_dev,
    )
