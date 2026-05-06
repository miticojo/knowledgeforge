# Scenario 3 — Da PDF a Knowledge Catalog Entry

**Audience**: data governance lead, enterprise architect.
**Goal**: show how an unstructured PDF becomes a structured, queryable, governance-ready entry — first locally in KnowledgeForge, then optionally synced to Google Cloud Knowledge Catalog (Dataplex).
**Dataset**: ArchiSurance `doc_05_claims_processing.pdf` (already in repo).

## Part A — Local ingestion (always works, no GCP needed for the demo)

### Setup

```bash
# Backend + frontend running locally (Spanner emulator OK for offline mode)
bash demo/scripts/seed.sh --offline
```

### Step 1 — Upload

In the frontend (`http://localhost:3000`), drag `evaluation/data/archisurance/doc_05_claims_processing.pdf` onto the upload zone.

- **Expected behavior**: parse progress bar (LiteParse extracts text + figures), then chunk progress, then graph extraction.
- **Talking point**: one document → ~30-60 chunks → ~15-30 ArchiMate entities → ~25-50 typed relationships.
- **Screenshot**: `screenshots/3-step-1-upload.png`

### Step 2 — Inspect the extracted graph

Open the architecture view filtered to the new document.

- **Expected nodes**: `ClaimsProcess` (BusinessProcess), `Adjuster` (BusinessRole), `ClaimRecord` (DataObject), `Claims Management Platform` (ApplicationComponent), `PostgreSQL 15` (TechnologyService), etc.
- **Expected edges**: typed (`assigned_to`, `accesses`, `realizes`) with confidence labels.
- **Talking point**: every node and edge has a back-pointer to the source PDF chunk + page. Auditable provenance.
- **Screenshot**: `screenshots/3-step-2-graph.png`

### Step 3 — Ask a governance question

> "List the data objects produced by the claims process and their owners."

- **Expected behavior**: graph traversal from `ClaimsProcess` along `produces` edges, joined with `owned_by` to surface accountable roles.
- **Talking point**: this is exactly the metadata a Knowledge Catalog entry needs.
- **Screenshot**: `screenshots/3-step-3-answer.png`

## Part B — Optional: sync to Google Cloud Knowledge Catalog

> :warning: **This part requires a GCP project with Dataplex Universal Catalog enabled and `gcloud auth application-default login`. Skip it if you are running the offline demo.** All KnowledgeForge functionality except the export works without GCP.

### Enable the export path

```bash
export KC_SYNC_ENABLED=true
export GOOGLE_CLOUD_PROJECT=your-project
export DATAPLEX_LOCATION=europe-west1
export DATAPLEX_ENTRY_GROUP=knowledgeforge-demo
gcloud auth application-default login
```

Restart the backend so it picks up the env vars.

### Step 4 — Push entities to Dataplex

```bash
curl -s -X POST "http://localhost:8080/catalog/sync" \
  -H 'content-type: application/json' \
  -d '{"document_id": "doc_05_claims_processing", "dry_run": false}' | jq
```

- **Expected behavior**: each ArchiMate entity becomes a Dataplex *Entry*; relationships are encoded as Aspects on the entry.
- **Talking point**: now your enterprise data catalog has a row for `ClaimRecord` that previously existed only as a sentence in a PDF.
- **Screenshot**: `screenshots/3-step-4-dataplex.png`

### Step 5 — Verify in the GCP console

Open Dataplex → Catalog → Entry Group `knowledgeforge-demo`. Search for `ClaimRecord`. The entry shows a link back to the source PDF and the KnowledgeForge graph URL.

- **Talking point**: closes the loop between unstructured docs and the corporate data catalog.
- **Screenshot**: `screenshots/3-step-5-gcp-console.png`

## What if I don't have GCP?

- Stop after Part A — the demo is still complete and shows the agentic ingestion pipeline.
- The `KC_SYNC_ENABLED=false` (default) path silently disables the `/catalog/sync` endpoint; the rest of the system is unchanged.
