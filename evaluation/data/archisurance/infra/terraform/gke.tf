# App Server Cluster (Node) — runs Kubernetes (SystemSoftware)
# Hosts: Claims Management Platform, Risk Engine, Customer Portal,
#         Fraud Detection Engine, API Gateway, and other ApplicationComponents.

resource "google_container_cluster" "app_cluster" {
  name     = "archisurance-app-cluster"
  location = var.region

  # INTENTIONAL VIOLATION: Missing labels (IAC-001)
  # labels should include: environment, team, cost-center

  initial_node_count = var.gke_node_count

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
  }

  # INTENTIONAL VIOLATION: Missing network_policy (IAC-004)
  # network_policy { enabled = true }

  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }
}

# Container Orchestration (TechnologyService)
# Kubernetes manages all containerized ApplicationComponents.
