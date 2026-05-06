# Cloud Run Service: kb-frontend (Next.js)
#
# Talks to kb-agent server-side via BACKEND_URL (used by the API route handlers
# under app/api/*) and exposes the same URL to the browser via
# NEXT_PUBLIC_BACKEND_URL for client-side fetches that bypass the proxy.

resource "google_service_account" "kb_frontend_sa" {
  account_id   = "kb-frontend-sa"
  display_name = "KB Frontend Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

resource "google_cloud_run_v2_service" "kb_frontend" {
  name     = "kb-frontend"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.kb_frontend_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = var.kb_frontend_image

      ports {
        container_port = 3000
      }

      env {
        name  = "BACKEND_URL"
        value = google_cloud_run_v2_service.kb_agent.uri
      }
      env {
        name  = "NEXT_PUBLIC_BACKEND_URL"
        value = google_cloud_run_v2_service.kb_agent.uri
      }
      env {
        name  = "LITEPARSE_URL"
        value = google_cloud_run_v2_service.liteparse.uri
      }
      env {
        name  = "NODE_ENV"
        value = "production"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        startup_cpu_boost = true
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_cloud_run_v2_service.kb_agent,
    google_cloud_run_v2_service.liteparse,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "kb_frontend_public" {
  count    = var.kb_frontend_allow_unauthenticated ? 1 : 0
  project  = google_cloud_run_v2_service.kb_frontend.project
  location = google_cloud_run_v2_service.kb_frontend.location
  name     = google_cloud_run_v2_service.kb_frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Allow kb-frontend SA to call liteparse directly (used by the /api/parse route
# in the frontend that talks to LITEPARSE_URL).
resource "google_cloud_run_v2_service_iam_member" "liteparse_invoker_kb_frontend" {
  project  = google_cloud_run_v2_service.liteparse.project
  location = google_cloud_run_v2_service.liteparse.location
  name     = google_cloud_run_v2_service.liteparse.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.kb_frontend_sa.email}"
}

output "kb_frontend_url" {
  description = "Public URL of the kb-frontend Cloud Run service."
  value       = google_cloud_run_v2_service.kb_frontend.uri
}
