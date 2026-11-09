variable "subscription_id" {
  type = string
}

variable "location" {
  description = "EU region (data residency, DSGVO)."
  type        = string
  default     = "swedencentral"
}

variable "github_repository" {
  description = "owner/name of the repository allowed to deploy and run the eval via OIDC."
  type        = string
  default     = "Parsaka/planwerk"
}

variable "openai_model" {
  description = "Small chat model. gpt-4o-mini and gpt-4.1-mini are deprecated in Azure: subscriptions that never deployed them cannot deploy them any more."
  type        = object({ name = string, version = string })
  default = {
    name    = "gpt-5-mini"
    version = "2025-08-07"
  }
}

variable "openai_capacity_k_tpm" {
  description = "Hard throughput cap of the deployment in thousand tokens per minute."
  type        = number
  default     = 30
}

variable "monthly_budget_eur" {
  description = "Cost cap: budget alerts at 50/80/100 % (actual) and 100 % (forecast)."
  type        = number
  default     = 20
}

variable "budget_contact_emails" {
  type    = list(string)
  default = []
}

variable "enable_ai_search" {
  description = "Azure AI Search (free tier) for the method-documentation retrieval (RAG)."
  type        = bool
  default     = false
}

variable "budget_start_date" {
  description = "First day of the budget period (RFC 3339, first of a month)."
  type        = string
  default     = "2026-12-01T00:00:00Z"
}
