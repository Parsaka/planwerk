terraform {
  required_version = ">= 1.6"
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.0"
    }
  }
  # Remote state: use the azurerm backend from ../azure (storage account) in a real deployment:
  # backend "azurerm" { key = "planwerk-snowflake.tfstate" }
}

# Authentication via environment variables only (never in code):
#   SNOWFLAKE_ORGANIZATION_NAME, SNOWFLAKE_ACCOUNT_NAME, SNOWFLAKE_USER,
#   SNOWFLAKE_AUTHENTICATOR=SNOWFLAKE_JWT, SNOWFLAKE_PRIVATE_KEY (from GitHub secret / Key Vault)
provider "snowflake" {
  role = "ACCOUNTADMIN"
}
