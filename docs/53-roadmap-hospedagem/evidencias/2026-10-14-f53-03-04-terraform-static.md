# F53-03/F53-04 — validação estática Terraform OCI

Data: 2026-10-14 (UTC). Checkout baseado em `origin/main` `1a42fb8`.

## Validação local

A restrição do root é `>= 1.5.0, < 2.0.0`; por isso a imagem oficial
`hashicorp/terraform:1.9.8` é compatível. Sem backend, credenciais, `plan` ou
`apply`, foram executados no Git Bash com `MSYS_NO_PATHCONV=1`:

```sh
docker run --rm -v "$(pwd -W)/infra/terraform/oci:/work" -w /work -e TF_DATA_DIR=/tmp/tf-data hashicorp/terraform:1.9.8 init -backend=false -input=false
docker run --rm -v "$(pwd -W)/infra/terraform/oci:/work" -w /work -e TF_DATA_DIR=/tmp/tf-data hashicorp/terraform:1.9.8 providers lock -platform=linux_amd64 -platform=linux_arm64
docker run --rm -v "$(pwd -W)/infra/terraform/oci:/work:ro" -w /work -e TF_DATA_DIR=/tmp/tf-data --entrypoint sh hashicorp/terraform:1.9.8 -ec 'terraform fmt -check -recursive && terraform init -backend=false -input=false -lockfile=readonly && terraform validate -no-color'
```

Saída literal do `init`:

```text
Initializing provider plugins...
- Finding oracle/oci versions matching "7.27.0"...
- Installing oracle/oci v7.27.0...
- Installed oracle/oci v7.27.0 (signed by a HashiCorp partner, key ID 1533A49284137CEB)

Terraform has created a lock file .terraform.lock.hcl to record the provider
selections it made above. Include this file in your version control repository
so that Terraform can guarantee to make the same selections by default when
you run "terraform init" in the future.

Terraform has been successfully initialized!
```

Saída literal de `terraform providers lock`:

```text
- Fetching oracle/oci 7.27.0 for linux_amd64...
- Retrieved oracle/oci 7.27.0 for linux_amd64 (signed by a HashiCorp partner, key ID 1533A49284137CEB)
- Fetching oracle/oci 7.27.0 for linux_arm64...
- Retrieved oracle/oci 7.27.0 for linux_arm64 (signed by a HashiCorp partner, key ID 1533A49284137CEB)
- Obtained oracle/oci checksums for linux_arm64; Additional checksums for this platform are now tracked in the lock file
- Obtained oracle/oci checksums for linux_amd64; All checksums for this platform were already tracked in the lock file

Success! Terraform has updated the lock file.
```

Saída literal da validação estática:

```text
Initializing provider plugins...
- Reusing previous version of oracle/oci from the dependency lock file
- Installing oracle/oci v7.27.0...
- Installed oracle/oci v7.27.0 (signed by a HashiCorp partner, key ID 1533A49284137CEB)

Terraform has been successfully initialized!

Success! The configuration is valid.
```

## Regressão do repositório

```sh
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/src:ro" -v or-pip-cache:/root/.cache/pip python:3.12-slim sh -c "cp -r /src /w && cd /w && pip install -q -r requirements-dev.txt 2>/dev/null && pip install -q --no-deps . 2>/dev/null && ruff check . && mypy && pytest -q -p no:cacheprovider 2>&1 | tail -14"
```

Saída literal:

```text
All checks passed!
Success: no issues found in 143 source files
    _raise_acquisition_error(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/backend/acquisition/test_pacing_table.py::test_pacing_table_ceiling_matches_the_code
FAILED tests/backend/acquisition/test_pacing_table.py::test_ceiling_is_not_below_the_documented_measured_peak
FAILED tests/backend/acquisition/test_pacing_table.py::test_service_default_ceilings_match_settings_for_typed_ceilings
FAILED tests/backend/http/test_auth.py::test_execute_source_uses_the_verified_owner_for_target_roles[owner-a-synthetic]
FAILED tests/backend/http/test_auth.py::test_execute_source_uses_the_verified_owner_for_target_roles[owner-b-synthetic]
FAILED tests/backend/opportunities/test_service.py::test_merged_normalization_bumps_version_when_skill_changes
FAILED tests/backend/platform/ai/test_tokenharbor_provider.py::test_without_a_key_nothing_changes
FAILED tests/backend/platform/ai/test_tokenharbor_provider.py::test_with_a_key_the_free_models_close_every_chain
FAILED tests/backend/platform/ai/test_tokenharbor_provider.py::test_router_falls_to_token_harbor_when_groq_is_rate_limited_and_telemetry_names_it
9 failed, 1724 passed, 731 skipped, 4 warnings in 32.86s
```

As nove falhas acima são as falhas ambientais previamente aceitas; nenhuma
outra falha foi observada.

## Ainda não comprovado

- IAM no console;
- state/lock no Resource Manager;
- `plan`;
- `apply`;
- capacidade A1;
- SSH;
- custos não medidos.
