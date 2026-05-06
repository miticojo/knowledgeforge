# Secret Manager: Gemini API key
#
# Two paths:
#   1) `var.create_gemini_api_key_secret = true` (default for greenfield):
#      Terraform manages the secret CONTAINER. The secret VALUE must still be
#      added out-of-band — never commit the value to Git:
#
#          echo -n "YOUR_GEMINI_KEY" | gcloud secrets versions add \
#              ${var.gemini_api_key_secret_id} --data-file=- --project=${var.project_id}
#
#   2) `var.create_gemini_api_key_secret = false`:
#      The secret is assumed to already exist (e.g. created by an org-level
#      bootstrap or a separate stack). Terraform only references it.
#
# Either way, the kb-agent Cloud Run service mounts the LATEST version as the
# GEMINI_API_KEY env var via `value_source.secret_key_ref` (see cloudrun.tf).

resource "google_secret_manager_secret" "gemini_api_key" {
  count     = var.create_gemini_api_key_secret ? 1 : 0
  project   = var.project_id
  secret_id = var.gemini_api_key_secret_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# Resolve the secret name regardless of whether we created it or it pre-exists.
# Used by cloudrun.tf to wire the env var.
data "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project_id
  secret_id = var.gemini_api_key_secret_id

  depends_on = [google_secret_manager_secret.gemini_api_key]
}

# Allow kb-agent SA to read the secret value at runtime.
resource "google_secret_manager_secret_iam_member" "kb_agent_gemini_accessor" {
  project   = var.project_id
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.kb_agent_sa.email}"
}
