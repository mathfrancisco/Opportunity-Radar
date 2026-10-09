# OCI Resource Manager injects provider authentication for the approved stack.
# Do not add API keys, tenancy OCIDs, or private keys to this root.
provider "oci" {
  region = var.region
}
