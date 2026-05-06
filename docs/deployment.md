# Deployment guide

KnowledgeForge runs on **Google Cloud Run** with **Cloud Spanner** as the graph + vector store. This guide assumes you have a GCP project, a Spanner instance, and the `gcloud` CLI authenticated.

## 1. Provision the Spanner schema

```bash
gcloud spanner databases create "$SPANNER_DATABASE" \
  --instance="$SPANNER_INSTANCE" \
  --ddl-file=database/spanner_schema.sdl

# (Optional) Multi-tenancy migration
gcloud spanner databases ddl update "$SPANNER_DATABASE" \
  --instance="$SPANNER_INSTANCE" \
  --ddl-file=database/add_tenant_id.ddl
```

## 2. Configure environment

Required env vars (used by both deploy scripts and the running services):

| Variable | Description |
|---|---|
| `PROJECT_ID` | GCP project that hosts Cloud Run services |
| `SPANNER_PROJECT` | GCP project that hosts the Spanner instance (often same as `PROJECT_ID`) |
| `SPANNER_INSTANCE` | Spanner instance ID |
| `SPANNER_DATABASE` | Spanner database ID |
| `REGION` | Cloud Run region (default `europe-west1`) |

Optional:

| Variable | Description |
|---|---|
| `DOCLING_URL` | URL of the Docling parser Cloud Run service |
| `LITEPARSE_URL` | URL of the LiteParse PDF parser Cloud Run service |
| `ENABLE_MODEL_ARMOR` | Set `true` to enable Vertex AI Model Armor guardrails |
| `MODEL_ARMOR_TEMPLATE_ID` | Full resource name of your Model Armor template |
| `DEMO_MODE` | `true` wires the stack to the local Spanner emulator and skips IAP / Model Armor. Set automatically by `docker-compose.demo.yml`. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` uses Vertex AI for Gemini calls (production). `false` uses the public `GEMINI_API_KEY` endpoint (demo mode). |
| `GEMINI_API_KEY` | Public Gemini API key — required in demo mode (`GOOGLE_GENAI_USE_VERTEXAI=false`). Loaded from `kb-agent/.env` via the compose `env_file` directive. |
| `KC_TOOLBOX_ENABLED` | `true` registers the Dataplex Knowledge Catalog MCP toolbox. Requires `DATAPLEX_PROJECT`. |
| `BQ_TOOLBOX_ENABLED` | `true` registers the BigQuery MCP toolbox. Requires `BIGQUERY_PROJECT` + `BIGQUERY_LOCATION`. |
| `KC_SYNC_ENABLED` | `true` enables `services/kc_exporter.py` (KF → KC). Requires `KC_ENTRY_GROUP_ID`, `KC_LOCATION`, `DATAPLEX_PROJECT`. |
| `KC_IMPORT_ENABLED` | `true` enables `services/kc_importer.py` (KC → KF). Requires `KC_IMPORT_SUBSCRIPTION` + `DATAPLEX_PROJECT`. |
| `KC_GLOSSARY_ID` | Glossary identifier for the bidirectional `BusinessObject` ↔ KC term bridge (`services/glossary_sync.py`). |
| `NEXT_PUBLIC_FIREBASE_*` | Frontend-only. When set, the frontend renders Google sign-in and propagates the email as `X-Tenant-Id`. Unset = single-tenant `demo@local`. See [`multi-tenancy.md`](multi-tenancy.md). |

## 3. Deploy

```bash
export PROJECT_ID=your-gcp-project
export SPANNER_PROJECT=your-gcp-project
export SPANNER_INSTANCE=your-spanner-instance
export SPANNER_DATABASE=your-spanner-database

./deploy_kb.sh        # backend (kb-agent) + frontend (kb-frontend)
# or
./deploy_run.sh       # equivalent
```

Each script:
1. Builds and deploys `kb-agent` to Cloud Run with the env vars above.
2. Captures the generated backend URL.
3. Builds and deploys `kb-frontend` with `BACKEND_URL` injected.

## 4. (Optional) Deploy the LiteParse PDF service

```bash
gcloud builds submit liteparse-service/ \
  --config=liteparse-service/cloudbuild.yaml \
  --substitutions=_IMAGE=europe-west1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/liteparse
```

Then set `LITEPARSE_URL` in the frontend env to the resulting Cloud Run URL.

## 5. (Optional) Identity-Aware Proxy

For production, restrict frontend access via IAP:

```bash
gcloud iap web add-iam-policy-binding \
  --resource-type=backend-services --service=kb-frontend \
  --member="user:you@example.com" \
  --role="roles/iap.httpsResourceAccessor"
```

## 6. Verify

```bash
curl "$BACKEND_URL/graph/stats"
curl "$BACKEND_URL/graph/brief"
```

Open the frontend URL in a browser, upload a sample document, and run a query.

## Troubleshooting

- **`GOOGLE_CLOUD_PROJECT env var is required`** — the backend now fails fast if env vars are missing. Set them via `--set-env-vars` or `.env`.
- **Vertex AI 404 on embeddings** — `gemini-embedding-2-preview` is currently available only in select regions; the code uses `us-central1` for embeddings regardless of `REGION`.
- **Spanner permission errors** — ensure the Cloud Run service account has `roles/spanner.databaseUser` on the target database.

## Local development with the demo stack

For laptop development you can skip Cloud Run entirely and run everything against the local Spanner emulator with `docker-compose.demo.yml`:

```bash
# 1. Put your Gemini API key in kb-agent/.env (env_file is auto-loaded by compose)
echo "GEMINI_API_KEY=YOUR_KEY"             >> kb-agent/.env
echo "GOOGLE_GENAI_USE_VERTEXAI=false"     >> kb-agent/.env
echo "DEMO_MODE=true"                      >> kb-agent/.env

# 2. Boot the stack (Spanner emulator + kb-agent + kb-frontend + liteparse mock)
docker compose -f docker-compose.demo.yml up -d

# 3. Apply schema + tenant DDL + ingest the demo repo
./demo/scripts/seed.sh

# 4. Open the UI
open http://localhost:13000        # frontend
open http://localhost:18080/docs   # backend OpenAPI
```

Compose ports default to **18080** (backend) and **13000** (frontend) to avoid collisions with anything already bound on the host. See [`docs/quickstart-demo.md`](quickstart-demo.md) for a step-by-step walkthrough and [`demo/README.md`](../demo/README.md) for the full demo kit.

## Optional: Google Data Agent Kit toolboxes

KnowledgeForge can optionally expose two prebuilt MCP toolboxes from Google's
[data-agent-kit-starter-pack](https://github.com/google/data-agent-kit-starter-pack)
to the Coordinator agent: a **Knowledge Catalog** toolbox (Dataplex metadata)
and a **BigQuery** toolbox (live SQL execution). Both default to **OFF**.

### Prerequisites

- **Node.js** with `npx` available on `PATH` in the runtime environment
  (Cloud Run base images do not ship Node — use a custom container that
  installs `nodejs` if you enable these). KF spawns the prebuilt MCP server
  via `npx -y @toolbox-sdk/server@>=1.1.0 --prebuilt <name> --stdio`.
- The first invocation downloads the package via `npx`, adding cold-start
  latency. Pre-baking `node_modules` into the image is recommended for prod.
- Cloning the data-agent-kit-starter-pack repo is **not required** for the
  prebuilt mode — `npx` fetches the package on demand. The repo is a useful
  reference for custom toolboxes.

### Environment variables

| Variable               | Default | Effect                                                   |
|------------------------|---------|----------------------------------------------------------|
| `KC_TOOLBOX_ENABLED`   | `false` | Enable the Dataplex Knowledge Catalog MCP (`kc_*` tools) |
| `BQ_TOOLBOX_ENABLED`   | `false` | Enable the BigQuery MCP (`bq_*` tools)                   |
| `DATAPLEX_PROJECT`     | —       | **Required** when `KC_TOOLBOX_ENABLED=true`              |
| `BIGQUERY_PROJECT`     | —       | **Required** when `BQ_TOOLBOX_ENABLED=true`              |
| `BIGQUERY_LOCATION`    | —       | **Required** when `BQ_TOOLBOX_ENABLED=true`              |

If a toolbox is enabled but its required vars are missing, the Coordinator
fails fast at startup with a clear `RuntimeError`.

### Tool routing

The Coordinator's system prompt teaches it to:

- Prefer `tool_query_spanner_graph` for architecture / conceptual questions
  (this is the indexed-document path).
- Use `kc_*` for live cloud asset metadata (tables, datasets, glossary, lineage).
- Use `bq_*` to run SQL against live BigQuery data when actual numbers are needed.
