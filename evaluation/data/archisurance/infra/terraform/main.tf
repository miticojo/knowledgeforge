# ArchiSurance Infrastructure — Google Cloud Platform
# Manages the infrastructure for all ArchiMate Technology Layer entities.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
  backend "gcs" {
    bucket = "archisurance-tf-state"
    prefix = "production"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
