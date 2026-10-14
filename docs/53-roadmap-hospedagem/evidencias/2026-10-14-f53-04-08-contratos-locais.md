# F53-04 e F53-08 — contratos locais

Data: 2026-10-14 (UTC), base `origin/main` `adc9830`. Isto é validação local e
estática: não houve `terraform plan/apply`, SSH, Pages nem sessão Clerk real.

## F53-04 — contrato estático do Terraform OCI

`tests/backend/test_terraform_oci_contract.py` lê `infra/terraform/oci/*.tf`
como texto e afirma: shape `VM.Standard.A1.Flex`, OCPUs <= 2, memória <= 12 GB,
boot volume 50 GB, ingress público somente TCP 80/443 mais SSH (22) limitado a
`var.admin_cidr`, nenhum ingress 5432/6379, nenhum bloco `backend`, nenhum NAT,
load balancer ou recurso de banco. Os arquivos `.tf` não foram alterados.

Comando (imagem `python:3.12-slim`, cópia do checkout):

```sh
pytest -q -p no:cacheprovider tests/backend/test_terraform_oci_contract.py
```

Saída literal:

```text
5 passed in 0.06s
```

### Prova de mutação (não commitada)

Cada mutação foi aplicada a uma cópia temporária de `infra/terraform/oci`
(`OCI_TF_DIR` aponta o teste para a cópia). Linhas de falha literais:

```text
shape A1.Flex -> E4.Flex      FAILED ...::test_instance_shape_is_a1_flex_within_always_free_limits
default shape_ocpus 2 -> 4    FAILED ...::test_instance_shape_is_a1_flex_within_always_free_limits
default memória 12 -> 24      FAILED ...::test_instance_shape_is_a1_flex_within_always_free_limits
boot volume 50 -> 100         FAILED ...::test_boot_volume_is_fixed_at_50_gb
SSH source -> "0.0.0.0/0"     FAILED ...::test_public_ingress_is_only_web_ports_and_admin_scoped_ssh
ingress 5432 extra            FAILED ...::test_public_ingress_is_only_web_ports_and_admin_scoped_ssh
                              FAILED ...::test_no_other_ingress_path_or_database_ports_are_opened
                              E  assert not <re.Match object; span=(286, 290), match='5432'>
bloco backend "s3"            E  assert not <re.Match object; span=(12, 23), match='  backend "'>
oci_core_nat_gateway          E  assert not ['oci_core_nat_gateway']
oci_database_autonomous_...   E  assert not ['oci_database_autonomous_database']
```

Cada execução mutada terminou com falhas (`1 failed, 4 passed`; a mutação de
5432 com `2 failed, 3 passed`).

## F53-08 — guardas de rota do frontend

Em `apps/web`: `npm ci` concluiu (rede disponível), sem commitar `node_modules`.

```text
npx vitest run src/app/RouteGuards.test.tsx
 Test Files  1 passed (1)
      Tests  7 passed (7)

npm test -- --run
 Test Files  46 passed (46)
      Tests  377 passed (377)
```

## Limites

Nada aqui prova plan/apply, exposição real de portas, sessão em Pages/domínio
ou rollback. Esses itens continuam pendentes de execução externa.
