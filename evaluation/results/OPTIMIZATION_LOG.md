# Optimization Log — KB Retrieval & Answer Quality

## Session: 2026-04-05/06

### Baseline (pre-optimization)
| Metric | Value |
|--------|-------|
| L1 Entity Micro-F1 | 0.081 |
| L1 Rel Type Coverage | 1.0 |
| L1 Duplicate Entities | 0 |
| L2 Full Pipeline Recall | 0.478 |
| L2 Vector-Only Recall | 0.732 |
| L2 Graph Uplift | -0.255 |
| L2 Graph Helps | 0/30 questions |
| L3 Faithfulness | 2.87/5 |
| L3 Relevancy | 4.77/5 |
| L3 Correctness | 1.57/5 |
| L3 Overall | 3.07/5 |

### Optimization Steps (cumulative)

| Step | Change | Graph Uplift | Pipeline Recall | L3 Correctness |
|------|--------|-------------|-----------------|----------------|
| 0. Baseline | Naive concat, 2000 tok chunks, no index | -0.255 | 0.478 | 1.57 |
| 1. Weighted RRF | keyword=0.4, vector=1.0, graph=0.3 | -0.255 | 0.478 | — |
| 2. Smaller chunks | 2000→500 tokens (1500 chars) | -0.078 | 0.466 | — |
| 3. ScaNN + LIMIT 40 | Vector index + more candidates | -0.044 | 0.499 | — |
| 4. Vertex AI Reranker | semantic-ranker-512 post-retrieval | **+0.031** | **0.575** | 1.83 |
| 5. Extract-then-Generate | 3-step prompt + ThinkingConfig(4096) | +0.031 | 0.575 | **2.13** |
| 6. 2-hop GQL chains | Typed A→B→C patterns for impact analysis | +0.008 | 0.552 | 2.13 |
| 7. Multi-query expansion | 3 query variants via Gemini (RAG-Fusion) | +0.027 | 0.570 | **2.27** |
| 7. CRAG verification | Post-gen claim verification step in prompt | +0.027 | 0.570 | **2.27** |

### Steps 8-10: Advanced Optimizations

| Step | Change | Graph Uplift | Pipeline Recall | L3 Correctness | L3 Overall |
|------|--------|-------------|-----------------|----------------|------------|
| 8. ChunkMentions expansion | Graph-guided chunk retrieval via entity IDs | +0.038 | 0.581 | 2.27 | 3.38 |
| 9. Contextual Retrieval | Context prefix per chunk before embedding | -0.007 | **0.613** | **2.73** | **3.51** |
| 10. Task Instructions | "search_document:"/"search_query:" prefix | -0.101 | 0.606 | 2.50 | 3.46 |

**Step 10 REVERTED**: Task instructions improved vector-only recall (+14%, 0.620→0.707) but hurt pipeline correctness (-8%) because overly precise vector search displaced graph-expanded chunks. Contextual Retrieval alone (Step 9) is the optimal configuration.

### Model Benchmark (Coordinator)
| Model | Faithfulness | Correctness | Overall |
|-------|-------------|-------------|---------|
| **Gemini 2.5 Flash** (budget=4096) | **3.57** | **2.27** | **3.50** |
| Gemini 3.1 Pro (LOW) | 3.07 | 1.93 | 3.27 |
| Gemini 3 Flash (LOW) | 2.43 | 2.27 | 3.00 |
| Gemini 3 Flash (HIGH) | 1.87 | 2.37 | 2.93 |
| Gemini 3 Flash (LOW) + independent judge | 2.20 | 2.27 | 2.90 |

### Final State (after Step 9 — Contextual Retrieval, best config)
| Metric | Baseline | Final | Delta |
|--------|----------|-------|-------|
| L2 Vector-Only Recall | 0.544 | **0.620** | +14% |
| L2 Pipeline Recall | 0.478 | **0.613** | +28% |
| L2 Graph Uplift | -0.255 | **-0.007** | nearly neutral |
| L3 Faithfulness | 2.87 | **3.23** | +13% |
| L3 Relevancy | 4.77 | **4.57** | -4% |
| L3 Correctness | 1.57 | **2.73** | +74% |
| L3 Overall | 3.07 | **3.51** | +14% |

### Reranker Benchmark
| Strategy | Avg Recall | Latency | Winner |
|----------|-----------|---------|--------|
| RRF (no rerank) | 0.558 | baseline | — |
| Vertex AI Ranking API | 0.558 | 754ms | **14x faster** |
| Gemini 2.5 Flash | 0.558 | 10432ms | Same quality |

### Infrastructure Changes
| Component | Before | After |
|-----------|--------|-------|
| Chunks per doc | ~29 (2000 tok) | ~63 (500 tok) |
| Total chunks | 281 | 1075 |
| Vector index | brute-force | ScaNN ANN |
| Fusion | naive concat | Weighted RRF |
| Reranker | none | Vertex AI Ranking API |
| Graph traversal | GRAPH_TABLE unidirectional | GQL bidirectional |
| Graph distance threshold | 0.4 | 0.35 |
| Answer prompt | simple | Extract-then-Generate 3-step |
| Thinking | none | ThinkingConfig(4096) |
| Temperature | default | 0.1 |

### Bug Fixes
| Bug | Impact | Fix |
|-----|--------|-----|
| mode=ANY infinite loop | 992x document duplication | mode→AUTO + state cleanup |
| No idempotency | Duplicate docs on re-ingestion | Title check + cascade delete |
| Keyword AND too strict | 0 matches on most queries | Switched to OR with stopwords |
| _split_text_semantically | Ignored \n (only \n\n) | Split on \n when block > chunk_size |
| ROW_NUMBER unsupported | SQL error on Spanner | Python-side dedup |

---

## Session: 2026-04-12 — Graphify Pattern Adoption

### Changes Applied

| Step | Change | Description |
|------|--------|-------------|
| 11. Confidence Labels | Edge confidence (EXTRACTED/INFERRED/AMBIGUOUS) | DDL migration on 11 edge tables, Controlled Gen prompt updated, RRF boost weighted by confidence, AMBIGUOUS edges filtered from graph traversal |
| 12. Token Budget | Graph traversal output capped at 1500 tokens | Prioritizes EXTRACTED edges, truncates to budget. 2/3 for 1-hop, 1/3 for 2-hop chains |
| 13. God Nodes | Graph analytics endpoints | `get_god_nodes()`, `get_graph_stats()` at `/graph/god-nodes`, `/graph/stats` |
| 14. Knowledge Brief | Structured KB overview for agents | `generate_brief()` at `/graph/brief` — core entities, relationships, gaps, sources |
| 15. MCP Server | KB exposed to external AI agents | `kb-mcp-server/` with 6 tools (brief, query, entity, connections, god_nodes, stats) |

### Bug Fixes (Session 2026-04-12)
| Bug | Impact | Fix |
|-----|--------|-----|
| service_tier="SERVICE_TIER_FLEX" | Contextual Retrieval silently failing on AI Studio API | Changed to `"flex"` (lowercase) per official docs |
| Spanner batch_write overflow | Documents with 200+ entities fail to write chunks | Chunked batch_write into 5000-mutation batches |

### Benchmark Results (L2, ArchiSurance 16 docs, 1020 chunks)

| Metric | Baseline (Step 9) | Post-Graphify (Step 15) | Delta |
|--------|-------------------|------------------------|-------|
| L2 Pipeline Recall | 0.613 | **0.628** | **+2.4%** |
| L2 Vector-Only Recall | 0.620 | **0.699** | **+12.7%** |
| L2 Graph Uplift | -0.007 | -0.071 | needs gate tuning |
| L2 Multi-hop Uplift | N/A | **+0.002** | positive |
| Graph Helps | 0/30 | **3/30** | +3 questions |

**Key insight**: The vector recall improvement (+12.7%) is primarily from the `service_tier="flex"` fix that unblocked Contextual Retrieval. The confidence labels and token budget provide structural improvements that will compound as the graph gate is tuned.

### Edge Confidence Distribution (1732 edges)
| Confidence | Count | Percentage |
|------------|-------|------------|
| EXTRACTED  | 1677  | 97% |
| INFERRED   | 55    | 3% |
| AMBIGUOUS  | 0     | 0% |

### New Infrastructure
| Component | Status |
|-----------|--------|
| Confidence column on 11 edge tables | DDL migrated + deployed |
| Graph analytics endpoints (3 new) | Deployed to Cloud Run |
| Knowledge Brief generator | Deployed to Cloud Run |
| MCP Server (`kb-mcp-server/`) | Created, tested E2E against Cloud Run |
| Entity/Connections endpoints (2 new) | Deployed to Cloud Run |

### Steps 16-17: Architecture & Data Governance (AaC-inspired)

| Step | Change | Description |
|------|--------|-------------|
| 16. Conformance Checking | YAML-defined architecture + data governance rules | 10 rules across structural/quality/completeness/data-governance categories. Validates: layer violations, orphan entities, minimum connections, fan-in thresholds, layer coverage |
| 17. Impact Analysis | BFS blast radius with confidence decay | EXTRACTED=1.0, INFERRED=0.5, AMBIGUOUS=0.0 (blocks). Traces impact across all 11 relationship types, both directions. Returns: layer summary, confidence-weighted radius, hop-by-hop results |

### E2E Test Results (Production, 2026-04-12)

| Endpoint | Status | Key Result |
|----------|--------|------------|
| `/graph/stats` | OK | 1166 entities, 1732 edges, 16 docs |
| `/graph/god-nodes` | OK | Top: Salesforce CRM (29), ArchiSurance B.V. (26) |
| `/graph/conformance` | OK | 10 rules: 3 passed, 5 warnings, 1 error |
| `/graph/impact/{type}/{name}` | OK | Apache Kafka: 107 entities impacted across 4 layers |
| `/graph/brief` | OK | Full brief with conformance report section |
| `/graph/entity/{type}/{name}` | OK | Correct lookup with layer info |
| `/graph/connections/{id}` | OK | All connections with confidence labels |
| MCP (8 tools) | OK | All tools tested against Cloud Run backend |

### Conformance Report Highlights (ArchiSurance)

| Rule | Status | Violations | Insight |
|------|--------|------------|---------|
| ARCH-001 | WARNING | 53 | Many extracted AppComponents lack Serving edges (extraction too generic) |
| ARCH-002 | ERROR | 7 | Layer violations: SystemSoftware serving BusinessProcess directly |
| ARCH-003 | WARNING | 171 | Most BusinessProcesses unreachable from applications |
| QUAL-001 | WARNING | 31 | Orphan entities — candidates for cleanup |
| COMP-002 | PASS | 0 | All 4 ArchiMate layers represented |
| DG-001 | WARNING | 1 | 1 high fan-in DataObject needing documentation |
