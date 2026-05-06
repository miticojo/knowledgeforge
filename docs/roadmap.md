# KnowledgeForge roadmap

This page tracks what is implemented in `kb-agent` today and what is planned next. For the architecture itself, see [`README.md`](../README.md) and [`docs/concepts/rag-primer.md`](concepts/rag-primer.md).

## Recently shipped

The last five commits, newest first:

- `857f80a` — KnowledgeForge as a Gemini CLI / Claude Code / Codex extension (single-source distribution via `gemini-extension.json`, `.claude-plugin/`, `.codex-plugin/`).
- `0e4d0b6` — Laptop-runnable demo stack: `docker-compose.demo.yml` with the Spanner emulator, seed scripts, and gold dataset under [`demo/`](../demo/README.md).
- `b60eb62` — `POST /ingest/git` endpoint and a **Code Repository** ingestion tab in the frontend.
- `b295950` — Coordinator wires Knowledge Catalog + BigQuery MCP toolboxes (opt-in via `KC_TOOLBOX_ENABLED` / `BQ_TOOLBOX_ENABLED`).
- `3fa9d46` — Git+AST ingester for Python, TypeScript, Java, Go, and SQL (treats source code as a first-class document).

## What is implemented

### Knowledge graph (operational)

ArchiMate 3.2-aligned ontology with 22 entity types across 5 layers (Strategy, Business, Application, Technology, Motivation) and 11 relationship types — defined in `kb-agent/ontology.yaml` and enforced via Pydantic `Literal` enums in `kb-agent/models/ontology.py`.

- **Extraction**: Gemini 2.5 Flash with Controlled Generation (`response_schema`) → 100 % schema compliance, no regex normalization. Confidence labels (`EXTRACTED`, `INFERRED`, `AMBIGUOUS`) on every edge.
- **Chunking & embeddings**: semantic chunking (~1500 chars, ~200 overlap) with `gemini-embedding-2-preview` (multimodal, 768 dim). Each chunk and entity is embedded individually.
- **Entity reconciliation** ([iText2KG](https://arxiv.org/abs/2409.03284)-inspired): exact match → vector similarity (`COSINE_DISTANCE < 0.15`) → new entity. Per-type batches with in-memory cache.
- **Spanner persistence**: atomic upsert via `database.batch()` in `services/graph_writer.py`. Idempotent — re-ingesting a document replaces the previous version.
- **Schema**: 23 node tables + 12 edge tables + a `KnowledgeGraph` Property Graph definition in `database/spanner_schema.sdl`.

### Hybrid retrieval (operational)

[HippoRAG](https://arxiv.org/abs/2405.14831)-inspired pipeline in `kb-agent/agents/search.py`:

1. **Q1 — hybrid text retrieval**: `UNION ALL` of keyword (`LIKE`) and vector ANN (`COSINE_DISTANCE`) → seed chunks.
2. **Q2 — bidirectional GQL traversal**: 1- and 2-hop GQL on 7 ArchiMate entity types, filtered by embedding similarity (`< 0.5`).
3. **Q3 — graph→text bridge**: chunks that mention graph-discovered entities, joined via `ChunkMentions`.
4. **Weighted RRF fusion** (Cormack 2009) — keyword 0.4, vector 1.0, graph 0.3 — with a vector-first slot guarantee to prevent displacement.
5. **Vertex AI semantic reranker** (`semantic-ranker-512`) — top-30 → top-15.

### Agentic orchestration (operational)

- **Coordinator agent** (`kb-agent/agents/coordinator.py`) on Google ADK, using AG-UI Server-Sent Events via `ag_ui_adk`.
- **Specialist multi-query**: fact / context / temporal sub-queries with an adaptive gate that decides whether the graph is worth traversing.
- **Synthesis & verification**: extract facts, synthesize, trace 2-hop graph chains, label every claim `SUPPORTED` / `CONTRADICTED` / `UNSUPPORTED`, prefer newer documents on conflict.
- **Deterministic image injection** via `after_model_callback`.

### MCP server (operational)

`kb-mcp-server/` exposes 8 tools (`get_brief`, `query`, `get_entity`, `get_connections`, `god_nodes`, `graph_stats`, `check_conformance`, `impact_analysis`) over the Model Context Protocol, callable from Codex, Cursor, and any other MCP-compatible client.

### Frontend (operational)

Next.js 16 + React 19 + CopilotKit v1.54. Two-tab layout (Ingestion / Search), live pipeline updates via SSE interceptor on `TOOL_CALL_*` events, force-directed graph viz with ArchiMate layer clustering, collapsible `<sources>` box parsed out of every coordinator response.

### Security (operational)

- Vertex AI Model Armor as an ADK `before_agent_callback` (toggle via `ENABLE_MODEL_ARMOR`).
- Identity-Aware Proxy on the Cloud Run frontend.

### Evaluation framework (operational)

`evaluation/` runs 3 levels on a benchmark dataset: L1 KG construction F1, L2 retrieval A/B (graph vs vector), L3 answer quality (LLM-as-judge). HotpotQA support out of the box.

---

## What is planned

### Done

- ✅ **Milestone H — Git + AST ingestion.** Source-as-document ingester for Python, TypeScript, Java, Go, and SQL. Exposed via `POST /ingest/git` and the **Code Repository** tab in the frontend.
- ✅ **Milestone I — Demo kit.** Laptop-runnable stack via [`docker-compose.demo.yml`](../docker-compose.demo.yml) with the Spanner emulator, seed scripts, gold dataset, asciinema walkthrough (embedded in README) and the [`docs/quickstart-demo.md`](quickstart-demo.md) guide. Activated by `DEMO_MODE=true`.
- ✅ **Milestone A — Knowledge Catalog + BigQuery MCP toolboxes.** Opt-in coordinator tools wired into the agent (`KC_TOOLBOX_ENABLED`, `BQ_TOOLBOX_ENABLED`). KnowledgeForge coexists with Google's `data-agent-kit` toolboxes instead of replacing them.
- ✅ **Milestone E — Multi-CLI extension distribution.** Single-source manifests for Gemini CLI (`gemini-extension.json`), Claude Code (`.claude-plugin/`), and Codex (`.codex-plugin/`).
- ✅ **Milestone B — Knowledge Catalog exporter.** `services/kc_exporter.py` projects DataObjects + Access/Realization edges into KC as Entry/Aspect/EntryLink. Opt-in via `KC_SYNC_ENABLED`. See [Knowledge Catalog Bridge](concepts/knowledge-catalog-bridge.md).
- ✅ **Milestone C — Knowledge Catalog reverse importer.** `services/kc_importer.py` consumes Pub/Sub change events from Dataplex and projects whitelisted KC Entry types (BigQuery / Spanner / CloudSQL / AlloyDB / Bigtable) into the KF graph as `DataObject` nodes. Opt-in via `KC_IMPORT_ENABLED` + `KC_IMPORT_SUBSCRIPTION`.
- ✅ **Milestone D — Glossary bridge.** `services/glossary_sync.py` syncs KF `BusinessObject` ↔ KC business glossary terms bidirectionally with conflict policy (last-write-wins for descriptions, union for synonyms). Configured via `KC_GLOSSARY_ID`.
- ✅ **Milestone F — Reference architecture document.** [`docs/architectures/kc-kf-spanner-graph.md`](architectures/kc-kf-spanner-graph.md) documents how KF complements Google's KC + Vertex AI Search + data-agent-kit.
- ✅ **Milestone J — Graph navigation UI.** Standalone `/graph` page with canvas, search, ArchiMate layer filters, hub/orphan filters; backend navigation endpoints (`GET /graph/neighbors`, `GET /graph/search`); chat entity-scope filter (`X-Entity-Scope` header). See [`docs/concepts/graph-navigation.md`](concepts/graph-navigation.md).
- ✅ **Milestone 6 — Multi-tenant hardening.** Per-tenant cost dashboard endpoint (`/tenant/dashboard`), Firebase-optional auth + login page, full isolation test suite (`tests/test_tenant_isolation.py`), `tenant_id` query degradation when column is missing. See [`docs/multi-tenancy.md`](multi-tenancy.md).
- ✅ **CI / supply-chain hygiene.** GitHub Actions workflow (backend, frontend, secret-scan, compose, lint), npm audit cleanup (critical 1→0, high 9→1).
- ✅ **Schema fix** — `Documents.doc_id STRING(MAX)` so synthesized git ingest IDs (`git:<repo>@<sha>:<file>`) fit; writer errors now propagate to `/ingest/git` job status.

### Planned

- **Milestone G — TM Forum SID overlay.** Optional industry overlay (telco) on top of ArchiMate so that `Customer`, `Product`, `Service`, `Resource` map cleanly to SID classes.
- **Milestone 1 — Graph extension to remaining ArchiMate layers.** Add Physical, Migration & Implementation layers (`Facility`, `Equipment`, `WorkPackage`, `Deliverable`, `Plateau`, `Gap`). Driver: enterprise Cloud runbooks and project epics.

---

## How to propose changes

Open a GitHub issue describing the use case before opening a PR. See [`CONTRIBUTING.md`](../CONTRIBUTING.md).
