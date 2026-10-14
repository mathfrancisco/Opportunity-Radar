data "oci_objectstorage_namespace" "current" {
  compartment_id = var.compartment_id
}

resource "oci_objectstorage_bucket" "backups" {
  compartment_id = var.compartment_id
  name           = var.backup_bucket_name
  namespace      = data.oci_objectstorage_namespace.current.namespace
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  freeform_tags = merge(local.common_tags, {
    purpose               = "future-backups"
    storage_limit_gbs     = tostring(var.backup_storage_limit_gbs)
    monthly_request_limit = tostring(var.backup_monthly_request_limit)
  })

  lifecycle {
    precondition {
      condition     = var.backup_storage_limit_gbs <= 20 && var.backup_monthly_request_limit <= 50000
      error_message = "Backup guardrails must remain within 20 GB and 50,000 monthly requests."
    }
  }
}
