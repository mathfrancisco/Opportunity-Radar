locals {
  common_tags = {
    service     = "opportunity-radar"
    environment = "pilot"
    managed_by  = "terraform"
    cost_tier   = "always-free-target"
  }
}

resource "oci_core_vcn" "pilot" {
  compartment_id = var.compartment_id
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.resource_prefix}-vcn"
  dns_label      = "oppradar"
  freeform_tags  = local.common_tags
}

resource "oci_core_internet_gateway" "pilot" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.pilot.id
  display_name   = "${var.resource_prefix}-igw"
  enabled        = true
  freeform_tags  = local.common_tags
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.pilot.id
  display_name   = "${var.resource_prefix}-public-routes"
  freeform_tags  = local.common_tags

  route_rules {
    network_entity_id = oci_core_internet_gateway.pilot.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }
}

# Associate an explicit security list instead of OCI's permissive default.
# Stateful responses to the egress rules remain allowed; inbound SSH is handled
# only by the NSG rule scoped to var.admin_cidr.
resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.pilot.id
  display_name   = "${var.resource_prefix}-public"
  freeform_tags  = local.common_tags

  egress_security_rules {
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "6"
    stateless        = false
    description      = "HTTPS for updates and approved external APIs."

    tcp_options {
      destination_port_range {
        min = 443
        max = 443
      }
    }
  }

  egress_security_rules {
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "6"
    stateless        = false
    description      = "HTTP for package mirrors that do not support HTTPS."

    tcp_options {
      destination_port_range {
        min = 80
        max = 80
      }
    }
  }

  egress_security_rules {
    destination      = var.vcn_cidr
    destination_type = "CIDR_BLOCK"
    protocol         = "17"
    stateless        = false
    description      = "DNS to the VCN resolver."

    udp_options {
      destination_port_range {
        min = 53
        max = 53
      }
    }
  }

  egress_security_rules {
    destination      = var.vcn_cidr
    destination_type = "CIDR_BLOCK"
    protocol         = "6"
    stateless        = false
    description      = "TCP DNS fallback to the VCN resolver."

    tcp_options {
      destination_port_range {
        min = 53
        max = 53
      }
    }
  }
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.pilot.id
  cidr_block                 = var.public_subnet_cidr
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.public.id]
  display_name               = "${var.resource_prefix}-public"
  dns_label                  = "public"
  prohibit_public_ip_on_vnic = false
  freeform_tags              = local.common_tags
}

resource "oci_core_network_security_group" "api" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.pilot.id
  display_name   = "${var.resource_prefix}-api"
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group_security_rule" "http" {
  network_security_group_id = oci_core_network_security_group.api.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = "0.0.0.0/0"
  description               = "Public HTTP for the future TLS proxy only."

  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

resource "oci_core_network_security_group_security_rule" "https" {
  network_security_group_id = oci_core_network_security_group.api.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = "0.0.0.0/0"
  description               = "Public HTTPS for the future TLS proxy only."

  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "ssh_admin" {
  network_security_group_id = oci_core_network_security_group.api.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = var.admin_cidr
  description               = "Administrative SSH from the approved CIDR only."

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}
