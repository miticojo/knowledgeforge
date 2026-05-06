variable "project_id" {
  description = "GCP project ID for ArchiSurance"
  type        = string
}

variable "region" {
  description = "Primary deployment region"
  type        = string
  default     = "europe-west1"
}

variable "environment" {
  description = "Environment (dev, staging, production)"
  type        = string
  default     = "production"
}

variable "gke_node_count" {
  description = "Number of GKE nodes in the App Server Cluster"
  type        = number
  default     = 3
}

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-custom-4-16384"
}
