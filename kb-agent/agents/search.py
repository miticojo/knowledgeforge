import os
import math
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from models.ontology import SearchResult
from services.cost_tracker import get_tracker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Information Gain Pruning (IGP) — "Less is More for RAG" (arXiv 2601.17532)
# ---------------------------------------------------------------------------
# Scores each reranked chunk by how much it reduces the generator's uncertainty.
# Chunks that don't help (IG < threshold) are pruned before generation.
_IGP_TOP_K = 5           # Top-K logprobs per token (Gemini max=20, paper uses 128)
_IGP_MAX_TOKENS = 32     # Max rollout tokens per probe
_IGP_THRESHOLD = 0.05    # Prune chunks with IG below this
_IGP_MIN_CHUNKS = 3      # Always keep at least this many chunks


def _get_igp_client():
    """Get a Vertex AI client for IGP probes (logprobs require Vertex AI)."""
    from google import genai as _genai
    _project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not _project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT env var is required for Vertex AI client")
    return _genai.Client(vertexai=True, project=_project, location="us-central1")


def _compute_normalized_uncertainty(client, prompt: str) -> float:
    """Compute normalized uncertainty (entropy) from a short generation probe."""
    try:
        from google.genai.types import GenerateContentConfig, ThinkingConfig
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=_IGP_MAX_TOKENS,
                response_logprobs=True,
                logprobs=_IGP_TOP_K,
                # Disable thinking for IGP probes — thinking tokens have near-zero
                # entropy and skew the uncertainty calculation.
                thinking_config=ThinkingConfig(thinking_budget=0),
            ),
        )
        logprobs_result = getattr(response.candidates[0], "logprobs_result", None)
        if not logprobs_result or not logprobs_result.top_candidates:
            return 0.5  # Neutral fallback

        total_entropy = 0.0
        n_steps = 0
        for step in logprobs_result.top_candidates:
            candidates = step.candidates
            if not candidates:
                continue
            # Renormalize top-K logprobs into probability distribution
            log_probs = [c.log_probability for c in candidates if c.log_probability is not None]
            if not log_probs:
                continue
            max_lp = max(log_probs)
            exps = [math.exp(lp - max_lp) for lp in log_probs]  # Numerically stable
            total = sum(exps)
            probs = [e / total for e in exps]
            # Compute entropy for this step
            entropy = -sum(p * math.log(p) for p in probs if p > 0)
            total_entropy += entropy
            n_steps += 1

        if n_steps == 0:
            return 0.5
        # Normalize: NU = avg_entropy / log(K), so NU ∈ [0, 1]
        log_k = math.log(_IGP_TOP_K) if _IGP_TOP_K > 1 else 1.0
        return (total_entropy / n_steps) / log_k
    except Exception as e:
        logger.debug(f"IGP probe failed: {e}")
        return 0.5  # Neutral fallback


def _information_gain_pruning(client, query: str, chunks: list[dict]) -> list[dict]:
    """Prune chunks with low information gain using generator logprobs.

    Uses Vertex AI client for logprobs (not available via AI Studio API).
    Returns filtered list of chunks sorted by IG (descending).
    """
    if len(chunks) <= _IGP_MIN_CHUNKS:
        return chunks  # Too few to prune

    # Use Vertex AI client for logprobs probes
    igp_client = _get_igp_client()

    # 1. Compute unconditional uncertainty (query only)
    uncond_prompt = f"User: {query[:500]}\nAssistant:"
    nu_baseline = _compute_normalized_uncertainty(igp_client, uncond_prompt)

    # 2. Compute conditional uncertainty for each chunk (parallel)
    def _probe_chunk(chunk):
        cond_prompt = f"User: {query[:500]}\nContext: {chunk['text'][:800]}\nAssistant:"
        nu_cond = _compute_normalized_uncertainty(igp_client, cond_prompt)
        return chunk, nu_baseline - nu_cond  # IG = baseline - conditional

    ig_results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_probe_chunk, c): c for c in chunks}
        for future in as_completed(futures):
            chunk, ig = future.result()
            chunk["ig_score"] = round(ig, 4)
            ig_results.append((chunk, ig))

    # 3. Sort by IG descending
    ig_results.sort(key=lambda x: x[1], reverse=True)

    # Adaptive pruning: use relative IG threshold based on the best chunk.
    # A chunk is useful if its IG is at least 30% of the top chunk's IG.
    # This handles high-uncertainty domains where all chunks have positive IG.
    top_ig = ig_results[0][1] if ig_results else 0.0
    adaptive_threshold = max(_IGP_THRESHOLD, top_ig * 0.3) if top_ig > 0 else _IGP_THRESHOLD
    pruned = [c for c, ig in ig_results if ig >= adaptive_threshold]

    # Also cap at max 10 chunks (paper shows diminishing returns beyond ~5-8)
    _IGP_MAX_CHUNKS = 10
    pruned = pruned[:_IGP_MAX_CHUNKS]

    # Ensure minimum chunks
    if len(pruned) < _IGP_MIN_CHUNKS:
        pruned = [c for c, _ in ig_results[:_IGP_MIN_CHUNKS]]

    n_pruned = len(chunks) - len(pruned)
    print(f"[SearchAgent] IGP: {len(pruned)}/{len(chunks)} chunks kept "
          f"({n_pruned} pruned, adaptive_thr={adaptive_threshold:.3f}, "
          f"top_ig={top_ig:.3f}, baseline_NU={nu_baseline:.3f})")
    return pruned


def tool_query_bigquery(bq_sql: str) -> str:
    """Esegue una query SQL formattata su BigQuery (Dati analitici).

    Args:
        bq_sql: La query testuale da eseguire.

    Returns:
        I risultati analitici in form di stringa.
    """
    print(f"[Search Engine Tool] BQ query execution mock. SQL: {bq_sql}")
    return "Mocked BQ result: data reflects normal performance"


def tool_check_dataplex_metadata(dataset_name: str) -> str:
    """Verifica le metainformazioni su dizionari Dataplex.

    Args:
        dataset_name: Il nome del dataset richiesto per il dizionario (es. customer_data).

    Returns:
        La definizione del metadato per il dataset selezionato.
    """
    print(f"[Search Engine Tool] Dataplex metadata lookup mock for {dataset_name}")
    return "Mocked Dataplex result: Dataset contains primary financial keys"


def tool_query_spanner_graph(user_intent: str, tool_context: ToolContext) -> str:
    """Esegue una ricerca ibrida su Spanner Graph: vector search + graph traversal + SQL join.

    Combina tre strategie in una singola query Spanner (HippoRAG-inspired):
    1. Vector similarity sui chunk per trovare i seed nodes più rilevanti
    2. Graph traversal multi-hop (1-3 hop) per scoprire entità collegate
    3. SQL join con DocumentChunks e ChunkMentions per restituire i passaggi testuali

    Args:
        user_intent: L'argomento chiave inserito o l'intento logico semantico utente.
        tool_context: Il contesto del tool ADK contenente lo stato della sessione.

    Returns:
        Un dump JSON con chunk semantici, connessioni grafo, e entità correlate.
    """
    try:
        from services.spanner_client import get_database
        from services.document_chunker import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
        from services.schema_registry import ENTITY_TABLE_MAP
        from services.tenant_context import get_tenant, SHARED_TENANT, tenant_sql_filter, get_shared_datasets, get_search_scope, get_entity_scope
        from google import genai

        # Read tenant context from session state passed by ADK if available,
        # falling back to thread-local/global fallbacks.
        # We split by comma to handle duplicated header values (e.g. "mine, mine").
        headers = tool_context.state.get("headers", {}) if hasattr(tool_context, "state") else {}
        _tenant_id = headers.get("tenant_id", get_tenant()).split(",")[0].strip()
        _search_scope = headers.get("search_scope", get_search_scope()).split(",")[0].strip()
        
        datasets_raw = headers.get("shared_datasets", "")
        if datasets_raw:
            from services.tenant_context import SHARED_ARCHISURANCE, SHARED_HOTPOTQA
            dataset_map = {"archisurance": SHARED_ARCHISURANCE, "hotpotqa": SHARED_HOTPOTQA}
            _shared_datasets = [dataset_map[d.strip()] for d in datasets_raw.split(",") if d.strip() in dataset_map]
            if not _shared_datasets:
                _shared_datasets = get_shared_datasets()
        else:
            _shared_datasets = get_shared_datasets()

        # ── Entity-scope: resolve from explicit arg → ToolContext.state → contextvar ──
        # When the user has pinned entities in the graph UI, the search should be
        # constrained to chunks that mention any of those entities. We pass them
        # via header (X-Entity-Scope) → middleware → contextvar; ADK may also
        # surface them via tool_context.state. Explicit arg wins for testability.
        # Entity-scope source of truth = the X-Entity-Scope header (forwarded by
        # the chat layout / graph UI). The LLM MUST NOT pass it as a tool arg —
        # we removed the parameter from the signature so it cannot.
        # Empty header value means "no scope".
        entity_scope: list[str] = []
        header_raw = headers.get("entity_scope", None)
        if header_raw is not None:
            entity_scope = [
                e.strip() for e in str(header_raw).split(",") if e and e.strip()
            ]
        else:
            # No header provided (non-chat path) — fall back to contextvar/global.
            try:
                entity_scope = list(get_entity_scope())
            except Exception:
                entity_scope = []
        # Only keep things that look like UUIDs — guards against the LLM ever
        # finding another path to inject entity names.
        import re as _ure
        _uuid_re = _ure.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", _ure.I)
        entity_scope = [e for e in entity_scope if _uuid_re.match(e or "")]
        if entity_scope:
            print(f"[SearchAgent] Entity scope active: {len(entity_scope)} entity(ies)")

        _pinned_filters: dict[str, str] = {}

        def _tenant_filter(alias: str = "") -> str:
            """Return cached tenant SQL filter, immune to concurrent scope changes."""
            if alias not in _pinned_filters:
                import re as _fre
                prefix = f"{alias}." if alias else ""
                safe_re = _fre.compile(r"^__shared__:[a-z0-9_]+$")
                quoted = ", ".join(f"'{d}'" for d in _shared_datasets if safe_re.match(d))
                if not quoted:
                    quoted = "'__shared__:archisurance', '__shared__:hotpotqa'"
                if _search_scope == "mine":
                    _pinned_filters[alias] = f"{prefix}tenant_id = @_tid"
                elif _search_scope == "shared":
                    _pinned_filters[alias] = f"{prefix}tenant_id IN ({quoted})"
                else:
                    _pinned_filters[alias] = f"{prefix}tenant_id IN (@_tid, {quoted})"
            return _pinned_filters[alias]

        # Pin tracker reference early — middleware may clear the global during streaming
        _tracker = get_tracker()
        started_here = False
        if not _tracker:
            from services.cost_tracker import start_tracking
            _tracker = start_tracking()
            started_here = True

        # 1. Specialist multi-query expansion + graph gate classification
        # Generate 3 specialist queries with different search perspectives:
        # - fact_query: explicit facts, definitions, specifications
        # - context_query: related context, dependencies, implications
        # - temporal_query: version changes, updates, dates, evolution
        # Inspired by Supermemory ASMR specialist agents + RAG-Fusion (arxiv 2402.03367)
        client = genai.Client()
        query_variants = [user_intent]
        enable_graph = True  # Default: graph on — cheap and RRF handles ranking
        try:
            expand_response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"""Analyze this question and return a JSON object with:
1. "fact_query": a search query focused on finding explicit facts, definitions, specifications, or direct answers
2. "context_query": a search query focused on finding related context, dependencies, prerequisites, or background information
3. "temporal_query": a search query focused on finding version changes, updates, dates, release notes, or superseding information
4. "graph_needed": boolean — true ONLY if the question asks about:
   - Dependencies or impact chains between systems/components
   - Relationships between entities (who serves whom, what connects to what)
   - Tracing paths across architecture layers (technology → application → business)
   - Stakeholders affected by a specific system or process
   Set false for factual lookups, definitions, descriptions, or "what is X" questions.

Question: {user_intent[:500]}

JSON object:""",
                config=genai.types.GenerateContentConfig(
                    temperature=0.7,
                    response_mime_type="application/json",
                ),
            )
            tracker = get_tracker()
            if tracker:
                tracker.track_generate(expand_response, model="gemini-2.5-flash")
            parsed = json.loads(expand_response.text or "{}")
            if isinstance(parsed, dict):
                for key in ["fact_query", "context_query", "temporal_query"]:
                    v = parsed.get(key, "")
                    if isinstance(v, str) and v.strip() and v.strip().lower() != user_intent.strip().lower():
                        query_variants.append(v.strip())
                enable_graph = bool(parsed.get("graph_needed", False))
        except Exception:
            pass  # Fallback to original query only, graph off
        print(f"[SearchAgent] Graph gate: {'ON' if enable_graph else 'OFF'} for query: {user_intent[:80]}")

        # Embed all query variants in parallel
        # Note: "search_query:" prefix was tested but removed — see OPTIMIZATION_LOG.md
        from services.document_chunker import _get_embedding_client
        _emb_client = _get_embedding_client()
        def _embed_query(qv):
            emb_response = _emb_client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=qv[:8000],
                config=genai.types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=EMBEDDING_DIMENSIONS,
                ),
            )
            return list(emb_response.embeddings[0].values)

        with ThreadPoolExecutor(max_workers=4) as pool:
            all_embeddings = list(pool.map(_embed_query, query_variants))
        tracker = get_tracker()
        if tracker:
            tracker.track_embed(texts=query_variants, model=EMBEDDING_MODEL)
        query_embedding = all_embeddings[0]  # Primary embedding for graph queries
        print(f"[SearchAgent] Multi-query: {len(query_variants)} variants, {len(all_embeddings)} embeddings")

        # ── CompactRAG Fast-Path: check pre-computed QA pairs first ──
        # If a QA pair matches with high confidence, return immediately (zero LLM calls).
        # Skip fast-path when graph is needed — the user wants graph connections.
        # Based on "CompactRAG" (arXiv 2602.05728).
        if not enable_graph:
            try:
                from services.qa_cache import search_qa_cache
                qa_match = search_qa_cache(query_embedding)
                if qa_match:
                    print(f"[SearchAgent] QA FAST-PATH HIT: confidence={qa_match['confidence']}, "
                          f"q=\"{qa_match['best_question'][:50]}\"")
                    return json.dumps({
                        "semantically_similar_chunks": [
                            f"[Source: {m['doc_title']}, Page: {m['page']}]\n"
                            f"Q: {m['question']}\nA: {m['answer']}"
                            for m in qa_match["matches"]
                        ],
                        "graph_connections": [],
                        "graph_chains": [],
                        "related_entities": [],
                        "source_documents": [{"title": qa_match["source_doc"], "page": qa_match.get("source_page")}],
                        "retrieval_metadata": {
                            "strategy": "compactrag_fast_path",
                            "confidence": qa_match["confidence"],
                            "qa_matches": len(qa_match["matches"]),
                        },
                    }, ensure_ascii=False)
            except Exception as e:
                logger.debug(f"QA cache check failed: {e}")

        database = get_database()
        graph_connections = []
        discovered_entity_names = set()
        from google.cloud.spanner_v1 import param_types

        # ── Weighted Reciprocal Rank Fusion (RRF) ──
        # Fuses keyword, vector, and graph-boosted results using weighted RRF.
        # Based on Cormack et al. 2009 + Elastic 2024 weighted extension.
        # Graph acts as a BOOST signal on existing chunks, not additional chunks.
        _RRF_K = 60  # RRF constant
        _W_KEYWORD = 0.4   # keyword match weight
        _W_VECTOR = 1.0    # vector similarity weight (primary signal)
        _W_GRAPH = 0.3     # graph entity boost weight

        # ── Q1a: Keyword search (OR logic with scoring) ──
        _stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for",
                       "of", "and", "or", "not", "it", "its", "un", "una", "il", "la", "le", "di",
                       "da", "del", "che", "per", "con", "come", "sono", "nel", "dei", "gli", "ha",
                       "which", "what", "how", "does", "who", "when", "where", "this", "that",
                       "esiste", "quale", "quali", "cosa", "chi", "dove", "quando", "come"}
        import re as _re
        keywords = [_re.sub(r"[^\w]", "", w).lower() for w in user_intent.split()
                    if len(_re.sub(r"[^\w]", "", w)) > 2 and _re.sub(r"[^\w]", "", w).lower() not in _stopwords]
        kw_limit = min(len(keywords), 8)

        keyword_chunks = []  # (chunk_dict, rank)
        # ── Entity-scope JOIN (Q1) ──
        # When entity_scope is non-empty, we restrict the seed retrieval to
        # chunks that ChunkMentions any of those entities. Implementation:
        # add an EXISTS sub-select against ChunkMentions matching chunk.doc_id
        # + chunk.chunk_id and entity_id IN (@es0..@esN). When the scope is
        # empty we emit no extra clause, preserving the original behaviour.
        _es_join_clause = ""
        _es_params: dict = {}
        _es_types: dict = {}
        if entity_scope:
            _es_in = ", ".join(f"@es{i}" for i in range(len(entity_scope)))
            _es_join_clause = (
                " AND EXISTS (SELECT 1 FROM ChunkMentions cm "
                "WHERE cm.doc_id = chunk.doc_id AND cm.chunk_id = chunk.chunk_id "
                f"AND cm.entity_id IN ({_es_in}))"
            )
            _es_params = {f"es{i}": eid for i, eid in enumerate(entity_scope)}
            _es_types = {f"es{i}": param_types.STRING for i in range(len(entity_scope))}

        if keywords:
            # OR logic — any keyword match counts
            keyword_conditions = " OR ".join(
                [f"LOWER(chunk.chunk_text) LIKE @kw{i}" for i in range(kw_limit)]
            )
            keyword_sql = f"""
                SELECT chunk.chunk_text, chunk.chunk_type, chunk.page_number,
                       doc.title AS source_doc, chunk.chunk_id, chunk.doc_id,
                       doc.document_date
                FROM DocumentChunks chunk
                JOIN Documents doc ON doc.doc_id = chunk.doc_id
                WHERE ({keyword_conditions})
                  AND {_tenant_filter("chunk")}{_es_join_clause}
                LIMIT 20
            """
            kw_params = {f"kw{i}": f"%{kw}%" for i, kw in enumerate(keywords[:kw_limit])}
            kw_params["_tid"] = _tenant_id
            kw_params.update(_es_params)
            kw_types = {f"kw{i}": param_types.STRING for i in range(kw_limit)}
            kw_types["_tid"] = param_types.STRING
            kw_types.update(_es_types)
            try:
                with database.snapshot() as snapshot:
                    result = snapshot.execute_sql(keyword_sql, params=kw_params, param_types=kw_types)
                    for row in result:
                        chunk_text = (row[0] or "")[:1500]
                        keyword_chunks.append({
                            "text": chunk_text, "type": row[1], "page": row[2],
                            "source": row[3], "chunk_id": row[4], "doc_id": row[5],
                            "document_date": row[6] or "",
                            "distance": 0.0, "match": "keyword",
                        })
                tracker = get_tracker()
                if tracker:
                    tracker.track_spanner_read()
            except Exception as e:
                logger.debug(f"Keyword search failed: {e}")

        # ── Q1b: Vector search (ScaNN ANN index) — multi-query ──
        # Search with each query variant embedding, merge results
        vector_chunks = []
        _vec_seen = set()
        vector_sql = f"""
            SELECT chunk.chunk_text, chunk.chunk_type, chunk.page_number,
                   doc.title AS source_doc,
                   COSINE_DISTANCE(chunk.chunk_embedding, CAST(@query_emb AS ARRAY<FLOAT32>)) AS distance,
                   chunk.chunk_id, chunk.doc_id,
                   doc.document_date
            FROM DocumentChunks chunk
            JOIN Documents doc ON doc.doc_id = chunk.doc_id
            WHERE chunk.chunk_embedding IS NOT NULL
              AND {_tenant_filter("chunk")}{_es_join_clause}
            ORDER BY COSINE_DISTANCE(chunk.chunk_embedding, CAST(@query_emb AS ARRAY<FLOAT32>))
            LIMIT 20
        """
        def _vector_search_single(qemb):
            """Run vector search for a single query embedding."""
            results = []
            try:
                with database.snapshot() as snapshot:
                    _vparams = {"query_emb": qemb, "_tid": _tenant_id, **_es_params}
                    _vtypes = {"query_emb": param_types.Array(param_types.FLOAT32), "_tid": param_types.STRING, **_es_types}
                    rows = snapshot.execute_sql(
                        vector_sql,
                        params=_vparams,
                        param_types=_vtypes,
                    )
                    for row in rows:
                        results.append({
                            "text": (row[0] or "")[:1500], "type": row[1], "page": row[2],
                            "source": row[3], "distance": round(row[4], 4) if row[4] else None,
                            "chunk_id": row[5], "doc_id": row[6],
                            "document_date": row[7] or "",
                            "match": "vector",
                        })
                tracker = get_tracker()
                if tracker:
                    tracker.track_spanner_read()
            except Exception:
                pass
            return results

        with ThreadPoolExecutor(max_workers=4) as pool:
            all_vector_results = list(pool.map(_vector_search_single, all_embeddings))
        for batch in all_vector_results:
            for chunk in batch:
                prefix = chunk["text"][:150]
                if prefix not in _vec_seen:
                    _vec_seen.add(prefix)
                    vector_chunks.append(chunk)

        # ── Q2: GQL graph traversal (bidirectional) — for connections + boost ──
        # Gated by A2RAG-inspired adaptive gate: skip when query doesn't need graph.
        _GRAPH_TOKEN_BUDGET = 1500  # ~tokens for graph context in prompt
        _GRAPH_ENTITY_TYPES = [
            "Capability", "ApplicationComponent", "BusinessProcess",
            "BusinessActor", "Stakeholder", "SystemSoftware", "Goal",
        ]
        _GRAPH_DISTANCE_THRESHOLD = 0.45  # text-embedding-005 produces wider distances than gemini-embedding-2
        _tgt_name_cols = ", ".join(dict.fromkeys(
            f"tgt.{info['name_col']}"
            for info in ENTITY_TABLE_MAP.values()
        ))
        if enable_graph:
            print(f"[SearchAgent] GQL tenant filter: {_tenant_filter('src')}, _tid={_tenant_id}, scope={_search_scope}, datasets={_shared_datasets}")
            for _etype in _GRAPH_ENTITY_TYPES:
                _tinfo = ENTITY_TABLE_MAP.get(_etype)
                if not _tinfo:
                    continue
                # Two-step pre-filter to dodge the Spanner emulator quirk where
                # COSINE_DISTANCE is evaluated against zero-vector rows even when
                # WHERE clauses try to exclude them. Step 1: SELECT seed ids in
                # plain SQL (filter zero vectors first, THEN cosine). Step 2:
                # GQL traversal restricted to those ids.
                _seed_sql = f"""
                    SELECT {_tinfo['id_col']} AS sid
                    FROM {_tinfo['table']}
                    WHERE {_tinfo['embedding_col']} IS NOT NULL
                      AND ARRAY_LENGTH({_tinfo['embedding_col']}) > 0
                      AND {_tinfo['embedding_col']}[OFFSET(0)] != 0.0
                      AND {_tinfo['embedding_col']}[OFFSET(1)] != 0.0
                    ORDER BY COSINE_DISTANCE({_tinfo['embedding_col']}, CAST(@query_emb AS ARRAY<FLOAT32>))
                    LIMIT 5
                """
                seed_ids: list[str] = []
                try:
                    with database.snapshot() as snapshot:
                        for row in snapshot.execute_sql(
                            _seed_sql,
                            params={"query_emb": query_embedding},
                            param_types={"query_emb": param_types.Array(param_types.FLOAT32)},
                        ):
                            sid = row[0]
                            if sid:
                                seed_ids.append(sid)
                except Exception as _seed_err:
                    print(f"[SearchAgent] seed SQL error for {_tinfo['table']}: {_seed_err}")
                if not seed_ids:
                    continue

                # Plain SQL traversal (Spanner emulator's PROPERTY GRAPH support
                # silently drops typed edge alias declarations beyond the first
                # `AS XxxToYyy`, so GQL MATCH returns 0 even when the underlying
                # edge rows exist. We bypass the property graph and JOIN the edge
                # tables directly. Same shape, fully portable to Cloud Spanner.
                _ids_csv = ", ".join(f"'{s}'" for s in seed_ids)
                _src_name = _tinfo["name_col"]

                def _tgt_name_expr_for(_t: str) -> str:
                    info = ENTITY_TABLE_MAP.get(_t)
                    return info["name_col"] if info else "NULL"

                from services.schema_registry import EDGE_TABLE_MAP as _EDGE_MAP
                for _rel, _einfo in _EDGE_MAP.items():
                    _etable = _einfo["table"]
                    _sql = f"""
                        SELECT s.{_src_name} AS sn, e.target_id AS tid, e.target_type AS ttype, '{_rel}' AS rel
                        FROM {_etable} e
                        JOIN {_tinfo['table']} s ON s.{_tinfo['id_col']} = e.source_id
                        WHERE e.source_id IN ({_ids_csv})
                          AND e.source_type = '{_etype}'
                        LIMIT 5
                    """
                    try:
                        with database.snapshot() as snapshot:
                            for row in snapshot.execute_sql(_sql):
                                _sn, _tid, _ttype, _r = row[0], row[1], row[2], row[3]
                                if not _sn or not _ttype:
                                    continue
                                # Resolve target name from its own entity table.
                                _tinfo2 = ENTITY_TABLE_MAP.get(_ttype)
                                if not _tinfo2:
                                    continue
                                _tgt_name = None
                                with database.snapshot() as snap2:
                                    rs = list(snap2.execute_sql(
                                        f"SELECT {_tinfo2['name_col']} FROM {_tinfo2['table']} WHERE {_tinfo2['id_col']} = @id LIMIT 1",
                                        params={"id": _tid},
                                        param_types={"id": param_types.STRING},
                                    ))
                                    if rs:
                                        _tgt_name = rs[0][0]
                                if not _tgt_name:
                                    continue
                                conn = f"{_sn} ({_etype}) -[{_r}, EXTRACTED]-> {_tgt_name} ({_ttype})"
                                graph_connections.append(conn)
                                discovered_entity_names.add(_sn)
                                discovered_entity_names.add(_tgt_name)
                        tracker = get_tracker()
                        if tracker:
                            tracker.track_spanner_read()
                    except Exception as _sql_err:
                        # Some edge tables don't have source_type column — silently skip
                        pass
            graph_connections = list(dict.fromkeys(graph_connections))

            # ── Q2b: 2-hop GQL chains for multi-hop discovery ──
            _2HOP_PATTERNS = [
                ("SystemSoftware", "ApplicationComponent", "BusinessProcess"),
                ("SystemSoftware", "ApplicationComponent", "BusinessService"),
                ("ApplicationComponent", "BusinessProcess", "Goal"),
                ("ApplicationComponent", "BusinessProcess", "Capability"),
                ("Node", "SystemSoftware", "ApplicationComponent"),
            ]
            graph_chains = []
            for src_t, mid_t, tgt_t in _2HOP_PATTERNS:
                src_info = ENTITY_TABLE_MAP.get(src_t)
                mid_info = ENTITY_TABLE_MAP.get(mid_t)
                tgt_info = ENTITY_TABLE_MAP.get(tgt_t)
                if not (src_info and mid_info and tgt_info):
                    continue
                # Same two-step trick as the 1-hop query above (see comment).
                _seed_sql = f"""
                    SELECT {src_info['id_col']} AS sid
                    FROM {src_info['table']}
                    WHERE {src_info['embedding_col']} IS NOT NULL
                      AND ARRAY_LENGTH({src_info['embedding_col']}) > 0
                      AND {src_info['embedding_col']}[OFFSET(0)] != 0.0
                      AND {src_info['embedding_col']}[OFFSET(1)] != 0.0
                    ORDER BY COSINE_DISTANCE({src_info['embedding_col']}, CAST(@query_emb AS ARRAY<FLOAT32>))
                    LIMIT 3
                """
                seed_ids: list[str] = []
                try:
                    with database.snapshot() as snapshot:
                        for row in snapshot.execute_sql(
                            _seed_sql,
                            params={"query_emb": query_embedding},
                            param_types={"query_emb": param_types.Array(param_types.FLOAT32)},
                        ):
                            if row[0]:
                                seed_ids.append(row[0])
                except Exception as _e:
                    print(f"[SearchAgent] 2-hop seed error for {src_info['table']}: {_e}")
                if not seed_ids:
                    continue
                _ids_csv = ", ".join(f"'{s}'" for s in seed_ids)
                _gql_2hop = f"""
                    GRAPH KnowledgeGraph
                    MATCH (src:{src_info['table']})-[r1]-(mid:{mid_info['table']})-[r2]-(tgt:{tgt_info['table']})
                    WHERE src.{src_info['id_col']} IN ({_ids_csv})
                    RETURN
                      src.{src_info['name_col']} AS srcName,
                      '{src_t}' AS srcType,
                      LABELS(r1) AS rel1,
                      mid.{mid_info['name_col']} AS midName,
                      '{mid_t}' AS midType,
                      LABELS(r2) AS rel2,
                      tgt.{tgt_info['name_col']} AS tgtName,
                      '{tgt_t}' AS tgtType
                    LIMIT 3
                """
                try:
                    with database.snapshot() as snapshot:
                        result = snapshot.execute_sql(_gql_2hop)
                        for row in result:
                            # Flatten GQL LABELS() lists to strings
                            r1_str = row[2][0] if isinstance(row[2], list) and row[2] else str(row[2])
                            r2_str = row[5][0] if isinstance(row[5], list) and row[5] else str(row[5])
                            chain = f"{row[0]} ({row[1]}) -[{r1_str}, EXTRACTED]-> {row[3]} ({row[4]}) -[{r2_str}, EXTRACTED]-> {row[6]} ({row[7]})"
                            graph_chains.append(chain)
                            for name, typ in [(row[0], row[1]), (row[3], row[4]), (row[6], row[7])]:
                                if name and name != typ:
                                    discovered_entity_names.add(name)
                    tracker = get_tracker()
                    if tracker:
                        tracker.track_spanner_read()
                except Exception as _gql_err:
                    print(f"[SearchAgent] GQL error: {_gql_err}")
            graph_chains = list(dict.fromkeys(graph_chains))

            # ── Token budget: prioritize EXTRACTED edges, truncate to budget ──
            _CHARS_PER_TOKEN = 3

            def _confidence_sort_key(conn_str: str) -> int:
                if "EXTRACTED" in conn_str:
                    return 0
                if "INFERRED" in conn_str:
                    return 1
                return 2

            _conn_before = len(graph_connections)
            _chain_before = len(graph_chains)

            # Budget for 1-hop connections (2/3 of total)
            _conn_budget = (_GRAPH_TOKEN_BUDGET * 2 // 3) * _CHARS_PER_TOKEN
            _total = 0
            _budgeted = []
            for conn in sorted(graph_connections, key=_confidence_sort_key):
                if _total + len(conn) > _conn_budget:
                    break
                _budgeted.append(conn)
                _total += len(conn)
            graph_connections = _budgeted

            # Budget for 2-hop chains (1/3 of total)
            _chain_budget = (_GRAPH_TOKEN_BUDGET // 3) * _CHARS_PER_TOKEN
            _total = 0
            _budgeted_chains = []
            for chain in sorted(graph_chains, key=_confidence_sort_key):
                if _total + len(chain) > _chain_budget:
                    break
                _budgeted_chains.append(chain)
                _total += len(chain)
            graph_chains = _budgeted_chains

            print(f"[SearchAgent] GQL Q2: {_conn_before}->{len(graph_connections)} 1-hop + {_chain_before}->{len(graph_chains)} 2-hop (budget={_GRAPH_TOKEN_BUDGET}t), {len(discovered_entity_names)} entities")

            # ── Q3: Graph-guided chunk expansion via ChunkMentions ──
            graph_expanded_chunks = []
            if discovered_entity_names:
                _entity_ids = []
                for _etype in _GRAPH_ENTITY_TYPES:
                    _tinfo = ENTITY_TABLE_MAP.get(_etype)
                    if not _tinfo:
                        continue
                    _name_params = {}
                    _name_conditions = []
                    for i, name in enumerate(list(discovered_entity_names)[:10]):
                        _name_params[f"en{i}"] = name
                        _name_conditions.append(f"{_tinfo['name_col']} = @en{i}")
                    if not _name_conditions:
                        continue
                    try:
                        with database.snapshot() as snapshot:
                            _id_sql = (
                                f"SELECT {_tinfo['id_col']} FROM {_tinfo['table']} "
                                f"WHERE ({' OR '.join(_name_conditions)}) "
                                f"AND {_tenant_filter()} LIMIT 10"
                            )
                            _name_params["_tid"] = _tenant_id
                            _id_types = {f"en{i}": param_types.STRING for i in range(len(_name_conditions))}
                            _id_types["_tid"] = param_types.STRING
                            result = snapshot.execute_sql(_id_sql, params=_name_params, param_types=_id_types)
                            for row in result:
                                if row[0]:
                                    _entity_ids.append(row[0])
                        tracker = get_tracker()
                        if tracker:
                            tracker.track_spanner_read()
                    except Exception:
                        pass

                if _entity_ids:
                    _eid_params = {f"eid{i}": eid for i, eid in enumerate(_entity_ids[:15])}
                    _eid_conditions = " OR ".join([f"cm.entity_id = @eid{i}" for i in range(len(_eid_params))])
                    _eid_types = {f"eid{i}": param_types.STRING for i in range(len(_eid_params))}
                    try:
                        _eid_params["_tid"] = _tenant_id
                        _eid_types["_tid"] = param_types.STRING
                        with database.snapshot() as snapshot:
                            result = snapshot.execute_sql(f"""
                                SELECT DISTINCT dc.chunk_text, dc.chunk_type, dc.page_number, doc.title,
                                       dc.chunk_id, dc.doc_id, doc.document_date
                                FROM ChunkMentions cm
                                JOIN DocumentChunks dc ON dc.doc_id = cm.doc_id AND dc.chunk_id = cm.chunk_id
                                JOIN Documents doc ON doc.doc_id = dc.doc_id
                                WHERE ({_eid_conditions})
                                  AND {_tenant_filter("cm")}
                                LIMIT 10
                            """, params=_eid_params, param_types=_eid_types)
                            for row in result:
                                chunk_text = (row[0] or "")[:1500]
                                graph_expanded_chunks.append({
                                    "text": chunk_text, "type": row[1], "page": row[2],
                                    "source": row[3], "chunk_id": row[4], "doc_id": row[5],
                                    "document_date": row[6] or "",
                                    "distance": None, "match": "graph_expanded",
                                })
                        tracker = get_tracker()
                        if tracker:
                            tracker.track_spanner_read()
                    except Exception as e:
                        logger.debug(f"Graph chunk expansion failed: {e}")
                print(f"[SearchAgent] Q3 Graph expansion: {len(graph_expanded_chunks)} chunks from {len(_entity_ids)} entity IDs via ChunkMentions")
        else:
            # Graph gate OFF — skip Q2, Q2b, Q3 entirely (vector-only retrieval)
            graph_chains = []
            graph_expanded_chunks = []
            print(f"[SearchAgent] Graph gate OFF — skipping Q2/Q3, using keyword+vector only")

        # ── Weighted RRF Fusion ──
        # Combine keyword + vector + graph-expanded results using RRF.
        # Graph-expanded chunks enter the candidate pool; reranker filters noise.
        import re as _re

        # Deduplicate all candidates by text prefix
        seen_prefixes = set()
        all_candidates = []
        for c in keyword_chunks + vector_chunks + graph_expanded_chunks:
            prefix = c["text"][:150]
            if prefix not in seen_prefixes:
                seen_prefixes.add(prefix)
                all_candidates.append(c)

        # Build rank maps (text_prefix → rank in each list)
        kw_rank = {}
        for i, c in enumerate(keyword_chunks):
            prefix = c["text"][:150]
            if prefix not in kw_rank:
                kw_rank[prefix] = i + 1  # 1-indexed

        vec_rank = {}
        for i, c in enumerate(vector_chunks):
            prefix = c["text"][:150]
            if prefix not in vec_rank:
                vec_rank[prefix] = i + 1

        # Graph-expanded rank map
        graph_rank = {}
        for i, c in enumerate(graph_expanded_chunks):
            prefix = c["text"][:150]
            if prefix not in graph_rank:
                graph_rank[prefix] = i + 1

        # Compute RRF score for each candidate
        graph_entity_names_lower = {n.lower() for n in discovered_entity_names}
        _W_GRAPH_EXPANDED = 0.5  # Weight for graph-expanded chunks (higher than boost)
        for c in all_candidates:
            prefix = c["text"][:150]
            rrf_score = 0.0

            # Keyword contribution
            if prefix in kw_rank:
                rrf_score += _W_KEYWORD / (_RRF_K + kw_rank[prefix])

            # Vector contribution
            if prefix in vec_rank:
                rrf_score += _W_VECTOR / (_RRF_K + vec_rank[prefix])

            # Graph-expanded contribution (from ChunkMentions)
            if prefix in graph_rank:
                rrf_score += _W_GRAPH_EXPANDED / (_RRF_K + graph_rank[prefix])

            # Graph boost: if chunk mentions any graph-discovered entity, boost its score
            # Weight boost by confidence: EXTRACTED = full, INFERRED = half
            if graph_entity_names_lower:
                chunk_lower = c["text"].lower()
                mentions = sum(1 for ent in graph_entity_names_lower if ent in chunk_lower)
                if mentions > 0:
                    # Compute confidence-weighted graph boost from connection strings
                    _extracted_count = sum(1 for gc in graph_connections if "EXTRACTED" in gc)
                    _total_gc = len(graph_connections) or 1
                    _confidence_factor = 0.5 + 0.5 * (_extracted_count / _total_gc)  # 0.5-1.0 range
                    rrf_score += _W_GRAPH * _confidence_factor * mentions / (_RRF_K + 1)
                    if "graph" not in c["match"]:
                        c["match"] = c["match"] + "+graph"

            c["rrf_score"] = round(rrf_score, 6)

        # ── Reranking: Vertex AI Ranking API (semantic-ranker-512) ──
        # Instead of vector-first heuristic, send ALL RRF candidates to a
        # cross-encoder reranker that scores each chunk's relevance to the query.
        # Fallback to RRF score ordering if the reranker is unavailable.
        _TOTAL_RESULTS = 15
        all_candidates.sort(key=lambda c: c["rrf_score"], reverse=True)
        pre_rerank = all_candidates[:30]  # Send top-30 RRF candidates to reranker

        try:
            from google.cloud.discoveryengine_v1 import RankServiceClient, RankRequest, RankingRecord
            _rerank_client = RankServiceClient()
            _project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not _project:
                raise RuntimeError("GOOGLE_CLOUD_PROJECT env var is required for Vertex AI Ranking API")
            _ranking_config = f"projects/{_project}/locations/global/rankingConfigs/default_ranking_config"

            records = []
            for i, c in enumerate(pre_rerank):
                records.append(RankingRecord(
                    id=str(i),
                    content=c["text"][:1000],  # Reranker input limit
                ))

            rerank_response = _rerank_client.rank(
                request=RankRequest(
                    ranking_config=_ranking_config,
                    model="semantic-ranker-512@latest",
                    top_n=_TOTAL_RESULTS,
                    query=user_intent,
                    records=records,
                )
            )

            tracker = get_tracker()
            if tracker:
                tracker.track_rerank(num_records=len(records))

            # Reorder candidates by reranker score
            reranked_chunks = []
            for record in rerank_response.records:
                idx = int(record.id)
                c = pre_rerank[idx]
                c["rerank_score"] = round(record.score, 4)
                reranked_chunks.append(c)
            chunks = reranked_chunks
            _rerank_used = True
            print(f"[SearchAgent] Reranked: {len(chunks)} chunks via Vertex AI Ranking API")

        except Exception as e:
            logger.debug(f"Reranker unavailable ({e}), falling back to RRF ordering")
            chunks = pre_rerank[:_TOTAL_RESULTS]
            _rerank_used = False
            print(f"[SearchAgent] RRF Fallback: {len(chunks)} chunks (reranker unavailable)")

        # ── Information Gain Pruning (IGP) — DISABLED ──
        # Based on "Less is More for RAG" (arXiv 2601.17532).
        # Tested: hurts entity recall significantly (-29%) because it prunes chunks
        # that contain expected entities but don't reduce generator uncertainty.
        # The paper's IG metric optimizes for generation quality, not retrieval coverage.
        # TODO: revisit with re-ordering approach (sort by IG, don't prune) or
        # use only for L3 faithfulness optimization with min_chunks=10.
        # try:
        #     chunks = _information_gain_pruning(client, user_intent, chunks)
        # except Exception as e:
        #     logger.debug(f"IGP failed ({e}), keeping all reranked chunks")

        kw_count = sum(1 for c in chunks if "keyword" in c["match"])
        vec_count = sum(1 for c in chunks if "vector" in c["match"])
        boosted = sum(1 for c in chunks if "graph" in c["match"])
        print(f"[SearchAgent] Final: kw={kw_count}, vec={vec_count}, graph-boosted={boosted}, total={len(chunks)}")

        # Build unique source document references with metadata
        seen_sources = set()
        source_documents = []
        for c in chunks:
            key = f"{c['source']}|{c['page']}"
            if key not in seen_sources:
                seen_sources.add(key)
                source_documents.append({
                    "title": c["source"],
                    "page": c["page"],
                    "match_type": c["match"],
                })

        # Prepend source metadata to each chunk so it survives LLM schema conversion
        # Separate image chunks: include [IMAGE:...] tags WITH Vision caption for LLM context
        enriched_chunks = []
        image_results = []
        _img_idx = 0
        for c in chunks:
            page_label = f", Page: {c['page']}" if c.get("page") else ""
            date_label = f", Date: {c['document_date']}" if c.get("document_date") else ""
            if c.get("type") == "image" and c.get("chunk_id") and c.get("doc_id"):
                img_id = f"img_{_img_idx}"
                caption = c.get("text", "").strip() or "Diagram/figure from this document page."
                enriched_chunks.append(
                    f"[Source: {c['source']}{date_label}{page_label}]\n"
                    f"[IMAGE:{img_id}:{c['doc_id']}:{c['chunk_id']}] — {caption}"
                )
                image_results.append({
                    "image_id": img_id,
                    "doc_id": c["doc_id"],
                    "chunk_id": c["chunk_id"],
                    "source_doc": c["source"],
                    "page_number": c.get("page"),
                })
                _img_idx += 1
            else:
                enriched_chunks.append(f"[Source: {c['source']}{date_label}{page_label}]\n{c['text']}")

        if image_results:
            print(f"[SearchAgent] Images: {len(image_results)} image chunks included in results")
            # Store for deterministic injection by coordinator callback
            try:
                from agents.coordinator import _pending_image_chunks
                import agents.coordinator as _coord
                _coord._pending_image_chunks = image_results
            except ImportError:
                pass

        if started_here:
            from services.cost_tracker import stop_tracking
            _tracker = stop_tracking()

        retrieval_metadata = {
            "strategy": "rrf_rerank" if _rerank_used else "rrf_fallback",
            "model": EMBEDDING_MODEL,
            "selected_scope": _search_scope,
            "fusion": {"rrf_k": _RRF_K, "w_keyword": _W_KEYWORD, "w_vector": _W_VECTOR, "w_graph": _W_GRAPH},
            "chunks_found": len(chunks),
            "keyword_candidates": len(keyword_chunks),
            "vector_candidates": len(vector_chunks),
            "graph_boosted": sum(1 for c in chunks if "graph" in c.get("match", "")),
            "connections_found": len(graph_connections),
            "chains_found": len(graph_chains),
            "graph_entities_discovered": len(discovered_entity_names) if discovered_entity_names else 0,
            "graph_distance_threshold": _GRAPH_DISTANCE_THRESHOLD,
            "graph_budget_tokens": _GRAPH_TOKEN_BUDGET if enable_graph else 0,
            "image_chunks_found": len(image_results),
            "query_cost": _tracker.to_dict() if _tracker else None,
        }
        # Store for deterministic injection by coordinator callback (same pattern as images)

        try:
            import agents.coordinator as _coord
            _coord._pending_retrieval_metadata = retrieval_metadata
            _coord._pending_graph_connections = graph_connections
            _coord._pending_graph_chains = graph_chains
        except ImportError:
            pass

        if hasattr(tool_context, "state"):
            tool_context.state["query_cost"] = _tracker.to_dict() if _tracker else {}
            tool_context.state["retrieval_meta"] = retrieval_metadata

        return json.dumps({
            "semantically_similar_chunks": enriched_chunks,
            "graph_connections": graph_connections,
            "graph_chains": graph_chains,
            "related_entities": [],
            "source_documents": source_documents,
            "image_chunks": image_results,
            "retrieval_metadata": retrieval_metadata,
        }, ensure_ascii=False)

    except Exception as e:
        logger.warning(f"Spanner hybrid search failed: {e}")
        return json.dumps({
            "semantically_similar_chunks": [],
            "graph_connections": [],
            "related_entities": [],
            "retrieval_metadata": {
                "strategy": "fallback_empty",
                "error": str(e),
            },
        })


from google.genai import types as genai_types

search_agent = LlmAgent(
    name="SearchAgent",
    model="gemini-2.5-flash",
    generate_content_config=genai_types.GenerateContentConfig(

        tool_config=genai_types.ToolConfig(
            function_calling_config=genai_types.FunctionCallingConfig(
                mode="AUTO",
            )
        )
    ),
    description="Intelligent search engine for the Knowledge Base. Hybrid retrieval: vector search + keyword search + GQL graph traversal + reranking on Spanner.",
    instruction="""
    You are the intelligent search engine for the Knowledge Base.
    You MUST ALWAYS call tool_query_spanner_graph as your first and only tool.

    Pass the user's query exactly as received. Translate to English if needed
    (indexed documents are predominantly in English).

    The tool automatically performs:
    - Keyword search for specific terms in document chunks
    - Vector similarity search on chunk embeddings
    - GQL graph traversal for multi-hop ArchiMate connections
    - Vertex AI reranking for relevance scoring

    Return the COMPLETE tool result as your output. You MUST preserve ALL fields
    from the tool result in your response, including:
    - semantically_similar_chunks: all text chunks AND [IMAGE:...] tagged chunks
    - graph_connections: all graph traversal results
    - source_documents: all source references
    - image_chunks: all image chunk metadata (image_id, doc_id, chunk_id, source_doc, page_number)

    CRITICAL: Do NOT drop or omit image_chunks. If the tool returns image data,
    you MUST include it in your output exactly as returned.
    """,
    tools=[tool_query_spanner_graph, tool_query_bigquery, tool_check_dataplex_metadata],
    output_schema=SearchResult,
    output_key="last_search_result"
)
