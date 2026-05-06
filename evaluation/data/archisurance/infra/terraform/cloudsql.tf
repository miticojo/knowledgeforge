# Database Server Primary (Node) — runs PostgreSQL 15 (SystemSoftware)
# Serves: Claims Management Platform, Policy Administration System, CRM System

resource "google_sql_database_instance" "primary" {
  name             = "archisurance-db-primary"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = var.db_tier

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    # INTENTIONAL VIOLATION: No backup_configuration (IAC-003)
    # backup_configuration {
    #   enabled    = true
    #   start_time = "02:00"
    # }

    database_flags {
      name  = "max_connections"
      value = "200"
    }
  }

  deletion_protection = true
}

# Database Server Replica (Node)
resource "google_sql_database_instance" "replica" {
  name                 = "archisurance-db-replica"
  master_instance_name = google_sql_database_instance.primary.name
  database_version     = "POSTGRES_15"
  region               = var.region

  replica_configuration {
    failover_target = true
  }

  settings {
    tier = var.db_tier
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }
  }
}

# Oracle Database 19c (SystemSoftware) — legacy, migration planned Q4 2026
# Currently serves: Billing System, Data Warehouse
# Constraint: "Legacy Oracle DB Migration Deadline Q4 2026"
resource "google_sql_database_instance" "oracle_legacy" {
  name             = "archisurance-oracle-legacy"
  # NOTE: GCP doesn't natively support Oracle — this would be a Compute Engine VM
  # Represented here for architecture mapping purposes
  database_version = "POSTGRES_15"  # Placeholder — actual Oracle on bare metal
  region           = var.region

  settings {
    tier = "db-custom-8-32768"
  }
}
