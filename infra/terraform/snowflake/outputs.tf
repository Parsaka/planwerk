output "database" { value = snowflake_database.db.name }
output "warehouse" { value = snowflake_warehouse.wh.name }
output "roles" {
  value = [snowflake_account_role.loader.name, snowflake_account_role.transformer.name,
  snowflake_account_role.reporter.name, snowflake_account_role.assistant.name]
}
