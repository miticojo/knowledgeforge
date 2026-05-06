# Cloud Run Service: kb-agent (Python / FastAPI / ADK)
#
# Env wiring mirrors kb-agent/main.py + services/spanner_client.py:
#   - PROJECT_ID / GOOGLE_CLOUD_PROJECT  -> Spanner client + Vertex AI client
#   - SPANNER_INSTANCE / SPANNER_DATABASE -> services/spanner_client.py
#   - GOOGLE_GENAI_USE_VERTEXAI=1        -> route google-genai SDK through Vertex
#                                            (use ADC; no API key needed)
#   - DOCLING_URL                        -> liteparse internal Cloud Run URL
#                                            (services/document_ingester.py also
#                                            accepts LITEPARSE_URL as fallback)
#   - GEMINI_API_KEY                     -> Secret Manager (only used outside Vertex)
#   - ENV=production                     -> disables uvicorn --reload
#
# Knowledge Catalog (Dataplex) env vars are NOT set here by default; toggle via
# `var.enable_dataplex_kc` + `var.kb_agent_extra_env` if KC_SYNC_ENABLED is desired.

resource "google_cloud_run_v2_service" "kb_agent" {
  name     = "kb-agent"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.kb_agent_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = var.kb_agent_image

      ports {
        container_port = 8080
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "SPANNER_PROJECT"
        value = var.project_id
      }
      env {
        name  = "SPANNER_INSTANCE"
        value = google_spanner_instance.kb_instance.name
      }
      env {
        name  = "SPANNER_DATABASE"
        value = google_spanner_database.kb_database.name
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "1"
      }
      env {
        name  = "ENV"
        value = "production"
      }
      env {
        name  = "PORT"
        value = "8080"
      }
      env {
        name  = "DOCLING_URL"
        value = google_cloud_run_v2_service.liteparse.uri
      }
      env {
        name  = "LITEPARSE_URL"
        value = google_cloud_run_v2_service.liteparse.uri
      }
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.documents.name
      }

      # Operator-supplied extras (KC_*, MODEL_ARMOR_TEMPLATE_ID, …)
      dynamic "env" {
        for_each = var.kb_agent_extra_env
        content {
          name  = env.key
          value = env.value
        }
      }

      # Gemini API key from Secret Manager (latest version).
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        startup_cpu_boost = true
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 6
        timeout_seconds       = 5
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 30
        failure_threshold = 3
        timeout_seconds   = 5
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_service_account.kb_agent_sa,
    google_secret_manager_secret_iam_member.kb_agent_gemini_accessor,
    google_cloud_run_v2_service.liteparse,
  ]
}

# Public access toggle. Default is allUsers because the demo is intentionally
# wide-open; flip `kb_agent_allow_unauthenticated=false` for a real deployment
# and rely on the frontend SA + run.invoker binding instead.
resource "google_cloud_run_v2_service_iam_member" "kb_agent_public" {
  count    = var.kb_agent_allow_unauthenticated ? 1 : 0
  project  = google_cloud_run_v2_service.kb_agent.project
  location = google_cloud_run_v2_service.kb_agent.location
  name     = google_cloud_run_v2_service.kb_agent.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Pub/Sub push subscription invokes /ingest with an OIDC token from
# pubsub_invoker_sa — grant that SA invoke permission on this service.
resource "google_cloud_run_v2_service_iam_member" "kb_agent_pubsub_invoker" {
  project  = google_cloud_run_v2_service.kb_agent.project
  location = google_cloud_run_v2_service.kb_agent.location
  name     = google_cloud_run_v2_service.kb_agent.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_invoker_sa.email}"
}

# Allow the frontend to invoke the agent (used when allow_unauthenticated=false).
resource "google_cloud_run_v2_service_iam_member" "kb_agent_frontend_invoker" {
  project  = google_cloud_run_v2_service.kb_agent.project
  location = google_cloud_run_v2_service.kb_agent.location
  name     = google_cloud_run_v2_service.kb_agent.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.kb_frontend_sa.email}"
}

output "kb_agent_url" {
  description = "Public URL of the kb-agent Cloud Run service."
  value       = google_cloud_run_v2_service.kb_agent.uri
}
