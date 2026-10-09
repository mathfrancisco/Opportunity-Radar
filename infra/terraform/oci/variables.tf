variable "region" {
  description = "OCI home region selected during the manual Resource Manager bootstrap."
  type        = string

  validation {
    condition     = length(trimspace(var.region)) > 0
    error_message = "region must be a non-empty OCI region name."
  }
}

variable "compartment_id" {
  description = "OCID of the manually approved pilot compartment."
  type        = string

  validation {
    condition     = can(regex("^ocid1\\.compartment\\.", var.compartment_id))
    error_message = "compartment_id must be an OCI compartment OCID."
  }
}

variable "availability_domain" {
  description = "Availability domain with confirmed A1 capacity."
  type        = string

  validation {
    condition     = length(trimspace(var.availability_domain)) > 0
    error_message = "availability_domain must not be empty."
  }
}

variable "arm_image_id" {
  description = "Approved ARM64 platform image OCID; select it in OCI, never infer it from a secret."
  type        = string

  validation {
    condition     = can(regex("^ocid1\\.image\\.", var.arm_image_id))
    error_message = "arm_image_id must be an OCI image OCID."
  }
}

variable "ssh_public_key" {
  description = "Administrative public SSH key only. Generate the key pair outside Terraform."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^(ssh-(ed25519|rsa)|ecdsa-sha2-)", trimspace(var.ssh_public_key)))
    error_message = "ssh_public_key must be a public OpenSSH key; never provide a private key."
  }
}

variable "vcn_cidr" {
  description = "RFC1918 CIDR for the pilot VCN."
  type        = string
  default     = "10.53.0.0/16"

  validation {
    condition     = can(cidrhost(var.vcn_cidr, 0)) && can(regex("^(10\\.|172\\.(1[6-9]|2[0-9]|3[0-1])\\.|192\\.168\\.)", var.vcn_cidr))
    error_message = "vcn_cidr must be a private RFC1918 CIDR."
  }
}

variable "public_subnet_cidr" {
  description = "Public subnet CIDR contained by vcn_cidr."
  type        = string
  default     = "10.53.10.0/24"

  validation {
    condition     = can(cidrhost(var.public_subnet_cidr, 0))
    error_message = "public_subnet_cidr must be a valid CIDR."
  }
}

variable "admin_cidr" {
  description = "Required administrative source CIDR for SSH. It must never be open to the Internet."
  type        = string

  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && var.admin_cidr != "0.0.0.0/0" && var.admin_cidr != "::/0"
    error_message = "admin_cidr must be a specific administrative CIDR, never 0.0.0.0/0 or ::/0."
  }
}

variable "instance_shape" {
  description = "Always Free ARM shape only."
  type        = string
  default     = "VM.Standard.A1.Flex"

  validation {
    condition     = var.instance_shape == "VM.Standard.A1.Flex"
    error_message = "Only VM.Standard.A1.Flex is allowed by this Always Free root."
  }
}

variable "shape_ocpus" {
  description = "A1 OCPUs; the tenancy-wide Always Free maximum is two."
  type        = number
  default     = 2

  validation {
    condition     = var.shape_ocpus > 0 && var.shape_ocpus <= 2
    error_message = "shape_ocpus must be greater than zero and no more than 2."
  }
}

variable "shape_memory_in_gbs" {
  description = "A1 memory; the tenancy-wide Always Free maximum is 12 GB."
  type        = number
  default     = 12

  validation {
    condition     = var.shape_memory_in_gbs > 0 && var.shape_memory_in_gbs <= 12
    error_message = "shape_memory_in_gbs must be greater than zero and no more than 12."
  }
}

variable "boot_volume_size_gbs" {
  description = "Boot volume capped at the approved 50 GB pilot size."
  type        = number
  default     = 50

  validation {
    condition     = var.boot_volume_size_gbs == 50
    error_message = "boot_volume_size_gbs is fixed at 50 GB for this approved pilot."
  }
}

variable "backup_bucket_name" {
  description = "Globally unique, lowercase private bucket name for future F53-14 use."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.backup_bucket_name))
    error_message = "backup_bucket_name must be 3-63 lowercase letters, digits, dots, or hyphens."
  }
}

variable "backup_storage_limit_gbs" {
  description = "Operational guardrail for F53-14; OCI bucket quotas are not enforced by this resource."
  type        = number
  default     = 20

  validation {
    condition     = var.backup_storage_limit_gbs > 0 && var.backup_storage_limit_gbs <= 20
    error_message = "backup_storage_limit_gbs must be greater than zero and no more than 20."
  }
}

variable "backup_monthly_request_limit" {
  description = "Operational guardrail for F53-14; monitor bucket requests against this limit."
  type        = number
  default     = 50000

  validation {
    condition     = var.backup_monthly_request_limit > 0 && var.backup_monthly_request_limit <= 50000
    error_message = "backup_monthly_request_limit must be greater than zero and no more than 50000."
  }
}

variable "resource_prefix" {
  description = "Short public identifier for pilot resources."
  type        = string
  default     = "opportunity-radar"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,30}$", var.resource_prefix))
    error_message = "resource_prefix must contain 3-30 lowercase letters, digits, or hyphens."
  }
}
