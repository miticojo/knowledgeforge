# Artifact Registry repository for KnowledgeForge container images.
# CI/CD pushes kb-agent / kb-frontend / liteparse here, then Cloud Run pulls.
resource "google_artifact_registry_repository" "knowledgeforge" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repo
  description   = "KnowledgeForge container images (kb-agent, kb-frontend, liteparse)"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}
