# Bootstrap IAM remains manual: this root must not create or broaden its own
# tenancy access. Substitute only approved names in OCI Console after review.
locals {
  required_iam_policy_statements = [
    "Allow group <GRUPO_INFRA_PILOTO> to manage virtual-network-family in compartment <COMPARTMENT_PILOTO>",
    "Allow group <GRUPO_INFRA_PILOTO> to manage instance-family in compartment <COMPARTMENT_PILOTO>",
    "Allow group <GRUPO_INFRA_PILOTO> to manage volume-family in compartment <COMPARTMENT_PILOTO>",
    "Allow group <GRUPO_INFRA_PILOTO> to manage object-family in compartment <COMPARTMENT_PILOTO>",
    "Allow group <GRUPO_INFRA_PILOTO> to manage resource-manager-family in compartment <COMPARTMENT_PILOTO>",
  ]
}
