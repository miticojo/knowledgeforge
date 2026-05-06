import os
import json
import logging
from typing import Literal, Optional
from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google import genai

from services.cost_tracker import get_tracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic schema for Controlled Generation (graph extraction)
# ---------------------------------------------------------------------------

_ENTITY_TYPES = Literal[
    "ApplicationComponent", "DataObject", "BusinessProcess", "Requirement",
    "Node", "SystemSoftware", "TechnologyService", "BusinessActor",
    "BusinessRole", "BusinessService", "BusinessFunction", "BusinessObject",
    "ApplicationService", "ApplicationInterface", "Artifact", "Device",
    "CommunicationNetwork", "Contract", "Goal", "Constraint", "Stakeholder",
    "Capability",
]

_RELATIONSHIP_TYPES = Literal[
    "Composition", "Aggregation", "Assignment", "Realization", "Serving",
    "Access", "Influence", "Association", "Triggering", "Flow", "Specialization",
]

_CONFIDENCE_LEVELS = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]


class _ExtractedNode(BaseModel):
    entity_type: _ENTITY_TYPES
    entity_name: str


class _ExtractedEdge(BaseModel):
    source_type: _ENTITY_TYPES
    source_name: str
    relationship_type: _RELATIONSHIP_TYPES
    target_type: _ENTITY_TYPES
    target_name: str
    qualifier: Optional[str] = None
    confidence: _CONFIDENCE_LEVELS = "EXTRACTED"


class _GraphExtraction(BaseModel):
    nodes: list[_ExtractedNode]
    edges: list[_ExtractedEdge]

# --- Module-level state for inter-tool data passing ---
# (safe for single-session ADK pipeline; each document gets its own session)
_last_metadata: dict | None = None
_last_doc_embedding: list[float] | None = None
_last_chunks: list | None = None
_last_graph_result: dict | None = None
_last_doc_text: str | None = None
# Set by main.py /upload-document endpoint BEFORE the pipeline starts
_full_document_text: str | None = None
_full_document_images: list | None = None


def extract_metadata(title: str, author: str, document_type: str, key_topics: list[str], document_date: str = "") -> str:
    """Save the key metadata extracted from the document by the agent.

    document_date should be the publication or creation date of the document
    in ISO format (YYYY-MM-DD) or any recognizable date string.
    If the date cannot be determined from the document, pass an empty string.
    """
    print(f"[STEP 1] extract_metadata called: title={title}, date={document_date}")
    global _last_metadata
    _last_metadata = {
        "title": title,
        "author": author,
        "type": document_type,
        "concepts": key_topics,
        "date": document_date,
    }
    return json.dumps({
        "type": document_type,
        "title": title,
        "author": author,
        "concepts": key_topics,
        "document_date": document_date,
    }, indent=2)

def _run_embeddings(doc_text: str, doc_images: list, doc_title: str, doc_type: str) -> dict:
    """Internal: chunk, contextualize, and embed the document. Returns summary dict."""
    try:
        from services.document_chunker import chunk_document, contextualize_chunks, compute_chunk_embeddings

        chunks = chunk_document(doc_text, images=doc_images)
        chunks = contextualize_chunks(chunks, doc_title=doc_title, doc_summary=doc_text[:2000])

        metadata_prefix = f"[doc:{doc_title}; type:{doc_type}]" if doc_type else f"[doc:{doc_title}]"
        chunks = compute_chunk_embeddings(chunks, metadata_prefix=metadata_prefix)

        if chunks and chunks[0].embedding:
            dim = len(chunks[0].embedding)
            avg_embedding = [0.0] * dim
            n = sum(1 for c in chunks if c.embedding)
            for c in chunks:
                if c.embedding:
                    for i, v in enumerate(c.embedding):
                        avg_embedding[i] += v / n
        else:
            avg_embedding = []

        return {"chunks": chunks, "doc_embedding": avg_embedding, "status": "completed", "count": len(chunks)}
    except Exception as e:
        logger.error(f"Embedding/chunking failed: {e}")
        return {"chunks": [], "doc_embedding": [], "status": f"failed: {e}", "count": 0}


def _run_graph_extraction(doc_text: str) -> dict:
    """Internal: extract ArchiMate graph via Controlled Generation."""
    doc_text_truncated = doc_text[:30000]
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=_GRAPH_EXTRACTION_PROMPT.format(document_text=doc_text_truncated),
            config=genai.types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=_GraphExtraction,
                thinking_config=genai.types.ThinkingConfig(thinking_budget=0),
            ),
        )
        tracker = get_tracker()
        if tracker:
            tracker.track_generate(response, model="gemini-2.5-flash")

        data = json.loads(response.text)
        extraction = _GraphExtraction(**data)

        nodes = [f"{n.entity_type}:{n.entity_name}" for n in extraction.nodes]
        edges = []
        for e in extraction.edges:
            edge_str = f"{e.source_type}:{e.source_name}->{e.relationship_type}"
            # Pack qualifier and confidence into bracket: [qualifier,CONFIDENCE]
            bracket_parts = []
            if e.qualifier:
                bracket_parts.append(e.qualifier)
            bracket_parts.append(e.confidence or "EXTRACTED")
            edge_str += f"[{','.join(bracket_parts)}]"
            edge_str += f"->{e.target_type}:{e.target_name}"
            edges.append(edge_str)

        return {
            "extracted_nodes": nodes, "extracted_edges": edges,
            "total_nodes": len(nodes), "total_edges": len(edges),
            "status": "completed",
        }
    except Exception as e:
        logger.error(f"Controlled Generation failed: {e}", exc_info=True)
        return {"extracted_nodes": [], "extracted_edges": [], "total_nodes": 0, "total_edges": 0, "status": f"failed: {e}"}


def _run_entity_search(search_query: str) -> dict:
    """Internal: search existing entities in the graph DB."""
    try:
        from services.entity_search import search_entities_by_themes
        results = search_entities_by_themes(search_query)
        return {"entities_found": results, "status": "completed"}
    except Exception as e:
        logger.warning(f"Spanner search failed: {e}")
        return {"entities_found": [], "status": f"failed: {e}"}


def process_document(summary: str, search_themes: str) -> str:
    """Run embeddings, graph extraction, and entity search IN PARALLEL.

    Pass a brief conceptual summary (max 2000 chars) and key themes for entity search.
    This function runs three heavy operations concurrently using ThreadPoolExecutor:
    1. Document chunking + contextual retrieval + multimodal embedding
    2. ArchiMate graph extraction via Controlled Generation
    3. Existing entity search in the Knowledge Graph
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    global _last_doc_embedding, _last_chunks, _last_doc_text, _last_graph_result
    global _full_document_text, _full_document_images

    doc_text = _full_document_text or summary
    doc_images = _full_document_images or []
    _last_doc_text = doc_text

    doc_title = _last_metadata.get("title", "Untitled") if _last_metadata else "Untitled"
    doc_type = _last_metadata.get("type", "") if _last_metadata else ""

    print(f"[STEP 2-4] process_document called: doc={len(doc_text)} chars, images={len(doc_images)}")
    t0 = time.time()

    # Run all 3 operations in parallel
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_embed = pool.submit(_run_embeddings, doc_text, doc_images, doc_title, doc_type)
        fut_graph = pool.submit(_run_graph_extraction, doc_text)
        fut_search = pool.submit(_run_entity_search, search_themes)

        embed_result = fut_embed.result()
        graph_result = fut_graph.result()
        search_result = fut_search.result()

    elapsed = time.time() - t0

    # Store results in module state for write_to_spanner
    _last_chunks = embed_result["chunks"]
    _last_doc_embedding = embed_result["doc_embedding"]
    _last_graph_result = graph_result if graph_result.get("total_nodes", 0) > 0 else None

    print(f"[STEP 2-4] Parallel processing completed in {elapsed:.1f}s: "
          f"chunks={embed_result['count']}, nodes={graph_result.get('total_nodes', 0)}, "
          f"edges={graph_result.get('total_edges', 0)}, entities={len(search_result.get('entities_found', []))}")

    return json.dumps({
        "embedding": {
            "status": embed_result["status"],
            "model": "gemini-embedding-2-preview",
            "chunks": embed_result["count"],
            "dimensions": len(embed_result["doc_embedding"]),
        },
        "graph": {
            "status": graph_result["status"],
            "total_nodes": graph_result.get("total_nodes", 0),
            "total_edges": graph_result.get("total_edges", 0),
            "extracted_nodes": graph_result.get("extracted_nodes", []),
            "extracted_edges": graph_result.get("extracted_edges", []),
        },
        "entity_search": {
            "status": search_result["status"],
            "entities_found": len(search_result.get("entities_found", [])),
        },
        "parallel_time_seconds": round(elapsed, 1),
    }, indent=2, ensure_ascii=False)


# Keep individual functions for backward compatibility and testing
def extract_embeddings(summary_to_embed: str) -> str:
    """Compute vector embeddings with document chunking and multimodal embedding."""
    global _last_doc_embedding, _last_chunks, _last_doc_text, _full_document_text, _full_document_images
    doc_text = _full_document_text or summary_to_embed
    _last_doc_text = doc_text
    doc_title = _last_metadata.get("title", "Untitled") if _last_metadata else "Untitled"
    doc_type = _last_metadata.get("type", "") if _last_metadata else ""
    result = _run_embeddings(doc_text, _full_document_images or [], doc_title, doc_type)
    _last_chunks = result["chunks"]
    _last_doc_embedding = result["doc_embedding"]
    return json.dumps({"status": result["status"], "chunks": result["count"]}, indent=2)


def search_existing_entities(search_query: str) -> str:
    """Search the existing Graph DB using keywords or topic strings."""
    result = _run_entity_search(search_query)
    return json.dumps(result, indent=2, ensure_ascii=False)

import re

VALID_ENTITY_TYPES = {
    "ApplicationComponent", "DataObject", "BusinessProcess", "Requirement",
    "Node", "SystemSoftware", "TechnologyService", "BusinessActor",
    "BusinessRole", "BusinessService", "BusinessFunction", "BusinessObject",
    "ApplicationService", "ApplicationInterface", "Artifact", "Device",
    "CommunicationNetwork", "Contract", "Goal", "Constraint", "Stakeholder",
    "Capability",
}

VALID_RELATIONSHIP_TYPES = {
    "Composition", "Aggregation", "Assignment", "Realization", "Serving",
    "Access", "Influence", "Association", "Triggering", "Flow", "Specialization",
}

# --- Mapping free-form verbs -> ArchiMate 3.2 relationships ---
_VERB_TO_RELATIONSHIP = {
    # Serving (provider → consumer)
    "USES": "Serving", "UTILIZES": "Serving", "PROVIDES_SERVICES_TO": "Serving",
    "PROVIDES": "Serving", "SERVES": "Serving", "SUPPORTS": "Serving",
    "ENABLES": "Serving", "REQUIRES": "Serving", "DEPENDS_ON": "Serving",
    "RELIES_ON": "Serving", "BASED_ON": "Serving",
    # Assignment (structure → behavior)
    "MANAGES": "Serving", "OPERATES_IN": "Assignment", "OPERATES_VIA": "Assignment",
    "WORKS_IN": "Assignment", "WORKS_FOR": "Assignment",
    "RESPONSIBLE_FOR": "Assignment", "ASSIGNED_TO": "Assignment",
    "AUTHORED": "Assignment", "WRITTEN_BY": "Assignment", "PREFACED": "Assignment",
    "CONTRIBUTED_TO": "Assignment", "APPLIED_TO": "Assignment",
    # Composition / Aggregation
    "CONTAINS": "Composition", "COMPOSED_OF": "Composition",
    "INCLUDES": "Aggregation", "INCLUDES_PATTERN": "Aggregation",
    "HAS_DIVISION": "Aggregation", "HAS_PART": "Aggregation",
    "COMPRISES": "Aggregation", "GROUPS": "Aggregation",
    # Realization
    "IMPLEMENTS": "Realization", "IMPLEMENTED_WITH": "Realization",
    "REALIZES": "Realization", "DEVELOPS": "Realization",
    "CONCRETIZES": "Realization",
    # Influence (→ motivation elements)
    "INFLUENCES": "Influence", "IMPACTS": "Influence", "IMPACTS_ON": "Influence",
    "IMPROVES": "Influence", "ENHANCES": "Influence", "GUIDES": "Influence",
    "CRUCIAL_FOR": "Influence", "ESSENTIAL_FOR": "Influence",
    "REDUCES": "Influence", "INCREASES": "Influence",
    # Triggering
    "FOLLOWS_PROCESS": "Triggering", "PRECEDES": "Triggering",
    "ACTIVATES": "Triggering", "TRIGGERS": "Triggering",
    # Flow
    "TRANSFERS": "Flow", "SENDS": "Flow", "RECEIVES": "Flow",
    "FLOWS": "Flow",
    # Access
    "ACCESSES": "Access", "READS": "Access", "WRITES": "Access",
    "MODIFIES": "Access", "PUBLISHES": "Access",
    "STUDIES": "Access", "MEASURED_BY": "Access",
    # Association (generic fallback)
    "ASSOCIATED_WITH": "Association", "LINKED_TO": "Association",
    "RELATED_TO": "Association", "CONNECTED_TO": "Association",
    "ACQUIRES": "Association", "INVESTS_IN": "Association",
    "ENGAGED_IN": "Association", "FOCUSES_ON": "Association",
    "MERGES_WITH": "Association", "DONATES_ROYALTIES_TO": "Association",
    "CONTROLLED_BY": "Association",
    "COLLABORATES_WITH": "Association",
}

# --- Heuristic node classification → ArchiMate type ---
_NODE_PATTERNS = [
    # Technology (check first — most specific patterns)
    (re.compile(r"(?i)\b(server|vm|cluster|k8s|kubernetes|gke|aks|eks|host)\b"), "Node"),
    (re.compile(r"(?i)\b(router|firewall|switch|load.?balancer|hardware|device)\b"), "Device"),
    (re.compile(r"(?i)\b(oracle|mysql|postgres|redis|linux|windows|docker|tomcat|nginx|apache|jdk|jre|dbms|os\b|runtime|mongodb|elasticsearch)\b"), "SystemSoftware"),
    (re.compile(r"(?i)\b(\.jar|\.war|\.ear|\.zip|\.tar|dockerfile|docker-compose|helm|artifact|image|package)\b"), "Artifact"),
    (re.compile(r"(?i)\b(lan|wan|vpn|network|internet|intranet|dmz)\b"), "CommunicationNetwork"),
    (re.compile(r"(?i)\b(dns|storage.?service|hosting|messaging|message.?queue|monitoring.?service)\b"), "TechnologyService"),
    # Application
    (re.compile(r"(?i)\b(api|endpoint|rest|graphql|soap|grpc|interface)\b"), "ApplicationInterface"),
    (re.compile(r"(?i)\b(crm|erp|sap|salesforce|jira|confluence|portal|app\b|application|tool|framework|library|sdk|platform.?engineering)\b"), "ApplicationComponent"),
    (re.compile(r"(?i)\b(record|dataset|data.?object|schema|database)\b"), "DataObject"),
    # Business — people/org
    (re.compile(r"(?i)\b(team|department|organization|company|group)\b"), "BusinessActor"),
    (re.compile(r"(?i)\b(role|owner|steward)\b"), "BusinessRole"),
    # Business — processes & functions
    (re.compile(r"(?i)\b(process|workflow|procedure|onboarding|fulfillment|billing|delivery|development|engineering|deployment|feedback.?loop|migration)\b"), "BusinessProcess"),
    (re.compile(r"(?i)\b(function|finance|hr|operations|marketing|governance|compliance)\b"), "BusinessFunction"),
    (re.compile(r"(?i)\b(service)\b"), "BusinessService"),
    (re.compile(r"(?i)\b(contract|sla|agreement|nda)\b"), "Contract"),
    # Motivation
    (re.compile(r"(?i)\b(stakeholder|cto|ceo|cio|cfo|architect|board|director)\b"), "Stakeholder"),
    (re.compile(r"(?i)\b(goal|target|strategy|increase|reduce|improve|success)\b"), "Goal"),
    (re.compile(r"(?i)\b(requirement|shall|must)\b"), "Requirement"),
    (re.compile(r"(?i)\b(constraint|limitation|budget|compliance|gdpr)\b"), "Constraint"),
    # Strategy
    (re.compile(r"(?i)\b(capability|ability|competency|adoption|transformation|adaptation|agility|model|maturity|readiness|value.?stream|stream.?management)\b"), "Capability"),
    # Catch-all for research/knowledge concepts
    (re.compile(r"(?i)\b(research|study|report|survey|analysis|paper|methodology|framework|model|standard|pattern|architecture|culture|practice|principle)\b"), "BusinessObject"),
]


def _classify_node(name: str) -> str:
    """Classify a free-form name into the most likely ArchiMate type."""
    for pattern, archimate_type in _NODE_PATTERNS:
        if pattern.search(name):
            return archimate_type
    # Fallback: proper nouns → BusinessActor, otherwise BusinessObject
    parts = name.strip().split()
    if 1 <= len(parts) <= 3 and all(p[0].isupper() for p in parts if p):
        return "BusinessActor"
    return "BusinessObject"


def _classify_relationship(verb: str) -> str:
    """Map a free-form verb to the closest ArchiMate relationship type."""
    normalized = verb.strip().upper().replace(" ", "_")
    if normalized in _VERB_TO_RELATIONSHIP:
        return _VERB_TO_RELATIONSHIP[normalized]
    # Check if it's already a valid ArchiMate relationship type
    for valid in VALID_RELATIONSHIP_TYPES:
        if normalized == valid.upper():
            return valid
    return "Association"  # safe fallback


def _normalize_node(raw: str) -> tuple[str, str]:
    """Parse a node: if it has 'Type:Name' use it, otherwise classify."""
    if ":" in raw:
        candidate_type, name = raw.split(":", 1)
        candidate_type = candidate_type.strip()
        name = name.strip()
        if candidate_type in VALID_ENTITY_TYPES:
            return candidate_type, name
    # Model did not use the format — classify automatically
    name = raw.strip()
    entity_type = _classify_node(name)
    return entity_type, name


def _normalize_edge(raw: str, node_map: dict[str, str]) -> tuple[str, str, str] | None:
    """Parse an edge, normalizing relationship type and source/target names."""
    parts = raw.split("->")
    if len(parts) < 3:
        return None
    src_raw = parts[0].strip()
    verb = parts[1].strip()
    tgt_raw = "->".join(parts[2:]).strip()

    rel_type = _classify_relationship(verb.replace("[", "").replace("]", "").split("[")[0])

    src_key = _find_node_key(src_raw, node_map)
    tgt_key = _find_node_key(tgt_raw, node_map)

    if src_key and tgt_key:
        return src_key, rel_type, tgt_key
    return None


def _find_node_key(raw: str, node_map: dict[str, str]) -> str | None:
    """Find the 'Type:Name' key in node_map for a raw name."""
    if raw in node_map:
        return raw
    for key, name in node_map.items():
        if name == raw or key.endswith(":" + raw):
            return key
    return None


_GRAPH_EXTRACTION_PROMPT = """Extract ALL entities and relationships from this document following the ArchiMate 3.2 Wave 2 ontology.

ENTITY TYPES (22): ApplicationComponent, DataObject, BusinessProcess, Requirement, Node, SystemSoftware, TechnologyService, BusinessActor, BusinessRole, BusinessService, BusinessFunction, BusinessObject, ApplicationService, ApplicationInterface, Artifact, Device, CommunicationNetwork, Contract, Goal, Constraint, Stakeholder, Capability.

RELATIONSHIP TYPES (11): Composition, Aggregation, Assignment, Realization, Serving, Access, Influence, Association, Triggering, Flow, Specialization.

DIRECTION RULES:
- Assignment: Active Structure -> Behavior (Actor -> Process, Node -> Artifact)
- Realization: Concrete -> Abstract (App -> Requirement, Artifact -> App)
- Serving: Provider -> Consumer (TechService -> App, App -> BusinessProcess)
- Access: Behavior -> Data (qualifier: Read, Write, ReadWrite)
- Composition/Aggregation: Whole -> Part
- Influence: any -> Motivation element (qualifier: +, -, ++, --)
- Triggering/Flow: Source -> Destination

CONFIDENCE RULES — assign one per relationship:
- EXTRACTED: the relationship is explicitly stated in the text (e.g. "X serves Y", "X is composed of Y", "X runs on Y")
- INFERRED: the relationship is reasonably deduced from context (e.g. two entities co-occur in the same paragraph describing an interaction, or a dependency is implied but not directly stated)
- AMBIGUOUS: the relationship is uncertain or the text is vague about the nature of the connection

CLASSIFICATION DECISION TREE:
1. Person/team/organization? -> BusinessActor
2. Named responsibility? -> BusinessRole
3. Software/application/platform? -> ApplicationComponent
4. API/endpoint? -> ApplicationInterface
5. Service exposed by application? -> ApplicationService
6. OS/middleware/DBMS/runtime? -> SystemSoftware
7. Server/VM/HW+SW platform? -> Node
8. Physical hardware? -> Device
9. Network? -> CommunicationNetwork
10. Deployable file? -> Artifact
11. Structured data for applications? -> DataObject
12. Business information concept? -> BusinessObject
13. Operational workflow? -> BusinessProcess
14. Competency grouping? -> BusinessFunction
15. Exposed business service? -> BusinessService
16. Formal agreement/SLA? -> Contract
17. Strategic objective? -> Goal
18. Functional/non-functional requirement? -> Requirement
19. Limitation/constraint? -> Constraint
20. Role with architecture interests? -> Stakeholder
21. Organizational/system capability? -> Capability
22. Exposed infrastructure service? -> TechnologyService

DOCUMENT:
{document_text}"""


def extract_graph(confirm_extraction: str) -> str:
    """Extract the ArchiMate knowledge graph from the document using structured generation.

    Pass 'OK' to start extraction. Kept for backward compatibility —
    prefer process_document which runs this in parallel with embeddings.
    """
    global _last_graph_result, _last_doc_text
    doc_text = _last_doc_text or _full_document_text or ""
    if not doc_text:
        return json.dumps({"error": "No document text available."})
    result = _run_graph_extraction(doc_text)
    if result.get("total_nodes", 0) > 0:
        _last_graph_result = result
    return json.dumps(result, indent=2, ensure_ascii=False)

def write_to_spanner(operation_status: str) -> str:
    """Persist the ArchiMate graph to Cloud Spanner with entity reconciliation.

    Pass 'OK' to start writing. The function uses data saved by previous tools
    (extract_metadata, extract_embeddings, extract_graph).
    """
    global _last_graph_result, _last_doc_embedding, _last_metadata, _last_chunks
    print(f"[STEP 5] write_to_spanner called: status={operation_status}, graph_result={'SET' if _last_graph_result else 'NONE'}")
    if operation_status != "OK" or _last_graph_result is None:
        return json.dumps({"error": "No data to write. Ensure extract_graph has completed."})

    try:
        import uuid
        from services.graph_writer import write_graph_to_spanner
        from services.tenant_context import get_tenant, SHARED_TENANT

        doc_title = _last_metadata.get("title", "Untitled") if _last_metadata else "Untitled"
        doc_summary = _last_doc_text[:10000] if _last_doc_text else ""

        # Idempotency: check if document with same title exists, replace it
        import hashlib
        from services.spanner_client import get_database
        content_hash = hashlib.sha256((doc_title + doc_summary[:1000]).encode()).hexdigest()[:16]
        doc_id = str(uuid.uuid4())
        existing_doc_ids = []
        try:
            db = get_database()
            from google.cloud.spanner_v1 import param_types as _pt
            tenant_id = get_tenant()
            with db.snapshot() as snap:
                rows = snap.execute_sql(
                    "SELECT doc_id FROM Documents WHERE title = @title AND tenant_id = @tenant_id",
                    params={"title": doc_title, "tenant_id": tenant_id},
                    param_types={"title": _pt.STRING, "tenant_id": _pt.STRING},
                )
                existing_doc_ids = [r[0] for r in rows]
            if existing_doc_ids:
                # Delete old versions — new version replaces them
                print(f"[STEP 5] Found {len(existing_doc_ids)} existing version(s) of '{doc_title}', replacing...")
                def _delete_old_docs(transaction):
                    for old_id in existing_doc_ids:
                        # Cascade: ChunkMentions (interleaved in DocumentChunks) → DocumentChunks (interleaved in Documents) → Documents
                        transaction.execute_update(
                            "DELETE FROM ChunkMentions WHERE doc_id = @doc_id AND tenant_id = @tenant_id",
                            params={"doc_id": old_id, "tenant_id": tenant_id},
                            param_types={"doc_id": _pt.STRING, "tenant_id": _pt.STRING},
                        )
                        transaction.execute_update(
                            "DELETE FROM DocumentMentions WHERE doc_id = @doc_id AND tenant_id = @tenant_id",
                            params={"doc_id": old_id, "tenant_id": tenant_id},
                            param_types={"doc_id": _pt.STRING, "tenant_id": _pt.STRING},
                        )
                        transaction.execute_update(
                            "DELETE FROM DocumentChunks WHERE doc_id = @doc_id AND tenant_id = @tenant_id",
                            params={"doc_id": old_id, "tenant_id": tenant_id},
                            param_types={"doc_id": _pt.STRING, "tenant_id": _pt.STRING},
                        )
                        transaction.execute_update(
                            "DELETE FROM Documents WHERE doc_id = @doc_id AND tenant_id = @tenant_id",
                            params={"doc_id": old_id, "tenant_id": tenant_id},
                            param_types={"doc_id": _pt.STRING, "tenant_id": _pt.STRING},
                        )
                db.run_in_transaction(_delete_old_docs)
                print(f"[STEP 5] Deleted {len(existing_doc_ids)} old version(s)")
        except Exception as e:
            logger.warning(f"Idempotency check failed (proceeding with insert): {e}")

        doc_date = _last_metadata.get("date", "") if _last_metadata else ""
        result = write_graph_to_spanner(
            graph_json=_last_graph_result,
            doc_id=doc_id,
            doc_title=doc_title,
            doc_summary=doc_summary,
            doc_embedding=_last_doc_embedding or [],
            chunks=_last_chunks or [],
            document_date=doc_date,
            tenant_id=get_tenant(),
        )

        # Clear global state to prevent duplicate writes if the LLM calls again
        _last_graph_result = None
        _last_doc_embedding = None
        _last_metadata = None
        _last_chunks = None

        return json.dumps({
            "status": "saved to Cloud Spanner",
            "document_id": doc_id,
            "entities": result.get("entities_total", 0),
            "edges": result.get("edges_total", 0),
            "chunks": result.get("chunks_total", 0),
            "reconciliation": result.get("reconciliation", {}),
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Write to Spanner failed: {e}", exc_info=True)
        return json.dumps({
            "status": "error writing to Spanner",
            "error": str(e),
            "note": "Graph data was extracted correctly but persistence failed.",
        }, indent=2, ensure_ascii=False)

def pipeline_complete(summary: str) -> str:
    """Signal the completion of the ingestion pipeline.

    Call ONLY after write_to_spanner has succeeded.
    Pass a brief summary of the result.
    """
    return json.dumps({"status": "pipeline completed", "summary": summary})

from google.genai import types as genai_types

processing_agent = LlmAgent(
    name="ProcessingAgent",
    model="gemini-2.5-flash",
    generate_content_config=genai_types.GenerateContentConfig(

        tool_config=genai_types.ToolConfig(
            function_calling_config=genai_types.FunctionCallingConfig(mode="AUTO")
        ),
    ),
    instruction="""
You are the Processing (Ingestion) Agent for the Knowledge Base.
Your job is to READ the provided document text and orchestrate the ingestion pipeline.

CRITICAL RULE: Call ONE TOOL at a time. ALWAYS wait for a tool's result before
calling the next one. NEVER call more than one tool per turn. The order is:

STEP 1: Call ONLY extract_metadata with your extracted title, author, document type,
key topics, and document_date (publication/creation date in YYYY-MM-DD format, or
empty string if unknown). NEVER paste the full document text into any tool.
Stop and wait for the result.

STEP 2: After receiving extract_metadata result, call ONLY process_document with:
- summary: a brief conceptual summary of the document (max 2000 chars)
- search_themes: a macro-query covering the document's main themes
This function runs embedding, graph extraction, and entity search IN PARALLEL.
Stop and wait for the result.

STEP 3: After receiving process_document result, call ONLY write_to_spanner passing 'OK'.
If any component failed, still call write_to_spanner — partial results are saved.

STEP 4: After write_to_spanner succeeds, call ONLY pipeline_complete with a brief summary
of the result (how many nodes, edges, chunks were saved).
After pipeline_complete, do NOT call any other tool. The pipeline is finished.
""",
    tools=[extract_metadata, process_document, write_to_spanner, pipeline_complete]
)
