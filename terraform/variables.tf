variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID. MUST be overridden — placeholder default is intentionally invalid."
  default     = "your-gcp-project"
}

variable "region" {
  type        = string
  description = "The region to deploy resources (e.g. europe-west1, us-central1). Must be a valid Cloud Run + Spanner regional config."
  default     = "us-central1"
}

variable "spanner_instance_name" {
  type        = string
  description = "Name for the Spanner instance"
  default     = "kb-instance"
}

variable "spanner_db_name" {
  type        = string
  description = "Name for the Spanner database"
  default     = "kb-db"
}

variable "spanner_processing_units" {
  type        = number
  description = "Spanner processing units (100 PU = 1/10th of a node). Use 100 for dev, >=1000 for prod."
  default     = 100
}

variable "gcs_bucket_name" {
  type        = string
  description = "Prefix for the GCS bucket for document uploads. The full name will be `<prefix>-<project_id>`."
  default     = "kb-documents"
}

variable "artifact_registry_repo" {
  type        = string
  description = "Artifact Registry repository name for container images."
  default     = "knowledgeforge"
}

variable "kb_agent_image" {
  type        = string
  description = "Container image for the kb-agent service. Defaults to a hello placeholder; CI/CD should pin an immutable digest."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "kb_frontend_image" {
  type        = string
  description = "Container image for the kb-frontend service."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "liteparse_image" {
  type        = string
  description = "Container image for the liteparse internal service."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "gemini_api_key_secret_id" {
  type        = string
  description = "Secret Manager secret ID holding the Gemini API key. The secret must already exist (or be created by Terraform — see secrets.tf). Mounted into kb-agent as GEMINI_API_KEY."
  default     = "gemini-api-key"
}

variable "create_gemini_api_key_secret" {
  type        = bool
  description = "Whether Terraform should manage the empty Secret Manager secret container. Set true for greenfield, false if the secret already exists."
  default     = true
}

variable "kb_agent_allow_unauthenticated" {
  type        = bool
  description = "Allow unauthenticated public traffic to kb-agent. Set to false to require IAM auth (recommended for prod; the frontend uses an ID token via SA)."
  default     = true
}

variable "kb_frontend_allow_unauthenticated" {
  type        = bool
  description = "Allow unauthenticated public traffic to kb-frontend (the public web UI)."
  default     = true
}

variable "enable_dataplex_kc" {
  type        = bool
  description = "Enable Dataplex / Knowledge Catalog API + IAM. Required when KC_SYNC_ENABLED=true is set on kb-agent."
  default     = false
}

variable "kb_agent_extra_env" {
  type        = map(string)
  description = "Extra plain-text env vars to inject into kb-agent (non-secret). Useful for KC_*, MODEL_ARMOR_TEMPLATE_ID, etc."
  default     = {}
}
