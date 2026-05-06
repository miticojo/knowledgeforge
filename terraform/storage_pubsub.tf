# GCS Bucket for uploaded documents.
#
# `force_destroy = true` is convenient for dev — flip to false for prod so
# `terraform destroy` cannot wipe ingested documents.
resource "google_storage_bucket" "documents" {
  name          = "${var.gcs_bucket_name}-${var.project_id}"
  project       = var.project_id
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

# Pub/Sub topic for storage notifications.
resource "google_pubsub_topic" "document_uploads" {
  name       = "gcs-document-uploads"
  project    = var.project_id
  depends_on = [google_project_service.apis]
}

# Allow GCS Service Agent to publish to the topic.
data "google_storage_project_service_account" "gcs_account" {
  project = var.project_id
}

resource "google_pubsub_topic_iam_binding" "gcs_publisher" {
  topic   = google_pubsub_topic.document_uploads.id
  role    = "roles/pubsub.publisher"
  members = ["serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"]
}

# Notification: every uploaded object emits a Pub/Sub message.
resource "google_storage_notification" "notification" {
  bucket         = google_storage_bucket.documents.name
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.document_uploads.id
  event_types    = ["OBJECT_FINALIZE"]
  depends_on     = [google_pubsub_topic_iam_binding.gcs_publisher]
}

# Service Account for the Pub/Sub push subscription. Must hold run.invoker on
# the kb-agent service (see cloudrun.tf -> kb_agent_pubsub_invoker).
resource "google_service_account" "pubsub_invoker_sa" {
  account_id   = "pubsub-invoker-sa"
  display_name = "Pub/Sub Invoker SA"
  project      = var.project_id
  depends_on   = [google_project_service.apis]
}

# Pub/Sub Push Subscription -> kb-agent /ingest
resource "google_pubsub_subscription" "push_to_cloud_run" {
  name    = "push-to-cloud-run"
  topic   = google_pubsub_topic.document_uploads.name
  project = var.project_id

  ack_deadline_seconds = 60

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.kb_agent.uri}/ingest"

    oidc_token {
      service_account_email = google_service_account.pubsub_invoker_sa.email
    }
  }

  depends_on = [google_cloud_run_v2_service.kb_agent]
}

output "documents_bucket" {
  description = "GCS bucket for uploaded documents."
  value       = google_storage_bucket.documents.name
}
