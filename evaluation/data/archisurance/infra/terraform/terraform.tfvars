# ArchiSurance Production Environment
project_id    = "archisurance-prod-001"
region        = "europe-west1"
environment   = "production"
gke_node_count = 3
db_tier       = "db-custom-4-16384"

# INTENTIONAL VIOLATION: Hardcoded IP (should be variable or data source)
allowed_ip = "10.0.1.100"
