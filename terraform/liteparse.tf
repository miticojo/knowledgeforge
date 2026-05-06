# LiteParse internal Cloud Run service.
#
# Used by kb-agent (DOCLING_URL) to parse PDFs/DOCX/etc. Not part of the public
# surface — ingress is restricted to internal traffic and only the kb-agent SA
# can invoke it.

resource "google_service_account" "liteparse_sa" {
  account_id   = "liteparse-sa"
  display_name = "LiteParse Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

resource "google_cloud_run_v2_service" "liteparse" {
  name     = "liteparse"
  location = var.region
  project  = var.project_id

  # INTERNAL: only callable by other GCP services in the project (incl. kb-agent
  # via direct VPC egress or via Cloud Run service-to-service with ID token).
  ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.liteparse_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    timeout = "300s"

    containers {
      image = var.liteparse_image

      ports {
        container_port = 8090
      }

      resources {
        # PDFium + sharp need real CPU; matches cloudbuild.yaml.
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle          = false
        startup_cpu_boost = true
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Only kb-agent can invoke liteparse.
resource "google_cloud_run_v2_service_iam_member" "liteparse_invoker_kb_agent" {
  project  = google_cloud_run_v2_service.liteparse.project
  location = google_cloud_run_v2_service.liteparse.location
  name     = google_cloud_run_v2_service.liteparse.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.kb_agent_sa.email}"
}
