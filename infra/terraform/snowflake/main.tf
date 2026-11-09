# Planwerk on Snowflake: one database, one XS warehouse with a hard monthly credit cap,
# least-privilege roles (loader -> transformer -> reporter/assistant), key-pair service users.
# Row-level security per cost-centre owner is created by dbt (macro apply_cost_centre_policy).

locals {
  schemas = {
    S4_RAW       = "S/4HANA extracts as loaded (Parquet -> tables)"
    STAGING      = "dbt staging views"
    INTERMEDIATE = "dbt intermediate tables (BAB allocation, costed sales items)"
    CORE         = "Kimball dimensions and facts"
    CONTROLLING  = "Controlling marts (DB I-III, BAB, PVM, GKV)"
    SEMANTIC     = "Semantic views for SAC and the AI assistant"
    FORECAST     = "Rolling forecast and liquidity outputs"
    REFERENCE    = "Seeds: access list, DB scheme, GKV mapping"
  }
}

resource "snowflake_resource_monitor" "cap" {
  name            = "PLANWERK_MONTHLY_CAP"
  credit_quota    = var.monthly_credit_quota
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"
  notify_triggers = [50, 80]
  suspend_trigger = 100
  # suspend running queries too at 110 % (protects against a runaway query at month end)
  suspend_immediate_trigger = 110
  notify_users              = var.notify_users
}

resource "snowflake_warehouse" "wh" {
  name                = "PLANWERK_WH"
  warehouse_size      = "XSMALL"
  auto_suspend        = 60
  auto_resume         = "true"
  initially_suspended = true
  resource_monitor    = snowflake_resource_monitor.cap.name
  comment             = "Planwerk (simulated Nordwerk GmbH data)"
}

resource "snowflake_database" "db" {
  name                        = var.database_name
  data_retention_time_in_days = 7
  comment                     = "Planwerk controlling platform - simulated data"
}

resource "snowflake_schema" "s" {
  for_each = local.schemas
  database = snowflake_database.db.name
  name     = each.key
  comment  = each.value
}

# ---- roles ------------------------------------------------------------------------------------
resource "snowflake_account_role" "loader" {
  name    = "PLANWERK_LOADER"
  comment = "Writes S4_RAW only"
}

resource "snowflake_account_role" "transformer" {
  name    = "PLANWERK_TRANSFORMER"
  comment = "dbt: reads S4_RAW, owns STAGING..SEMANTIC"
}

resource "snowflake_account_role" "reporter" {
  name    = "PLANWERK_REPORTER"
  comment = "Controllers, SAC live connection: read CONTROLLING and SEMANTIC"
}

resource "snowflake_account_role" "assistant" {
  name    = "PLANWERK_ASSISTANT"
  comment = "AI assistant: read SEMANTIC only"
}

resource "snowflake_grant_account_role" "hierarchy" {
  for_each         = toset([snowflake_account_role.loader.name, snowflake_account_role.transformer.name, snowflake_account_role.reporter.name, snowflake_account_role.assistant.name])
  role_name        = each.value
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_privileges_to_account_role" "wh_usage" {
  for_each          = toset([snowflake_account_role.loader.name, snowflake_account_role.transformer.name, snowflake_account_role.reporter.name, snowflake_account_role.assistant.name])
  account_role_name = each.value
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "db_usage" {
  for_each          = toset([snowflake_account_role.loader.name, snowflake_account_role.transformer.name, snowflake_account_role.reporter.name, snowflake_account_role.assistant.name])
  account_role_name = each.value
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.db.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "loader_raw" {
  account_role_name = snowflake_account_role.loader.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE STAGE", "CREATE FILE FORMAT"]
  on_schema {
    schema_name = "\"${snowflake_database.db.name}\".\"${snowflake_schema.s["S4_RAW"].name}\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_raw_read" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "\"${snowflake_database.db.name}\".\"${snowflake_schema.s["S4_RAW"].name}\""
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_schemas" {
  for_each          = toset(["STAGING", "INTERMEDIATE", "CORE", "CONTROLLING", "SEMANTIC", "FORECAST", "REFERENCE"])
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE ROW ACCESS POLICY"]
  on_schema {
    schema_name = "\"${snowflake_database.db.name}\".\"${snowflake_schema.s[each.key].name}\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_apply_rap" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["APPLY ROW ACCESS POLICY"]
  on_account        = true
}

resource "snowflake_grant_privileges_to_account_role" "transformer_raw_usage" {
  account_role_name = snowflake_account_role.transformer.name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "\"${snowflake_database.db.name}\".\"${snowflake_schema.s["S4_RAW"].name}\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "reporter_usage" {
  for_each          = toset(["CONTROLLING", "SEMANTIC", "FORECAST"])
  account_role_name = snowflake_account_role.reporter.name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "\"${snowflake_database.db.name}\".\"${snowflake_schema.s[each.key].name}\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "reporter_read" {
  for_each          = { for p in setproduct(["CONTROLLING", "SEMANTIC", "FORECAST"], ["TABLES", "VIEWS"]) : "${p[0]}_${p[1]}" => p }
  account_role_name = snowflake_account_role.reporter.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = each.value[1]
      in_schema          = "\"${snowflake_database.db.name}\".\"${snowflake_schema.s[each.value[0]].name}\""
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "assistant_usage" {
  account_role_name = snowflake_account_role.assistant.name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "\"${snowflake_database.db.name}\".\"${snowflake_schema.s["SEMANTIC"].name}\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "assistant_read" {
  account_role_name = snowflake_account_role.assistant.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_schema          = "\"${snowflake_database.db.name}\".\"${snowflake_schema.s["SEMANTIC"].name}\""
    }
  }
}

# ---- service users (key pair only, no password) -------------------------------------------------
resource "snowflake_service_user" "ci" {
  name              = "PLANWERK_CI"
  comment           = "GitHub Actions: load S4_RAW and run dbt"
  default_role      = snowflake_account_role.transformer.name
  default_warehouse = snowflake_warehouse.wh.name
  rsa_public_key    = var.loader_rsa_public_key
}

resource "snowflake_service_user" "assistant" {
  name              = "PLANWERK_ASSISTANT"
  comment           = "AI assistant: read-only on SEMANTIC"
  default_role      = snowflake_account_role.assistant.name
  default_warehouse = snowflake_warehouse.wh.name
  rsa_public_key    = var.assistant_rsa_public_key
}

resource "snowflake_grant_account_role" "ci_roles" {
  for_each  = toset([snowflake_account_role.loader.name, snowflake_account_role.transformer.name])
  role_name = each.value
  user_name = snowflake_service_user.ci.name
}

resource "snowflake_grant_account_role" "assistant_role" {
  role_name = snowflake_account_role.assistant.name
  user_name = snowflake_service_user.assistant.name
}
