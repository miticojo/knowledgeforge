# AGENTS.md — instructions for AI coding assistants working on KnowledgeForge

This file is the canonical brief for any AI agent (Codex, Cursor, GitHub Copilot, MCP-compatible IDEs, …) editing this repository. Read it before touching code.

## What this project is

KnowledgeForge is an open-source **AgenticRAG over GraphRAG** platform on Google Cloud. See [`README.md`](README.md) for the architecture overview and [`docs/concepts/rag-primer.md`](docs/concepts/rag-primer.md) for the conceptual primer.

Two services:
- `kb-agent/` — FastAPI + Google ADK backend (Python 3.11+).
- `kb-frontend/` — Next.js 16 + React 19 + CopilotKit frontend.
- `kb-mcp-server/` — stdio MCP server exposing the KB to external AI clients.
- `liteparse-service/` — Cloud Run service for PDF text + image extraction.
- `evaluation/` — retrieval benchmarks (HotpotQA + custom Q&A).
- `database/` — Spanner DDL.
- `terraform/` — IaC for GCP foundation.

## Hard rules

1. **No proprietary identifiers.** Never reintroduce hardcoded GCP project IDs, Spanner instance/database names, or internal Cloud Run URLs. Read from env vars; fail fast if missing.
2. **No AI-vendor attribution in commits.** Author = real maintainer. Never add `Co-Authored-By: Claude`, `Generated with Claude Code`, or similar markers.
3. **ArchiMate 3.2 ontology is canonical.** All entity and relationship types in the knowledge graph must come from `kb-agent/ontology.yaml`. Do not invent generic types like `App`, `Server`, or `DB`.
4. **No silent fallbacks for required config.** If `GOOGLE_CLOUD_PROJECT`, `SPANNER_*`, `DOCLING_URL`, or `LITEPARSE_URL` are missing, raise / exit with a clear message. Never guess.
5. **Do not commit secrets.** `.env*` (except `.env.example`), `*.pem`, `*.key`, `credentials*.json`, `service-account*.json`, `*.log`, `.planning/`, `.agent/` are gitignored. Keep them that way.
6. **Tests live in `kb-agent/tests/` and `kb-frontend/__tests__/`.** Do not create one-off `test_*.py` scripts in the project root.

## Coding conventions

- **Python**: PEP 8, type hints on public APIs, prefer composition over inheritance.
- **TypeScript**: strict mode, project ESLint config, no `any` without justification.
- **Comments**: write only when the *why* is non-obvious. Code should be self-documenting; comments should explain decisions, not actions.
- **Docstrings**: short and factual. No multi-paragraph essays.
- **No dead code, no commented-out blocks, no `console.log` in committed code.**

## Workflow expectations

- **Plan before coding** for non-trivial changes. State intent, list files to touch, then act.
- **Small, atomic commits**. One logical change per commit. Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`).
- **Verify before claiming done**: run the relevant tests, `npm run typecheck`, or hit the running service. Don't conflate "code compiles" with "feature works".
- **Prefer editing existing files** over creating new ones.
- **Frontend changes**: start the dev server, exercise the UI in a browser, then report.

## Ingestion paths

KnowledgeForge has two complementary ingestion paths — pick based on the source:

- **Documents** (PDF / DOCX / PPTX): upload through the **Documents** tab in the frontend or the existing `/ingest` endpoint. Parsing goes through LiteParse (PDFium + sharp for figure extraction). Use this for architecture decks, runbooks, RFCs, vendor manuals.
- **Git repositories** (Python / TypeScript / Java / Go / SQL): submit a Git URL through the **Code Repository** tab or `POST /ingest/git`. The AST ingester extracts ArchiMate entities directly from source (modules → `ApplicationComponent`, services → `ApplicationService`, schema → `DataObject`, etc.). Use this for legacy systems whose only documentation *is* the code.

Both paths land in the same Spanner graph and are queried by the same retrieval pipeline.

Once ingested, the graph is consumable through:

- **`/graph`** — standalone navigable canvas with search, ArchiMate layer filters, hub/orphan filters, click-to-pin selection. Backend endpoints: `GET /graph/neighbors`, `GET /graph/search`. See [`docs/concepts/graph-navigation.md`](docs/concepts/graph-navigation.md).
- **`/dashboard`** — per-tenant cost dashboard backed by `/tenant/dashboard` (top tenants, daily trend, per-op-type breakdown).
- **`/chat`** — coordinator agent with optional **entity scope** banner; toggling it sets the `X-Entity-Scope` header so retrieval is restricted to a single entity's neighborhood.

## Environment toggles

- `DEMO_MODE=true` — laptop dev mode. Wires the stack to the local Spanner emulator from `docker-compose.demo.yml`; skips IAP and Model Armor. Compose loads `kb-agent/.env` via `env_file`, so `GEMINI_API_KEY` declared there is enough — no host `export` needed.
- `GOOGLE_GENAI_USE_VERTEXAI` — `true` (production, Vertex AI) or `false` (demo, public Gemini endpoint with `GEMINI_API_KEY`). Must be `false` in `DEMO_MODE`.
- `GEMINI_API_KEY` — required when `GOOGLE_GENAI_USE_VERTEXAI=false`.
- `KC_TOOLBOX_ENABLED=true` — opt-in: registers Google's **Knowledge Catalog** MCP toolbox as a coordinator tool.
- `BQ_TOOLBOX_ENABLED=true` — opt-in: registers Google's **BigQuery** MCP toolbox as a coordinator tool. KF and the toolboxes are designed to coexist, not replace each other.
- `KC_SYNC_ENABLED=true` — opt-in: enables the Knowledge Catalog **exporter** (`services/kc_exporter.py`) to push curated KF entities into KC as managed tags / linked assets.
- `KC_IMPORT_ENABLED=true` — opt-in: enables the Knowledge Catalog **reverse importer** (`services/kc_importer.py`) to pull KC Entries (BigQuery, Spanner, Cloud SQL, ...) into the KF graph as ArchiMate `DataObject` nodes. Pair with `KC_IMPORT_SUBSCRIPTION` for streaming mode.
- `KC_GLOSSARY_ID` — identifier of the Dataplex glossary used by the bidirectional `BusinessObject` ↔ glossary term sync (`services/glossary_sync.py`).
- `NEXT_PUBLIC_FIREBASE_*` — frontend-only. When set, enables Google sign-in and propagates the email as `X-Tenant-Id`. Unset = single-tenant `demo@local`.
- `ENABLE_MODEL_ARMOR` — see Security section in `README.md`.

## Distribution

KnowledgeForge is installable as a multi-CLI extension. Manifests:

- Gemini CLI → `gemini-extension.json`
- Claude Code → `.claude-plugin/plugin.json`
- Codex → `.codex-plugin/plugin.json`

When changing MCP tool surface area in `kb-mcp-server/`, keep all three manifests in sync.

## When in doubt

- Architecture questions → `README.md`, `docs/concepts/`.
- Deploy questions → `docs/deployment.md`.
- Roadmap → `docs/roadmap.md`.
- Contribution flow → `CONTRIBUTING.md`.

If a request would violate any rule above, push back before acting.
