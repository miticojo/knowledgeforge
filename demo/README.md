# KnowledgeForge Demo Kit

Everything needed to run a 30-minute live demo of KnowledgeForge against a
realistic mixed corpus of architecture documents and microservice source code.

## What's in this kit

```
demo/
├── README.md                          ← you are here
├── PITCH.md                           ← ~2000-word client narrative
├── gold-set.json                      ← 20 Q&A entries for evaluation
├── datasets/
│   ├── pdfs.txt                       ← TSV manifest of dataset URLs + licenses
│   ├── fetch_pdfs.sh                  ← idempotent downloader (curl + sha256)
│   ├── repos.txt                      ← TSV of repos to clone (with pinned SHAs)
│   ├── LICENSES.md                    ← attribution + license per dataset file
│   └── pdfs/                          ← (created by fetch_pdfs.sh)
└── scenarios/
    ├── 1-system-discovery.md          ← "Capisci un sistema sconosciuto in 5 minuti"
    ├── 2-impact-analysis.md           ← "Cosa si rompe se decommissioni X?"
    ├── 3-doc-to-catalog.md            ← "Da PDF a Knowledge Catalog Entry"
    └── screenshots/                   ← (PNGs, currently placeholder names)
```

## Prerequisites

Two supported modes:

**Offline mode** (recommended for first-time presenters):
- Docker 24+ and Docker Compose v2
- ~8 GB free disk for Spanner emulator + cached PDFs
- No GCP project required

**Full mode** (required for Scenario 3 Part B and any Knowledge Catalog sync):
- A GCP project with **Cloud Spanner**, **Vertex AI**, and (optionally) **Dataplex** enabled
- `gcloud auth application-default login`
- ~$5/day estimated billing during demo prep

## How to run

The end-to-end seed script lives in `demo/scripts/seed.sh` (delivered by Task 4
of the demo workstream and not yet present in this content-only kit).

```bash
# 1. Fetch external dataset files
bash demo/datasets/fetch_pdfs.sh

# 2. Run the seed (creates DB, ingests PDFs + repos, builds graph)
bash demo/scripts/seed.sh                 # uses defaults
bash demo/scripts/seed.sh --offline       # use Spanner emulator
bash demo/scripts/seed.sh --dataset microservices-demo

# 3. Open the frontend
open http://localhost:3000

# 4. Walk through the scenarios in order
$EDITOR demo/scenarios/1-system-discovery.md
```

## Running the gold-set evaluation

```bash
# Once the corpus is loaded, run the eval harness against the gold set:
python evaluation/run_eval.py --gold demo/gold-set.json
# Results written to evaluation/results/eval_<timestamp>.json
```

The schema of `gold-set.json` extends `evaluation/data/ground_truth/eval_questions_v2.json`
with two demo-specific fields (`expected_answer_keywords`, `expected_documents`)
plus a `scenario` tag so you can slice results per scenario.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `fetch_pdfs.sh` fails on one URL | upstream HTML page moved | update `pdfs.txt` and re-run; the script is idempotent |
| Frontend shows empty graph | seed didn't finish or wrong Spanner instance | check backend logs, confirm `SPANNER_INSTANCE` matches what seed populated |
| `/catalog/sync` returns 404 | `KC_SYNC_ENABLED` not set or backend not restarted | `export KC_SYNC_ENABLED=true` then restart `kb-agent` |
| Verification labels everything UNSUPPORTED | embedding mismatch (e.g. wrong model id) | confirm `EMBEDDING_MODEL` env var matches what was used at ingest time |
| Port 3000 / 8080 in use | local dev server already running | stop the other process or override `PORT` in `.env.local` / `.env` |
| `seed.sh: command not found` | script lives in Task 4 deliverable, not in this content-only kit | use the manual ingestion flow described in repo `README.md` Quickstart |

## License & attribution

All third-party content is enumerated with license + attribution in
[`datasets/LICENSES.md`](datasets/LICENSES.md). Apache-2.0 obligations
(NOTICE preservation, copyright preservation) are documented per source.

## Reporting issues

Open an issue at the KnowledgeForge GitHub repo and tag it `demo`.

---

## Infrastructure (offline demo stack)

The demo runs entirely on `docker-compose` with the **Cloud Spanner emulator** —
no GCP project, no credentials, no network egress required.

### Quick start

```bash
# 1. Boot the stack (Spanner emulator + kb-agent + kb-frontend + liteparse mock)
docker compose -f docker-compose.demo.yml up -d

# 2. Initialize the emulator + ingest the demo repos (~5–10 min depending on machine)
./demo/scripts/seed.sh

# 3. Run the 10-query demo script for the presenter
./demo/scripts/queries.sh

# 4. When done — tear down and wipe state
./demo/scripts/teardown.sh
```

UI: http://localhost:3000  ·  API: http://localhost:8080  ·  Emulator gRPC: localhost:9010

### Prerequisites

- Docker (with `docker compose` v2 plugin)
- `jq` and `curl`
- Optional: `GEMINI_API_KEY` exported on the host — enables full LLM-backed
  answers via the public Gemini endpoint. Without it, the agent still serves
  graph queries (stats, brief, impact, connections) but chat responses are
  degraded.

### Environment variables (set automatically by compose)

| Variable                  | Value                       | Purpose                        |
| ------------------------- | --------------------------- | ------------------------------ |
| `DEMO_MODE`               | `true`                      | Enables emulator + skips Model Armor |
| `SPANNER_EMULATOR_HOST`   | `spanner-emulator:9010`     | Routes Spanner client to emulator |
| `GOOGLE_CLOUD_PROJECT`    | `demo-project`              | Project ID inside emulator     |
| `SPANNER_INSTANCE`        | `demo-instance`             | Instance ID inside emulator    |
| `SPANNER_DATABASE`        | `demo-db`                   | Database ID inside emulator    |
| `GEMINI_API_KEY`          | from host (optional)        | Enables real LLM responses     |

### Known-good lessons (from end-to-end smoke runs)

The demo is verified with **`pallets/itsdangerous`** as the seed repo. A clean
run produces approximately:

- **~32 chunks** ingested into `DocumentChunks`.
- **~80+ entities** across the ArchiMate layers (mostly `ApplicationComponent`,
  `DataObject`, `BusinessProcess`).
- **Non-empty `/graph/stats`** and a non-trivial `/graph/god-nodes` response.

If your numbers are dramatically lower, scroll the troubleshooting table for
the most common culprit (missing API key, Vertex AI mode in DEMO_MODE, etc.).

The recommended runtime configuration for DEMO_MODE:

```bash
# kb-agent/.env (loaded automatically via env_file in docker-compose.demo.yml)
DEMO_MODE=true
GEMINI_API_KEY=ya29...                   # public Gemini endpoint
GOOGLE_GENAI_USE_VERTEXAI=false          # MUST be false in DEMO_MODE
```

In the **chat** tab a "Scope" toggle in the banner restricts retrieval to a
single entity (sets the `X-Entity-Scope` header). Use it to demo focused
question answering without re-ingesting; toggle off to fall back to the full
graph search. See [`docs/concepts/graph-navigation.md`](../docs/concepts/graph-navigation.md).

### Troubleshooting

| Symptom                                          | Likely cause / fix                                                                 |
| ------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `GEMINI_API_KEY not set` / per-file `writer error: No API key was provided` | Add `GEMINI_API_KEY=...` to `kb-agent/.env` (gitignored). Compose's `env_file: kb-agent/.env` directive auto-propagates it to the agent — **no need to `export` it on the host**. Re-run `docker compose -f docker-compose.demo.yml up -d` to pick up the change. |
| Chat returns `Vertex AI 404` or `permission denied` in DEMO_MODE | `GOOGLE_GENAI_USE_VERTEXAI=true` is leaking into the demo container. Ensure `kb-agent/.env` contains `GOOGLE_GENAI_USE_VERTEXAI=false`; the demo path uses the public Gemini endpoint, not Vertex AI. |
| `bind: address already in use` for 8080/3000/9010 | Another local service is using the port. Stop it or edit `docker-compose.demo.yml`. The compose file maps host ports **18080** (backend) and **13000** (frontend) by default; the asciinema recorder uses 8090/3010/9110. |
| `init_emulator.py` fails with `instance not found` | Emulator wasn't fully up — wait 5s and re-run `./demo/scripts/seed.sh`.            |
| DDL apply errors mentioning `MODEL`              | Expected — `CREATE MODEL` (Vertex AI) is filtered out for the emulator automatically. |
| `/ingest/git` job stuck in `running`              | Increase per-job timeout in `seed.sh` (default 10 min) or check `docker logs kf-kb-agent`. |
| Empty `/graph/stats`                              | Re-run `./demo/scripts/seed.sh` — it's idempotent and will resume.                |
| PDF upload errors                                 | Expected — `liteparse-mock` only echoes; PDF parsing is intentionally degraded in DEMO_MODE. |
| `/ingest/git` job fails: `Bad git executable. The git executable must be specified...` | The `kb-agent` Docker image (`python:3.12-slim`) does **not** install `git`, but the ingestion path uses `GitPython` which shells out to `git clone`. **Fix:** add `git` to the system packages in `kb-agent/Dockerfile` (`apt-get install -y git`) and rebuild. As a one-off workaround for an already-running container: `docker exec -u root kf-kb-agent apt-get update && apt-get install -y git && docker restart kf-kb-agent`. |
| `/ingest/git` job fails: `Remote branch <sha> not found in upstream origin` | The `ref` field is passed straight to `git clone --depth=1 --branch=<ref>`, which only accepts branch/tag names — **not commit SHAs**. The pinned SHAs in `demo/datasets/repos.txt` therefore fail. **Workaround:** use a branch name (e.g. `main`). **Proper fix:** in the agent's git ingest code, do `git clone` then `git checkout <sha>` (or `git fetch <sha>` if the host supports `uploadpack.allowReachableSHA1InWant`). |
| `/ingest/git` completes with `summary.entities_total: 0` and per-file `writer error: No API key was provided` | Entity extraction in DEMO_MODE relies on the public Gemini endpoint and requires `GEMINI_API_KEY` exported on the host before `docker compose up`. Without it, the graph stays empty even after a successful clone+walk, and downstream queries (`/graph/god-nodes`, `/graph/impact/...`) return empty or 500. |
| `spanner-emulator` shown as `unhealthy` in `docker ps` but logs say `gRPC server listening at 0.0.0.0:9010` | The compose healthcheck uses `nc`, which is not present in the distroless `gcr.io/cloud-spanner-emulator/emulator` image, so it always reports `unhealthy` even when the emulator is fine. This blocks `kb-agent` from starting because of `depends_on.condition: service_healthy`. **Fix:** change the healthcheck to `["CMD", "/emulator_main", "--help"]` or use a TCP probe from outside the container; or replace `condition: service_healthy` with `condition: service_started`. |
| `/copilotkit` queries 4 and 8 in `queries.sh` return HTTP 422 with `Field required: threadId, runId, state, tools, context, forwardedProps` | The shell helper `ck()` in `demo/scripts/queries.sh` posts a minimal `{messages:[...]}` body, but the `/copilotkit` FastAPI route expects the full CopilotKit runtime envelope. **Fix:** either point `ck()` at a simpler chat endpoint, or build the full payload (threadId, runId, empty state/tools/context/forwardedProps). |
| `/graph/conformance` rules return SQL error `Unrecognized name: tenant_id`; `/graph/impact/...` and `/tenant/stats` return 500 | Several SQL queries in the conformance and impact code paths reference `tenant_id` against tables/columns that don't expose it (interleaved schema). Rule rows show `violation_count: -1` and `status: error` instead of real results. Needs a backend fix (qualify `tenant_id` against the correct table or remove the predicate where the schema is shared). |

### Recording

A pre-rendered asciinema walkthrough lives in `demo/recording/`:

- `walkthrough.cast` — full-fidelity terminal capture (~60 KB, ~40 s).
  Open it locally with `asciinema play demo/recording/walkthrough.cast`.
- `walkthrough.svg` — static SVG playback embedded in the top-level
  [`README.md`](../README.md). Renders inline on GitHub.

#### Re-recording

```bash
bash demo/scripts/record.sh
```

The script:

1. Validates `asciinema`, `svg-term`, and Docker are installed.
2. Sources `kb-agent/.env` (so `GEMINI_API_KEY` is available to the agent).
   The key is **never echoed**, copied into the cast, or committed.
3. Boots `docker-compose.demo.yml` with a generated port-override file
   (`demo/recording/.compose.override.yml`, gitignored) that maps the
   agent / frontend / spanner ports to `8090 / 3010 / 9110` to avoid
   collisions with anything already bound on the host. Override via
   `HOST_AGENT_PORT`, `HOST_FRONTEND_PORT`, `HOST_SPANNER_PORT` env vars.
4. Backs up `demo/datasets/repos.txt` and swaps in a single-repo manifest
   (`pallets/itsdangerous`, recent SHA) so the recording stays under a
   minute. The original file is restored on exit.
5. Records `seed.sh` + `queries.sh` via `asciinema rec`.
6. Downgrades the cast from v3 (default in `asciinema` 3.x) to v2
   in-place, since `svg-term-cli` only reads v1/v2.
7. Renders to SVG (window chrome, no cursor, 100×28).
8. Tears the stack down (`docker compose down -v`) and restores
   `repos.txt` regardless of success or failure (via `trap`).

If anything fails (Docker not running, asciinema crash, svg-term
parse error), a placeholder SVG (`<text>Demo recording pending</text>`)
is written so the README link does not break.

#### Recording troubleshooting

| Symptom | Fix |
| --- | --- |
| `bind: address already in use` on 8080/3000/9010 | The script uses 8090/3010/9110 by default. Override further with `HOST_AGENT_PORT=... bash demo/scripts/record.sh`. |
| `svg-term`: `only asciicast v1 and v2 formats can be opened` | The script downgrades v3 to v2 automatically. If you re-ran a partial flow, delete `demo/recording/walkthrough.cast` and re-run. |
| SVG > 500 KB | Reduce `--width`/`--height` in step 6 of `record.sh`, or shorten the recorded command. |
| `GEMINI_API_KEY not set` | Add `GEMINI_API_KEY=...` to `kb-agent/.env` (gitignored). |
| `init_emulator` creates `your-spanner-instance` instead of `demo-instance` | `kb-agent/.env` ships with placeholder `SPANNER_*` values for production GCP. The recorder forces `GOOGLE_CLOUD_PROJECT=demo-project`, `SPANNER_PROJECT=demo-project`, `SPANNER_INSTANCE=demo-instance`, `SPANNER_DATABASE=demo-db` after sourcing `.env` to match the in-container compose env. |
| Recording shows `total_entities: 0` after a "complete" git ingest | Known backend bug: `Documents.doc_id STRING(36)` is too narrow to hold the synthesized git ingest doc IDs (`git:<repo_url>@<sha>:<file_path>`, typically 100–130 chars). Every batch write fails with `New value exceeds the maximum size limit for this column: Documents.doc_id`. Job is reported `complete` but `entities_discovered=0`. Fix is in the agent (hash the doc_id, or widen the column to `STRING(MAX)`); not a recorder issue. |

### What's NOT included in DEMO_MODE

- **Model Armor** safety filtering (production-only)
- **Vertex AI** embeddings / Gemini via `CREATE MODEL` (use `GEMINI_API_KEY` instead)
- **liteparse** real PDF chunking (replaced by an nginx echo container)
- **Production Spanner** (replaced by the emulator — no persistence across `down -v`)
