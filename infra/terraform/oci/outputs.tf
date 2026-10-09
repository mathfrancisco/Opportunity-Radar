output "resource_manager_iam_policy_template" {
  description = "Manual least-privilege policy template; placeholders must be replaced in OCI Console."
  value       = local.required_iam_policy_statements
}

output "network_security_group_id" {
  description = "NSG ID for the approved plan review."
  value       = oci_core_network_security_group.api.id
}

output "instance_id" {
  description = "Instance ID after an explicitly approved apply."
  value       = oci_core_instance.api.id
}

output "backup_bucket_name" {
  description = "Private future-backup bucket name; it contains no credential."
  value       = oci_objectstorage_bucket.backups.name
}
