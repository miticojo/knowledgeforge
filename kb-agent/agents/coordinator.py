import os
import json
import re
from .search import search_agent, tool_query_spanner_graph
from .doc import doc_agent
from .security import before_agent_security_check
from models.ontology import QueryIntent, SearchResult
from google.adk.agents import LlmAgent
from google.adk.models import LlmResponse
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

_doc_agent_tool = AgentTool(agent=doc_agent)


def _truthy(value: str | None) -> bool:
    """Return True if value is one of '1', 'true', 'yes' (case-insensitive)."""
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes")


def _build_mcp_toolset(prebuilt_name: str, prefix: str, env_extra: dict) -> MCPToolset:
    """Build an MCPToolset wrapping a data-agent-kit prebuilt MCP server via npx.

    NOTE: env passed to StdioServerParameters REPLACES (does not merge) the subprocess env.
    We always include PATH from the current process so npx can be resolved.
    """
    env = {"PATH": os.environ.get("PATH", ""), **env_extra}
    stdio_params = StdioServerParameters(
        command="npx",
        args=["-y", "@toolbox-sdk/server@>=1.1.0", "--prebuilt", prebuilt_name, "--stdio"],
        env=env,
    )
    return MCPToolset(
        connection_params=StdioConnectionParams(server_params=stdio_params, timeout=30.0),
        tool_name_prefix=prefix,
    )

from google.genai import types as genai_types

# ---------------------------------------------------------------------------
# Module-level storage for image results and retrieval metadata
# (set by tool, read by callback)
# ---------------------------------------------------------------------------
_LATEST_TURN_METADATA: dict = {}
_pending_image_chunks: list[dict] = []
_pending_retrieval_metadata: dict | None = None
_pending_graph_connections: list[str] = []
_pending_graph_chains: list[str] = []


def _after_model_inject_images(callback_context, llm_response: LlmResponse) -> LlmResponse | None:
    """Deterministically inject image data and retrieval metadata into the Coordinator's response.

    The LLM unreliably includes [IMAGE:...] tags, image sources, and query_cost.
    This callback ensures images and full retrieval metadata (including cost) always appear.
    """
    global _pending_image_chunks, _pending_retrieval_metadata, _pending_graph_connections, _pending_graph_chains

    if (not _pending_image_chunks and not _pending_retrieval_metadata
            and not _pending_graph_connections and not _pending_graph_chains) or not llm_response.content:
        return None  # Nothing to inject

    # Only inject on the FINAL response (turn_complete=True), not on streaming partials
    if not llm_response.turn_complete:
        return None

    # Only inject on text responses (not function calls)
    parts = llm_response.content.parts or []
    has_text = any(getattr(p, "text", None) for p in parts)
    has_function_call = any(getattr(p, "function_call", None) for p in parts)
    if has_function_call or (not has_text and not llm_response.turn_complete):
        return None

    # Consume only on the final response event
    # We DO NOT clear them here, because the callback might fire multiple times
    # (e.g. once for function call, once for text stream). Wiping them causes data loss.
    retrieval_meta = _pending_retrieval_metadata
    images = _pending_image_chunks
    graph_conns = _pending_graph_connections
    graph_chains = _pending_graph_chains

    # Track coordinator LLM cost using ADK-native usage_metadata, then refresh query_cost.
    # Note: get_tracker() may return None if middleware already called stop_tracking()
    # during streaming — in that case, retrieval_meta keeps search-only costs from the tool.
    if retrieval_meta:
        from services.cost_tracker import get_tracker
        tracker = get_tracker()
        if tracker:
            if llm_response.usage_metadata:
                tracker.track_generate(llm_response, model="gemini-2.5-flash")
            retrieval_meta["query_cost"] = tracker.to_dict()

    print(f"[Coordinator] Final retrieval_meta: {retrieval_meta}")
    
    # Build image tags and sources entry
    image_tags = []
    image_sources = []
    for img in images:
        tag = f"\n\n[IMAGE:{img['image_id']}:{img['doc_id']}:{img['chunk_id']}]"
        image_tags.append(tag)
        image_sources.append(img)

    # Build sources_json for out-of-band delivery
    sources_json = {}
    if graph_conns: sources_json["graph"] = graph_conns
    if graph_chains: sources_json["chains"] = graph_chains
    if image_sources: sources_json["images"] = image_sources
    if retrieval_meta: sources_json["retrieval"] = retrieval_meta
    
    if "documents" not in sources_json:
        sources_json["documents"] = []
    if "graph" not in sources_json:
        sources_json["graph"] = []

    # Store out-of-band
    from services.tenant_context import get_tenant
    tenant_id = get_tenant()
    _LATEST_TURN_METADATA[tenant_id] = sources_json
    _LATEST_TURN_METADATA["LATEST"] = sources_json
    try:
        with open("/tmp/latest_turn_metadata.json", "w") as f:
            json.dump(sources_json, f)
    except Exception:
        pass
    print(f"[Coordinator] Stored out-of-band metadata for tenant '{tenant_id}' to disk")

    # Clean the text from existing <sources> blocks and inject [IMAGE:...] tags
    for part in parts:
        text = getattr(part, "text", None)
        if not text:
            continue
        
        # Strip <sources> block if model added it
        sources_match = re.search(r"<sources>\s*(\{.*?\})\s*</sources>", text, re.DOTALL)
        if sources_match:
            text = text[:sources_match.start()] + text[sources_match.end():]

        # Inject images
        if image_tags:
            text = text.rstrip() + "".join(image_tags)

        part.text = text

    return llm_response

_COORDINATOR_INSTRUCTION = """
    You are the Coordinator Agent for the Agentic Knowledge Base.

    CRITICAL CHAT GUIDELINES (MUST FOLLOW):
    1. You are in a multi-turn conversation. Answer ONLY the user's LATEST question.
    2. Do NOT repeat previous answers or summarize the conversation unless explicitly asked.
    3. Focus on providing new information relevant to the current query.
    4. If the user asks "which of these", refer to the previous context but do not repeat the list unless necessary.

    Your job is to analyze the user's request and provide COMPLETE, ACCURATE answers.

    SEARCH STRATEGY:
    1. ALWAYS call the tool_query_spanner_graph tool to search the knowledge base first.
       Pass the user's query directly. The tool performs hybrid retrieval on Cloud Spanner:
       - Keyword search for exact term matching in document chunks
       - Vector similarity search on chunk embeddings
       - Graph traversal across ArchiMate relationships for cross-document discovery

       NOTE: if the user has selected entities in the graph, the tool will
       automatically scope retrieval to documents/chunks that mention those
       entities — you do not need to mention this scope in your answer unless
       the user explicitly asks about it.

    2. If the user asks for a Document (report, analysis, wiki), AFTER the search
       delegate the writing to the DocAgent AgentTool.

    ANSWER GENERATION — EXTRACT-THEN-GENERATE (3 steps):

    You MUST follow these 3 steps internally before writing your answer:

    STEP 1 — EXTRACT: Read EVERY chunk returned by the search. For each chunk,
    extract ALL facts relevant to the question. Do not skip any chunk.
    Each chunk is prefixed with [Source: DocTitle, Date: YYYY-MM-DD, Page: N].
    The Date field indicates when the document was published or created.

    STEP 2 — SYNTHESIZE: Combine the extracted facts into a coherent, complete answer.
    Include ALL relevant details found across ALL chunks. When multiple chunks
    mention the same entity, merge the information. If different chunks provide
    complementary facts, include them all.

    STEP 3 — USE GRAPH CHAINS: The search results may include "graph_chains" —
    these are 2-hop dependency paths like "A -[Serving]-> B -[Assignment]-> C".
    For impact analysis, dependency, or "what happens if X fails" questions,
    USE these chains to trace the full impact path and include ALL entities in the chain.

    STEP 4 — ATOMIC FACT VERIFICATION (based on RLFKV, ICASSP 2026):
    Before finalizing, decompose your draft answer into independent atomic claims.
    An atomic claim is a single, self-contained factual assertion.
    For each claim, mentally classify it as:
    - SUPPORTED: explicitly stated or directly inferable from a specific chunk
    - CONTRADICTED: conflicts with information in the chunks → REMOVE this claim
    - UNSUPPORTED: not mentioned in any chunk → either REMOVE or prefix with
      "Based on general knowledge, ..." and do NOT cite a source document for it.
    Only present SUPPORTED claims as definitive statements with source citations.
    This step is critical: it prevents hallucination of details that look plausible
    but are not in the retrieved evidence.

    STEP 5 — TEMPORAL REASONING: When multiple chunks from different documents
    discuss the same topic, prefer information from the MORE RECENT document
    (higher Date value). If a newer document contradicts an older one, trust
    the newer version. Always mention the document date when it is relevant
    to the answer (e.g., version changes, policy updates).

    STEP 6 — VERIFY COMPLETENESS: Before writing the final answer, re-check:
    - Did I include facts from every relevant chunk?
    - Did I miss any entity names, relationships, or technical details?
    - For multi-hop questions (impact analysis, dependency chains), did I follow
      the full chain of relationships from graph_chains?
    - Did I consider entity ALIASES? The same system may be called by different
      names in different documents (e.g. "CRM System" = "Salesforce CRM" =
      "Customer Management Platform"). Treat them as the same entity.
    If anything is missing, add it before finalizing.

    IMAGE REFERENCES:
    Search results may include image references in this format:
    [IMAGE:img_N:doc_id:chunk_id] — Description

    When you encounter these in retrieved chunks:
    1. Reference the image naturally in your answer (e.g. "The following diagram
       illustrates this architecture (from Document X, page Y):").
    2. Include the [IMAGE:img_N:doc_id:chunk_id] tag on its OWN line where you want
       the image to appear. Do NOT modify the tag — copy it exactly as-is.
    3. The frontend will replace these tags with the actual rendered images.
    4. Always mention the source document and page when referencing an image.

    RESPONSE FORMAT:
    - Answer clearly and directly in well-formatted prose.
    - If the answer involves lists of entities, dependencies, or specs, use bullet
      points or tables — do NOT bury them in prose.
    - For impact analysis / dependency questions, structure the answer as a chain:
      Entity A → (relationship) → Entity B → (relationship) → Entity C
    - Cite sources naturally: "Dal documento X (pag. Y):" when quoting specific facts.
    - Remove noise from chunk text: ignore `\n`, stray URLs, OCR artifacts.
    - DO NOT say "information not available" if ANY chunk contains relevant content.
      Instead, present what IS available and note if the answer may be incomplete.
    - DO NOT list ArchiMate connections unless the user explicitly asks for them.
    - DO NOT mention how many chunks or connections were found.
    - Always respond in the same language as the user's query.

    SOURCES BLOCK (MANDATORY):
    At the VERY END of every response, after ALL answer text, you MUST append a
    structured sources block in this exact format:

    <sources>
    {"documents": [{"title": "Document Name", "page": "3"}], "graph": ["EntityA (TypeA) -[Rel]-> EntityB (TypeB)"], "chains": ["A (TypeA) -[Rel1]-> B (TypeB) -[Rel2]-> C (TypeC)"], "images": [...], "retrieval": {"strategy": "rrf_rerank", "chunks_found": 15, "keyword_candidates": 9, "vector_candidates": 11, "graph_boosted": 3, "image_chunks_found": 1}}
    </sources>

    Rules for the sources block:
    - "documents": list each unique source document and page from the [Source: ...]
      prefix in the chunks. Use the NUMERIC page value, never "N/A".
      If no page number is present, omit the "page" field for that document.
    - "graph": include graph_connections from the search results as-is.
      Copy them exactly from the search output into the JSON array.
    - "images": list image references used in the answer. Copy the image_chunks
      array from search results (image_id, doc_id, chunk_id, source_doc, page_number).
    - "retrieval": copy the retrieval_metadata object from the search results.
      Include: strategy, chunks_found, keyword_candidates, vector_candidates,
      graph_boosted, image_chunks_found.
    - The <sources> block MUST be the LAST thing in your response.
    - If no sources were used, include: <sources>{"documents": [], "graph": []}</sources>
    - The JSON inside <sources> must be valid, single-line JSON.

    MULTI-SOURCE TOOL SELECTION:
    - Use `tool_query_spanner_graph` for architecture context from indexed
      documents: entities, relationships, processes, dependency chains, and any
      "how does the architecture work" question. This is your default first call.
    - When `kc_*` tools are available, use them to look up live cloud data asset
      metadata (BigQuery tables, datasets, glossary, lineage) maintained in
      Dataplex. Use these when the user asks "what tables exist", "describe
      dataset X", or for current schema/lineage facts.
    - When `bq_*` tools are available, use them to execute SQL against live
      BigQuery data when the user asks for actual numbers, aggregates, counts,
      or fresh analytics that cannot come from indexed documents.
    - Prefer `tool_query_spanner_graph` first for any architectural or
      conceptual question; only reach for `kc_*` / `bq_*` when the answer
      requires live cloud metadata or live data.
    """


def build_coordinator() -> LlmAgent:
    """Construct the Coordinator agent, optionally appending Google Data Agent Kit
    MCP toolboxes based on env vars. Defaults: both toolboxes OFF.

    Env vars:
      - KC_TOOLBOX_ENABLED: enable Dataplex/Knowledge-Catalog MCP. Requires DATAPLEX_PROJECT.
      - BQ_TOOLBOX_ENABLED: enable BigQuery MCP. Requires BIGQUERY_PROJECT and BIGQUERY_LOCATION.

    Raises:
      RuntimeError if a toolbox is enabled but its required env vars are missing.
    """
    tools: list = [tool_query_spanner_graph, _doc_agent_tool]

    if _truthy(os.getenv("KC_TOOLBOX_ENABLED")):
        project = os.getenv("DATAPLEX_PROJECT")
        if not project:
            raise RuntimeError(
                "KC_TOOLBOX_ENABLED=true requires DATAPLEX_PROJECT env var to be set."
            )
        tools.append(_build_mcp_toolset(
            prebuilt_name="dataplex",
            prefix="kc_",
            env_extra={"DATAPLEX_PROJECT": project},
        ))

    if _truthy(os.getenv("BQ_TOOLBOX_ENABLED")):
        bq_project = os.getenv("BIGQUERY_PROJECT")
        bq_location = os.getenv("BIGQUERY_LOCATION")
        missing = [name for name, val in (
            ("BIGQUERY_PROJECT", bq_project),
            ("BIGQUERY_LOCATION", bq_location),
        ) if not val]
        if missing:
            raise RuntimeError(
                f"BQ_TOOLBOX_ENABLED=true requires env vars: {', '.join(missing)}."
            )
        tools.append(_build_mcp_toolset(
            prebuilt_name="bigquery",
            prefix="bq_",
            env_extra={
                "BIGQUERY_PROJECT": bq_project,
                "BIGQUERY_LOCATION": bq_location,
            },
        ))

    return LlmAgent(
        name="CoordinatorAgent",
        model="gemini-2.5-flash",
        generate_content_config=genai_types.GenerateContentConfig(
            temperature=0.1,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=4096),
        ),
        instruction=_COORDINATOR_INSTRUCTION,
        tools=tools,
        before_agent_callback=before_agent_security_check,
        after_model_callback=_after_model_inject_images,
    )


coordinator_agent = build_coordinator()
