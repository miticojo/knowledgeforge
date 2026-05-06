# Provider configuration.
#
# State backend is intentionally local — wire up a GCS backend block here
# before running `terraform init` against a shared/prod project:
#
#   terraform {
#     backend "gcs" {
#       bucket = "my-tf-state-bucket"
#       prefix = "knowledgeforge"
#     }
#   }

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
