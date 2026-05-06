# ArchiSurance Claims Processing — Technology Architecture

## Nodes

- **GKE cluster `claims-prod`** — regional Kubernetes cluster in
  `europe-west1` hosting all application components.
- **CloudSQL Postgres `claims-db`** — primary OLTP store (instance
  `claims-db-pg16`).
- **BigQuery dataset `claims_warehouse`** — analytics store, populated
  by the dbt project `claims_analytics`.

## System Software

- **PostgreSQL 16** — DBMS for ClaimsDB and PolicyDB.
- **Apache Airflow 2.x** — orchestrates nightly dbt runs and exports
  from CloudSQL to BigQuery.
- **dbt 1.7** — transformation framework; project lives at
  `demo/datasets/archisurance/dbt/`.

## Technology Services

- **Cloud Pub/Sub** — message bus carrying `ClaimEvent` messages on the
  `claims.events` topic.
- **Cloud Storage `claims-attachments`** — bucket for uploaded photos
  referenced by `damage_reports.photos_uri`.
- **Cloud Spanner (graph)** — knowledge graph backing KnowledgeForge.
- **Vertex AI** — hosts the FraudScorer model artefact.

## Artifacts

- **`claims-api` Docker image** — built from `code/claims_api/`,
  published to `europe-west1-docker.pkg.dev/archisurance/claims/api`.
- **`claims-worker` Docker image** — built from `code/claims_worker/`.
- **`fraud-scorer` Docker image** — built from `code/fraud_scorer/`.
- **dbt project `claims_analytics`** — source artefact for the
  warehouse build.

## Deployment Topology

GKE workloads connect to CloudSQL via the Cloud SQL Auth Proxy
sidecar. Pub/Sub access uses Workload Identity binding the
`claims-prod` Kubernetes service account to a GCP service account with
publish/subscribe rights on `claims.events`. The dbt runner pod reads
from CloudSQL through a federated Postgres external table in BigQuery,
so no nightly dump is required.
