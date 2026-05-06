locals {
  base_apis = [
    "spanner.googleapis.com",
    "aiplatform.googleapis.com",
    "generativelanguage.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
    "pubsub.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
  ]

  # Opt-in: Knowledge Catalog / Dataplex (kb-agent KC_SYNC_ENABLED path)
  kc_apis = var.enable_dataplex_kc ? ["dataplex.googleapis.com"] : []

  enabled_apis = toset(concat(local.base_apis, local.kc_apis))
}

resource "google_project_service" "apis" {
  for_each = local.enabled_apis

  service = each.value
  project = var.project_id

  disable_on_destroy = false
}
