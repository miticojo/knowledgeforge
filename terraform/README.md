# KnowledgeForge — Terraform

Provisions the Google Cloud footprint required to run KnowledgeForge in
production: Cloud Run services (`kb-agent`, `kb-frontend`, `liteparse`),
Spanner, GCS + Pub/Sub for document ingestion, IAM, Secret Manager, and
Artifact Registry.

## What gets created

| File | Resource |
| --- | --- |
| `apis.tf` | Required Google APIs (Spanner, Run, Vertex, GenLang, Storage, PubSub, Secret Manager, IAM, Artifact Registry, Cloud Build; optional Dataplex) |
| `artifact_registry.tf` | Docker repository for kb-agent / kb-frontend / liteparse images |
| `cloudrun.tf` | `kb-agent` service + invoker IAM (public + Pub/Sub + frontend) |
| `frontend.tf` | `kb-frontend` service + SA + invoker IAM |
| `liteparse.tf` | Internal `liteparse` service + SA + invoker IAM |
| `spanner.tf` | Spanner instance + database (DDL applied out-of-band) |
| `secrets.tf` | Secret Manager container for `GEMINI_API_KEY` + accessor IAM |
| `storage_pubsub.tf` | Documents bucket + GCS notification + Pub/Sub topic + push subscription |
| `iam.tf` | `kb-agent-sa` + role bindings (Spanner DB user, Vertex user, bucket reader); Spanner service-agent Vertex binding |
| `provider.tf` | Google + google-beta providers |
| `variables.tf` | Inputs |

## Prerequisites

1. `gcloud` CLI authenticated: `gcloud auth application-default login`.
2. A GCP project with **billing enabled**.
3. Terraform >= 1.5.
4. (Recommended) A GCS bucket for remote state — uncomment the `backend "gcs"`
   block in `provider.tf`.

## First-time bootstrap

```bash
cd terraform

# 1. Set inputs (never check terraform.tfvars into Git if it contains secrets)
cat > terraform.tfvars <<EOF
project_id = "my-real-gcp-project"
region     = "us-central1"
EOF

# 2. Init + plan + apply (apis + IAM first; rerun if Cloud Run errors out
#    on a brand-new project — API enablement can lag a few seconds)
terraform init
terraform apply -target=google_project_service.apis
terraform apply

# 3. Add the Gemini API key (secret CONTAINER is created by Terraform; the
#    VALUE must never live in code/state). Skip if using Vertex-only.
echo -n "YOUR_GEMINI_KEY" | gcloud secrets versions add gemini-api-key \
    --data-file=- --project=my-real-gcp-project

# 4. Apply the Spanner schema + migrations (NOT managed by Terraform)
gcloud spanner databases ddl update kb-db \
    --instance=kb-instance \
    --project=my-real-gcp-project \
    --ddl-file=../database/spanner_schema.sdl

for f in ../database/migrations/*.sql; do
  gcloud spanner databases ddl update kb-db \
      --instance=kb-instance \
      --project=my-real-gcp-project \
      --ddl-file="$f"
done

# 5. Build + push container images (CI/CD or local), then re-apply with the
#    real image refs:
terraform apply \
    -var "kb_agent_image=us-central1-docker.pkg.dev/my-real-gcp-project/knowledgeforge/kb-agent@sha256:..." \
    -var "kb_frontend_image=us-central1-docker.pkg.dev/my-real-gcp-project/knowledgeforge/kb-frontend@sha256:..." \
    -var "liteparse_image=us-central1-docker.pkg.dev/my-real-gcp-project/knowledgeforge/liteparse@sha256:..."
```

## Variables you will likely override

| Variable | Why |
| --- | --- |
| `project_id` | **Required.** Default `your-gcp-project` is intentionally invalid. |
| `region` | Cloud Run + Spanner region (e.g. `europe-west1`). |
| `kb_agent_image` / `kb_frontend_image` / `liteparse_image` | Pin to immutable Artifact Registry digests once CI/CD is wired up. |
| `gemini_api_key_secret_id` | Default `gemini-api-key`. |
| `create_gemini_api_key_secret` | Set `false` if the secret already exists outside this stack. |
| `kb_agent_allow_unauthenticated` / `kb_frontend_allow_unauthenticated` | Flip to `false` to lock the services down to IAM-authenticated callers. |
| `enable_dataplex_kc` | Set `true` if running with `KC_SYNC_ENABLED=true`. |
| `kb_agent_extra_env` | Inject KC_*, MODEL_ARMOR_TEMPLATE_ID, ENABLE_MODEL_ARMOR, etc. |
| `spanner_processing_units` | Default 100 (dev). Use ≥1000 for prod. |

## Service architecture (post-apply)

```
              Internet
                 │
                 ▼
        ┌─────────────────┐
        │   kb-frontend   │  Next.js (Cloud Run, public)
        │   (kb-frontend-sa)│
        └────────┬────────┘
                 │ BACKEND_URL (ID token if auth enabled)
                 ▼
        ┌─────────────────┐         ┌──────────────────┐
        │     kb-agent    │ ──ID──▶ │    liteparse     │ Cloud Run, INTERNAL
        │  (kb-agent-sa)  │ token   │ (liteparse-sa)   │
        └─┬─────┬───────┬─┘         └──────────────────┘
          │     │       │
   Spanner│     │       │GCS read
          ▼     │       ▼
      ┌──────┐  │   ┌─────────────────┐
      │kb-db │  │   │ documents bucket│◀──── upload
      └──────┘  │   └────────┬────────┘
                │            │ OBJECT_FINALIZE
                │            ▼
                │      ┌──────────┐
                │      │ Pub/Sub  │
                │      └────┬─────┘
                │           │ push (OIDC, pubsub-invoker-sa)
                └───────────┘  -> POST /ingest
       Vertex AI (Gemini, embeddings, ranking)  ◀──── kb-agent
       Secret Manager (GEMINI_API_KEY)          ◀──── kb-agent
```

## Disaster recovery / rollback

- **Container rollback**: redeploy the previous image digest; Cloud Run keeps
  revisions and traffic-split is supported via the v2 service resource.
- **Spanner**: enable PITR on the database (not yet wired in TF — add
  `version_retention_period = "7d"` if needed).
- **State**: use a GCS backend with object versioning so a botched
  `terraform apply` can be rewound.

## Tagging / labels

Terraform does **not** currently apply project-wide labels — add a `labels = {
team = "knowledgeforge", env = "prod" }` block to each resource if your org
requires cost-tracking labels. Cloud Run v2 supports `labels` directly under
`template`.
