# Corporate LAN (CommunicationNetwork)
resource "google_compute_network" "main" {
  name                    = "archisurance-vpc"
  auto_create_subnetworks = false
  description             = "Corporate LAN — primary network for all ArchiSurance services"
}

# DMZ Network (CommunicationNetwork)
resource "google_compute_subnetwork" "dmz" {
  name          = "dmz-subnet"
  network       = google_compute_network.main.id
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  description   = "DMZ Network — hosts Load Balancer F5, API Gateway, WAF"
}

# Private subnet for application workloads
resource "google_compute_subnetwork" "private" {
  name          = "private-subnet"
  network       = google_compute_network.main.id
  ip_cidr_range = "10.0.2.0/24"
  region        = var.region
  description   = "Private subnet — App Server Cluster, Database Servers"
}

# Management VLAN (CommunicationNetwork)
resource "google_compute_subnetwork" "management" {
  name          = "management-subnet"
  network       = google_compute_network.main.id
  ip_cidr_range = "10.0.10.0/24"
  region        = var.region
  description   = "Management VLAN — monitoring, CI/CD, bastion hosts"
}

# INTENTIONAL VIOLATION: Overly permissive firewall rule (IAC-002)
resource "google_compute_firewall" "allow_all_internal" {
  name    = "allow-all-internal"
  network = google_compute_network.main.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  # VIOLATION: 0.0.0.0/0 allows traffic from anywhere
  source_ranges = ["0.0.0.0/0"]

  description = "Allow all internal traffic — NEEDS TIGHTENING"
}

# Cloud VPN (CommunicationNetwork) — connects to on-premise data center
resource "google_compute_vpn_gateway" "vpn" {
  name    = "archisurance-vpn"
  network = google_compute_network.main.id
  region  = var.region
}
