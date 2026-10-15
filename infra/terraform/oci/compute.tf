resource "oci_core_instance" "api" {
  compartment_id      = var.compartment_id
  availability_domain = var.availability_domain
  display_name        = "${var.resource_prefix}-api"
  shape               = var.instance_shape
  freeform_tags       = local.common_tags

  shape_config {
    ocpus         = var.shape_ocpus
    memory_in_gbs = var.shape_memory_in_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    nsg_ids          = [oci_core_network_security_group.api.id]
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }

  source_details {
    source_type             = "image"
    source_id               = var.enable_free_trial ? var.trial_image_id : var.arm_image_id
    boot_volume_size_in_gbs = var.boot_volume_size_gbs
  }

  lifecycle {
    precondition {
      condition     = var.enable_free_trial ? contains(["VM.Standard.E4.Flex", "VM.Standard.E5.Flex"], var.instance_shape) && var.shape_ocpus == 1 && var.shape_memory_in_gbs == 8 && var.trial_image_id != null : var.instance_shape == "VM.Standard.A1.Flex" && var.shape_ocpus <= 2 && var.shape_memory_in_gbs <= 12 && var.arm_image_id != null
      error_message = "Use A1 within Always Free limits by default; temporary Free Trial mode requires E4 or E5 Flex, 1 OCPU, 8 GB and its x86 image."
    }

    precondition {
      condition     = var.boot_volume_size_gbs <= 50
      error_message = "The pilot boot volume must not exceed 50 GB."
    }
  }
}
