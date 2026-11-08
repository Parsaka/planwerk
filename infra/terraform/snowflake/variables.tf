variable "database_name" {
  type    = string
  default = "PLANWERK"
}

variable "monthly_credit_quota" {
  description = "Hard cost cap: the warehouse is suspended when the monthly credit quota is used up."
  type        = number
  default     = 10
}

variable "notify_users" {
  description = "Snowflake user names that receive resource-monitor notifications."
  type        = list(string)
  default     = []
}

variable "loader_rsa_public_key" {
  description = "Public key (PEM body without header) of the CI loader / dbt service user."
  type        = string
  sensitive   = true
}

variable "assistant_rsa_public_key" {
  description = "Public key of the read-only AI assistant service user."
  type        = string
  sensitive   = true
}
