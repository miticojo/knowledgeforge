# Spanner Instance.
#
# We use processing units (PU) instead of nodes — 1000 PU = 1 node, and 100 PU
# is the smallest dev-sized footprint. Override `var.spanner_processing_units`
# for prod.
resource "google_spanner_instance" "kb_instance" {
  name             = var.spanner_instance_name
  config           = "regional-${var.region}"
  display_name     = "KnowledgeForge Spanner"
  processing_units = var.spanner_processing_units
  project          = var.project_id

  depends_on = [google_project_service.apis]
}

# Spanner Database.
#
# DDL is intentionally NOT managed via the Terraform `ddl` argument. The schema
# in `database/spanner_schema.sdl` (plus migrations under `database/migrations/`)
# uses GoogleSQL graph features and REMOTE MODEL declarations that the
# google_spanner_database provider's diff logic handles poorly. Apply schema
# out-of-band:
#
#   gcloud spanner databases ddl update ${var.spanner_db_name} \
#       --instance=${var.spanner_instance_name} \
#       --project=${var.project_id} \
#       --ddl-file=../database/spanner_schema.sdl
#
#   for f in ../database/migrations/*.sql; do
#     gcloud spanner databases ddl update ${var.spanner_db_name} \
#         --instance=${var.spanner_instance_name} \
#         --project=${var.project_id} \
#         --ddl-file="$f"
#   done
resource "google_spanner_database" "kb_database" {
  instance = google_spanner_instance.kb_instance.name
  name     = var.spanner_db_name
  project  = var.project_id

  # Allow `terraform destroy` to drop the DB. Flip to true for prod.
  deletion_protection = false
}

output "spanner_instance" {
  description = "Spanner instance name."
  value       = google_spanner_instance.kb_instance.name
}

output "spanner_database" {
  description = "Spanner database name."
  value       = google_spanner_database.kb_database.name
}
