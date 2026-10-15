# OCI Always Free root — F53-03/F53-04

This root is source for one OCI Resource Manager stack. It creates only a VCN,
public subnet, Internet Gateway, route table, NSG, one A1 ARM instance by
default (or the explicit temporary Free Trial option below), and a private
Object Storage bucket. It deliberately has no backend block: Resource Manager
owns remote state and locking after the manual bootstrap.

It does **not** create a NAT Gateway, Load Balancer, database, Redis,
Kubernetes service, extra public IP, DNS record, account, principal, API key,
or secrets. Terraform apply is not authorized by this source or this runbook.

## Always Free guardrails

- The only allowed shape is `VM.Standard.A1.Flex`, capped at 2 OCPUs and 12 GB.
- Boot volume is fixed at 50 GB.
- The bucket is `NoPublicAccess`. `20 GB` and `50,000` requests/month are
  explicit operational limits for F53-14, not quotas enforced by OCI.
- Ingress is TCP 80/443 from the Internet and TCP 22 only from `admin_cidr`.
  No rule declares 5432, 6379, container ports, or a world-open SSH CIDR.
- OCI availability and free-tier eligibility are external gates; a successful
  validate or plan does not prove either.

## Temporary Free Trial recovery option

The default remains A1 Always Free. Only when `enable_free_trial = true`, this
root permits `VM.Standard.E4.Flex` or `VM.Standard.E5.Flex` at exactly 1 OCPU
and 8 GB, using the operator-selected Ubuntu 24.04 x86 image in `trial_image_id`.
Choose only a shape currently offered by the account. Do not upgrade the account
to Pay As You Go. A Free Trial balance or eligibility is temporary and must be
checked in OCI before a separately authorized Apply; this configuration does
not guarantee credits, host capacity, or zero cost. The 50 GB boot-volume limit,
private bucket, network, ingress rules, and SSH key input remain the same.

Returning from x86 E4/E5 to A1 ARM changes the instance image and shape and is
expected to recreate the VM. Review the Plan, preserve any required data, and
redeploy the application; do not treat this as an in-place architecture switch.

## Manual bootstrap and Plan

1. In OCI Console, create the approved pilot compartment, group/principal and
   Resource Manager stack. Do not automate bootstrap identity with this root.
2. Review the five least-privilege policy statements in `iam.tf`, then replace
   their placeholders with the approved group and compartment names in OCI
   Console. The `resource_manager_iam_policy_template` output repeats those
   statements for review; it does not create or apply IAM policies.
   Do not replace them with tenancy-wide or `manage all-resources` access.
3. Confirm A1 capacity and ARM image for the default path. For the temporary
   option, explicitly enable Free Trial, select an Ubuntu 24.04 x86 image, and
   confirm trial credits, shape availability, Resource Manager pricing/support
   and stack locking in the selected home region.
4. Copy `terraform.tfvars.example` **outside Git**, use only public values, and
   provide it as masked Resource Manager stack variables. Keep actual public
   SSH keys private to the stack configuration if policy requires it; never
   provide a private key.
5. From this directory, source-only validation is safe and does not create
   infrastructure:

   ```powershell
   terraform fmt -check -recursive
   terraform init -backend=false
   terraform validate
   ```

6. Create one Resource Manager **Plan** job. Review that compute matches the
   selected mode (default A1 `2/12`; temporary E4/E5 `1/8`), boot is `50`, its
   bucket is private, and SSH is not `0.0.0.0/0`. Archive only its redacted
   job ID and summary in `docs/53-roadmap-hospedagem/evidencias/`.
7. Run **Apply** only after a distinct owner authorization for the reviewed
   plan. If capacity is unavailable, trial credits are insufficient, or a
   charge outside the approved Free Trial appears, cancel the job; do not
   upgrade the account to Pay As You Go or substitute another shape or region.

## Validação estática

O workflow `Infra / Terraform static validation` executa formatação, `init`
sem backend com lockfile somente-leitura e `validate` no container
`hashicorp/terraform:1.9.8`. Ele não usa credenciais OCI nem executa `plan` ou
`apply`.

Para a mesma verificação local, a partir da raiz do repositório:

```sh
docker run --rm -v "$(pwd -W)/infra/terraform/oci:/work:ro" -w /work -e TF_DATA_DIR=/tmp/tf-data --entrypoint sh hashicorp/terraform:1.9.8 -ec 'terraform fmt -check -recursive && terraform init -backend=false -input=false -lockfile=readonly && terraform validate -no-color'
```

## State, lock and rollback

Resource Manager is the intended state/lock owner. Verify a concurrent Plan or
Apply cannot write the stack simultaneously and verify controlled cancellation
leaves recoverable state before declaring F53-03 accepted. Never delete state
to clear a lock.

For rollback after an approved pilot apply, create a Resource Manager destroy
plan, review exact targets, verify backup/ownership requirements, then obtain
the owner's separate deletion authorization. This repository provides no
automatic destroy command.
