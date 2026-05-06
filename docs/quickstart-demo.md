# Quickstart: KnowledgeForge demo in 15 minutes

Goal: take a clean clone of this repository to a working KnowledgeForge
demo (graph + chat + dashboard) running entirely on your laptop, in under
fifteen minutes. No GCP project, no production credentials.

## Prerequisites

- Docker 24+ with the `docker compose` v2 plugin
- `git`, `curl`, `jq`
- A **public Gemini API key** (free tier is fine) — get one at
  <https://aistudio.google.com/apikey>

## 1. Clone

```bash
git clone https://github.com/<you>/knowledgeforge.git
cd knowledgeforge
```

## 2. Configure `kb-agent/.env`

`docker-compose.demo.yml` declares `env_file: kb-agent/.env`, so any
variable you put in that file is propagated to the agent container
automatically — you do **not** need to `export` anything on the host.

```bash
cat >> kb-agent/.env <<'EOF'
DEMO_MODE=true
GOOGLE_GENAI_USE_VERTEXAI=false
GEMINI_API_KEY=YOUR_KEY_HERE
EOF
```

`.env` is gitignored, so the key never lands in a commit.

## 3. Boot the stack

```bash
docker compose -f docker-compose.demo.yml up -d
```

This starts four containers:

- `kf-spanner-emulator` — local Cloud Spanner emulator (gRPC on `9010`)
- `kf-kb-agent` — FastAPI backend (host port `18080`)
- `kf-kb-frontend` — Next.js frontend (host port `13000`)
- `kf-liteparse-mock` — nginx echo for PDF parsing in DEMO_MODE

`docker compose ps` should show all four healthy within ~30 s. (The
Spanner emulator may report `unhealthy` in some Docker versions because
its image lacks `nc`; ignore that — the agent's own readiness check is
the source of truth.)

## 4. Initialize the emulator + ingest the demo repo

```bash
./demo/scripts/seed.sh
```

The script:

1. Applies `database/spanner_schema.sdl` and the tenant DDL
   (`database/add_tenant_id.ddl`) to the emulator. Idempotent.
2. Submits `pallets/itsdangerous` (a small, public Python repo) to
   `POST /ingest/git` and polls the job until it completes.
3. Prints the final `/graph/stats` so you can verify the graph is
   populated.

Expected outcome: **~32 chunks** and **~80+ entities** discovered. If
you see `entities_discovered: 0`, the `GEMINI_API_KEY` did not propagate
— double-check `kb-agent/.env`.

## 5. Query the chat

Open **<http://localhost:13000>** and click into the **Chat** tab. Try:

- *"What is itsdangerous and what does it do?"*
- *"Which application components depend on the Signer class?"*
- *"What data objects does the Serializer use?"*

The right-hand panel streams the coordinator's pipeline (query expansion,
hybrid retrieval, RRF fusion, reranking, synthesis) live via AG-UI SSE,
and the answer cites its sources in a collapsible `<sources>` block.

To restrict retrieval to a single entity, use the **Scope** banner above
the chat box: it sets the `X-Entity-Scope` header, and only chunks that
mention the scoped entity feed into the answer. Dismiss the banner to
return to full graph search. See [`docs/concepts/graph-navigation.md`](concepts/graph-navigation.md).

## 6. Explore the graph

Open **<http://localhost:13000/graph>**. The standalone graph page lets
you:

- Toggle ArchiMate layers (Strategy / Business / Application / Technology / Motivation)
- Filter by entity type or by hubs / orphans
- Search for an entity by name and pin it as the focus
- Re-root the canvas on a clicked node's 1-hop or 2-hop neighbourhood

## 7. Inspect cost + tenant dashboard

Open **<http://localhost:13000/dashboard>** to see the per-tenant cost
dashboard (top tenants, daily trend, breakdown by ingestion vs query).
In single-tenant DEMO_MODE the dashboard shows `demo@local`'s usage.

## 8. Tear down

```bash
docker compose -f docker-compose.demo.yml down -v
```

The `-v` flag deletes the emulator volume so the next `up -d` starts
clean. The `seed.sh` script is idempotent and safe to re-run on a fresh
emulator.

## Where to go next

- [`demo/README.md`](../demo/README.md) — full demo kit, scenarios, gold-set evaluation
- [`docs/concepts/rag-primer.md`](concepts/rag-primer.md) — RAG / GraphRAG / AgenticRAG primer
- [`docs/concepts/graph-navigation.md`](concepts/graph-navigation.md) — the `/graph` page and entity-scope chat filter
- [`docs/concepts/knowledge-catalog-bridge.md`](concepts/knowledge-catalog-bridge.md) — Knowledge Catalog roundtrip (B + C + D)
- [`docs/deployment.md`](deployment.md) — Cloud Run deployment for production
- [`docs/multi-tenancy.md`](multi-tenancy.md) — tenant model, search scopes, Firebase auth
