terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
  # backend "azurerm" { resource_group_name = "rg-planwerk-tfstate" storage_account_name = "<name>" container_name = "tfstate" key = "planwerk-azure.tfstate" use_oidc = true }
}

provider "azurerm" {
  features {}
  use_oidc        = true # GitHub Actions federated credential, no client secret
  subscription_id = var.subscription_id
}
