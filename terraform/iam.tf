# Service Account: kb-agent
resource "google_service_account" "kb_agent_sa" {
  account_id   = "kb-agent-sa"
  display_name = "KB Agent Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

# Spanner read/write at the database level (least-privilege; databaseUser is
# fine for both DML + read against the kb-db database).
resource "google_spanner_database_iam_member" "agent_spanner_user" {
  project  = var.project_id
  instance = google_spanner_instance.kb_instance.name
  database = google_spanner_database.kb_database.name
  role     = "roles/spanner.databaseUser"
  member   = "serviceAccount:${google_service_account.kb_agent_sa.email}"
}

# Vertex AI (Gemini, embeddings, ranking API).
resource "google_project_iam_member" "agent_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.kb_agent_sa.email}"
}

# GCS — read uploaded documents from the documents bucket only (NOT project-wide).
resource "google_storage_bucket_iam_member" "agent_bucket_reader" {
  bucket = google_storage_bucket.documents.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.kb_agent_sa.email}"
}

# Optional: Knowledge Catalog / Dataplex bindings (only when KC_SYNC_ENABLED).
# Disabled by default. To enable, set var.enable_dataplex_kc = true and add
# any KC_* env vars to var.kb_agent_extra_env.
#
# resource "google_project_iam_member" "agent_dataplex_editor" {
#   count   = var.enable_dataplex_kc ? 1 : 0
#   project = var.project_id
#   role    = "roles/dataplex.catalogEditor"
#   member  = "serviceAccount:${google_service_account.kb_agent_sa.email}"
# }

# Spanner Service Agent needs Vertex permissions for REMOTE MODELS used by
# the schema (Gemini-backed embedding functions, etc.).
resource "google_project_service_identity" "spanner_sa" {
  provider   = google-beta
  project    = var.project_id
  service    = "spanner.googleapis.com"
  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "spanner_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_project_service_identity.spanner_sa.email}"
}
