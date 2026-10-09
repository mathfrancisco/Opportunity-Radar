# OCI Always Free root — F53-03/F53-04

This root is source for one OCI Resource Manager stack. It creates only a VCN,
public subnet, Internet Gateway, route table, NSG, one A1 ARM instance and a
private Object Storage bucket. It deliberately has no backend block: Resource
Manager owns remote state and locking after the manual bootstrap.

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

## Manual bootstrap and Plan

1. In OCI Console, create the approved pilot compartment, group/principal and
   Resource Manager stack. Do not automate bootstrap identity with this root.
2. Apply the five least-privilege policy templates exposed by
   `resource_manager_iam_policy_template` after replacing both placeholders.
   Do not replace them with tenancy-wide or `manage all-resources` access.
3. Confirm A1 capacity, ARM image, Resource Manager pricing/support and stack
   locking in the selected home region.
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

6. Create one Resource Manager **Plan** job. Review that its sole compute is
   A1, shape `2/12`, boot `50`, its bucket is private, and SSH is not
   `0.0.0.0/0`. Archive only its redacted job ID and summary in
   `docs/53-roadmap-hospedagem/evidencias/`.
7. Run **Apply** only after a distinct owner authorization for the reviewed
   plan. If capacity is unavailable or a paid resource appears, cancel the job;
   do not substitute a paid shape or region.

## State, lock and rollback

Resource Manager is the intended state/lock owner. Verify a concurrent Plan or
Apply cannot write the stack simultaneously and verify controlled cancellation
leaves recoverable state before declaring F53-03 accepted. Never delete state
to clear a lock.

For rollback after an approved pilot apply, create a Resource Manager destroy
plan, review exact targets, verify backup/ownership requirements, then obtain
the owner's separate deletion authorization. This repository provides no
automatic destroy command.
