output "openai_endpoint" { value = azurerm_cognitive_account.openai.endpoint }
output "openai_deployment" { value = azurerm_cognitive_deployment.chat.name }
output "ci_client_id" {
  description = "Set as GitHub variable AZURE_CLIENT_ID (not a secret)."
  value       = azurerm_user_assigned_identity.ci.client_id
}
output "tenant_id" { value = data.azurerm_client_config.current.tenant_id }
output "key_vault_uri" { value = azurerm_key_vault.kv.vault_uri }
