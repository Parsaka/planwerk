# Planwerk on Azure: Azure OpenAI (keyless, Entra ID only) for the controlling assistant, Key Vault
# for the Snowflake key pair, Log Analytics for diagnostics, a monthly budget, and a GitHub OIDC
# identity so CI needs no stored cloud secret.

data "azurerm_client_config" "current" {}

locals {
  name = "planwerk"
  tags = { project = "planwerk", data = "simulated", owner = "parsa-kamali", cost_center = "portfolio" }
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_log_analytics_workspace" "law" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5
  tags                = local.tags
}

resource "azurerm_cognitive_account" "openai" {
  name                  = "oai-${local.name}"
  location              = azurerm_resource_group.rg.location
  resource_group_name   = azurerm_resource_group.rg.name
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-${local.name}"
  local_auth_enabled    = false # no API keys: Entra ID tokens only
  tags                  = local.tags
  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = "planwerk-chat"
  cognitive_account_id = azurerm_cognitive_account.openai.id
  model {
    format  = "OpenAI"
    name    = var.openai_model.name
    version = var.openai_model.version
  }
  sku {
    name     = "DataZoneStandard" # processing stays in the EU data zone
    capacity = var.openai_capacity_k_tpm
  }
}

resource "azurerm_monitor_diagnostic_setting" "openai" {
  name                       = "diag-openai"
  target_resource_id         = azurerm_cognitive_account.openai.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
  enabled_log {
    category_group = "audit"
  }
  enabled_metric {
    category = "AllMetrics"
  }
}

resource "azurerm_key_vault" "kv" {
  name                       = "kv-${local.name}-${substr(md5(data.azurerm_client_config.current.subscription_id), 0, 6)}"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 7
  tags                       = local.tags
}

resource "azurerm_search_service" "search" {
  count                        = var.enable_ai_search ? 1 : 0
  name                         = "srch-${local.name}"
  location                     = azurerm_resource_group.rg.location
  resource_group_name          = azurerm_resource_group.rg.name
  sku                          = "free"
  local_authentication_enabled = false
  tags                         = local.tags
}

# ---- GitHub Actions identity (OIDC federation, no secret) --------------------------------------
resource "azurerm_user_assigned_identity" "ci" {
  name                = "id-${local.name}-github"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "main" {
  name                = "github-main"
  resource_group_name = azurerm_resource_group.rg.name
  parent_id           = azurerm_user_assigned_identity.ci.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = coalesce(var.github_oidc_subject, "repo:${var.github_repository}:environment:eval")
}

resource "azurerm_role_assignment" "ci_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User" # inference only, cannot change the resource
  principal_id         = azurerm_user_assigned_identity.ci.principal_id
}

resource "azurerm_role_assignment" "ci_kv_reader" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.ci.principal_id
}

# ---- cost cap ---------------------------------------------------------------------------------
resource "azurerm_consumption_budget_resource_group" "budget" {
  name              = "budget-${local.name}"
  resource_group_id = azurerm_resource_group.rg.id
  amount            = var.monthly_budget_eur
  time_grain        = "Monthly"
  time_period {
    start_date = var.budget_start_date
  }
  dynamic "notification" {
    for_each = { for t in [50, 80, 100] : tostring(t) => t }
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = var.budget_contact_emails
    }
  }
  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Forecasted"
    contact_emails = var.budget_contact_emails
  }
}
