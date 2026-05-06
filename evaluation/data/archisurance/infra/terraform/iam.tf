# IAM — maps to BusinessRole → Assignment relationships
# Identity & Access Management (ApplicationComponent)

# Claims Service Account
resource "google_service_account" "claims_service" {
  account_id   = "claims-service"
  display_name = "Claims Management Platform SA"
  description  = "Service account for Claims Management Platform (ApplicationComponent)"
}

# Risk Engine Service Account
resource "google_service_account" "risk_engine" {
  account_id   = "risk-engine"
  display_name = "Risk Engine SA"
  description  = "Service account for Risk Engine (ApplicationComponent)"
}

# INTENTIONAL VIOLATION: roles/owner on service account (IAC-005)
resource "google_project_iam_member" "claims_owner" {
  project = var.project_id
  role    = "roles/owner"  # VIOLATION: Should be roles/cloudsql.client or similar
  member  = "serviceAccount:${google_service_account.claims_service.email}"
}

# Correct IAM binding example
resource "google_project_iam_member" "risk_engine_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.risk_engine.email}"
}
