# A primer on RAG, GraphRAG, and AgenticRAG

If you have heard "RAG" but never built one, this page is for you. It explains the three retrieval paradigms that KnowledgeForge implements, in plain English, with pointers to the actual code.

## 1. RAG — Retrieval-Augmented Generation

LLMs are great at language, terrible at facts they were not trained on. **RAG** fixes this by:

1. **Retrieving** relevant chunks of text from your private documents (semantic search via vector embeddings).
2. **Augmenting** the LLM prompt with those chunks ("here are 5 passages — answer using these").
3. **Generating** the answer.

```
question → embed → vector search → top-K chunks → LLM(prompt + chunks) → answer
```

Strengths: simple, works for FAQ-style questions.
Weaknesses: each chunk is judged in isolation. The model has no idea how concepts relate.

**Where this lives in KnowledgeForge:** vector search runs against `DocumentChunks` in Spanner. See `kb-agent/agents/search.py` (`COSINE_DISTANCE`).

## 2. GraphRAG — Retrieval over a Knowledge Graph

Real knowledge has **structure**. "Service A depends on Database B which is hosted on Cluster C" is information that no isolated chunk captures cleanly. **GraphRAG** builds a knowledge graph from your documents and uses it during retrieval.

```
docs ──► entity & relationship extraction ──► knowledge graph
                                                    │
question ──► vector search + graph traversal ──► chunks + connected entities ──► LLM
```

So for "what breaks if we shut down Database B?", a GraphRAG system can traverse 1–3 hops of the graph and surface every dependent service — not just chunks that happen to mention "Database B".

**Where this lives in KnowledgeForge:**
- Extraction: `kb-agent/agents/` uses Gemini Controlled Generation against an **ArchiMate 3.2** ontology (22 entity types, 11 relationship types). Every edge gets a `confidence` label: `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`.
- Storage: Cloud Spanner Graph. See `database/spanner_schema.sdl` and `kb-agent/ontology.yaml`.
- Traversal: GQL queries in `kb-agent/agents/search.py` (1-hop, 2-hop chains, ChunkMentions join).
- Inspired by [HippoRAG](https://arxiv.org/abs/2405.14831) (Personalized PageRank) and [iText2KG](https://arxiv.org/abs/2409.03284) (incremental entity reconciliation).

## 3. AgenticRAG — the LLM decides how to retrieve

Plain RAG retrieves once, then answers. But hard questions need **planning**: rephrase the query, decide whether to consult the graph, retrieve again, verify claims, possibly call external tools.

**AgenticRAG** wraps the retrieval pipeline in an LLM agent that can:
- Reformulate the user query (specialist queries: fact / context / temporal).
- Call retrieval as a **tool** (function-calling).
- Decide when graph traversal is worth the cost.
- Verify each generated claim against retrieved evidence.
- Loop if confidence is low.

```
user query
    │
    ▼
┌────────────────────────────────────┐
│  Coordinator LLM (Gemini 2.5)     │
│  - rephrases the query             │
│  - calls retrieval tool(s)         │
│  - synthesises + verifies          │
└────────────────────────────────────┘
    │ tool calls ▲
    ▼            │
[ retrieval pipeline = vector + graph + keyword + reranker ]
```

**Where this lives in KnowledgeForge:**
- Orchestration: Google **Agent Development Kit (ADK)** in `kb-agent/agents/coordinator.py`.
- Streaming protocol: **AG-UI** (Server-Sent Events) via `ag_ui_adk`, consumed by the frontend through CopilotKit.
- Tool exposed to the LLM: `tool_query_spanner_graph` (in `kb-agent/agents/search.py`).
- Verification: synthesis step labels each claim `SUPPORTED`, `CONTRADICTED`, or `UNSUPPORTED`.

## How KnowledgeForge combines all three

KnowledgeForge is **AgenticRAG over GraphRAG**:

1. The LLM coordinator receives a user question.
2. It generates 3 specialist sub-queries (fact / context / temporal) and decides whether the graph is needed (adaptive gate).
3. The retrieval tool runs **vector + keyword + graph** searches in parallel, then fuses them with **Reciprocal Rank Fusion (RRF)**, then reranks with Vertex AI's semantic ranker.
4. The coordinator synthesises an answer, traces 2-hop graph chains for dependency reasoning, verifies every claim against sources, and returns sources + images deterministically injected.

End result: answers that are grounded in your documents, traceable to specific pages, and aware of structural relationships between concepts.

## Further reading

- [Contextual Retrieval — research note](https://arxiv.org/abs/2410.16924)
- [HippoRAG (NeurIPS 2024)](https://arxiv.org/abs/2405.14831)
- [iText2KG (2024)](https://arxiv.org/abs/2409.03284)
- [Graphify](https://github.com/safishamsi/graphify) — confidence-labeled edges
- [The Open Group — ArchiMate 3.2](https://pubs.opengroup.org/architecture/archimate32-doc/)
