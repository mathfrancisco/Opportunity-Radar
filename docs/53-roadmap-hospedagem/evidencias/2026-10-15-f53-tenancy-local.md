# F53 — validação local de tenancy em 15/10

Validação focalizada executada em banco de teste isolado (`DB_test`), sem
acesso ao banco operacional ou a serviços externos.

## Resultado focalizado

- `test_auth.py`, `test_auth_tenancy_integration.py` e
  `test_opportunity_relevance_tenancy.py`: **46 passed, 2 warnings, 12.52 s**.
- Após corrigir o helper da fixture de upgrade, `test_upgrade_populated_integration.py`:
  **3 passed in 20.29 s**; revisão independente da fixture: **No issues**.
- Cauda não alcançada na primeira execução, `test_worker.py` e
  `test_worker_evaluate_batch_size.py`: **33 passed in 4.61 s**.
- Ruff final em seis arquivos Python: `All checks passed!` e
  `6 files already formatted`.
- Mypy: `Success: no issues found in 2 source files` (`backup.py` e
  `auth.py`), executado antes da edição somente da fixture de teste; não foi
  repetido após essa edição.
- Revisão independente somente de leitura: **No issues**.

As validações de banco foram executadas em imagem Docker já local, sem pull,
com checkout montado somente para leitura, rede Docker isolada, sem bytecode e
sem cache pytest. Para reproduzi-las, use `--pull=never`, volume read-only,
`PYTHONDONTWRITEBYTECODE=1` e `pytest -p no:cacheprovider`. As duas guardas de
integração são obrigatórias; configure `RUN_DATABASE_INTEGRATION=1`,
`DATABASE_INTEGRATION_ISOLATED=1` e `DATABASE_URL` apontando para um banco de
teste isolado cujo nome termine em `_test`. Nunca use o banco operacional nem
registre o DSN nesta evidência. Exemplo de forma, substituindo os placeholders
locais de checkout, rede Docker isolada e URL redigida:

```text
docker run --rm --pull=never --network <rede-docker-isolada> --mount type=bind,source=<checkout>,target=/app,readonly --workdir /app --env PYTHONPATH=/app/src --env PYTHONDONTWRITEBYTECODE=1 --env RUN_DATABASE_INTEGRATION=1 --env DATABASE_INTEGRATION_ISOLATED=1 --env DATABASE_URL=<redacted-url-para-banco_test> opportunity-radar-dev-api:latest pytest -q -p no:cacheprovider tests/backend/http/test_auth.py tests/backend/http/test_auth_tenancy_integration.py tests/backend/http/test_opportunity_relevance_tenancy.py
docker run --rm --pull=never --network <rede-docker-isolada> --mount type=bind,source=<checkout>,target=/app,readonly --workdir /app --env PYTHONPATH=/app/src --env PYTHONDONTWRITEBYTECODE=1 --env RUN_DATABASE_INTEGRATION=1 --env DATABASE_INTEGRATION_ISOLATED=1 --env DATABASE_URL=<redacted-url-para-banco_test> opportunity-radar-dev-api:latest pytest -q -p no:cacheprovider tests/backend/test_upgrade_populated_integration.py
docker run --rm --pull=never --network <rede-docker-isolada> --mount type=bind,source=<checkout>,target=/app,readonly --workdir /app --env PYTHONPATH=/app/src --env PYTHONDONTWRITEBYTECODE=1 --env RUN_DATABASE_INTEGRATION=1 --env DATABASE_INTEGRATION_ISOLATED=1 --env DATABASE_URL=<redacted-url-para-banco_test> opportunity-radar-dev-api:latest pytest -q -p no:cacheprovider tests/backend/test_worker.py tests/backend/test_worker_evaluate_batch_size.py
```

## Diagnóstico da suíte completa

A primeira execução completa terminou com exit 1, mas seu resumo não foi
preservado. Uma repetição diagnóstica com `--maxfail=1` capturou **1 failed,
2621 passed, 10 skipped, 15 warnings em 383.47 s**; a cauda não foi executada.
A falha foi
`tests/backend/test_upgrade_populated_integration.py::test_pre_phase_20_database_upgrades_to_head_without_losing_history`:
o helper prepara um banco scratch pré-Phase 20 sem o backfill
`OWNER_SUB_BACKFILL` exigido pela migração 0069. Após a correção, o módulo de
upgrade passou nos três testes; os dois módulos da cauda também passaram, mas
não houve nova execução completa. Não há evidência de suíte completa green.

## Execução completa em `ba27db0` — inválida como aceite

Em `ba27db0edeac32fcdf64bcad1a1ad8fdd82b412a`, foi feita **uma única**
execução de `pytest -q -p no:cacheprovider tests/backend` em imagem local
`f53-tenancy-api:latest` (`--pull=never`), com checkout montado como somente
leitura e as duas guardas obrigatórias ativadas. O único banco alcançável era o
contêiner Docker efêmero `opportunity_radar_validation_test`; os contêineres
preexistentes que continham `opportunity_radar` foram inspecionados e não foram
usados. A execução terminou em exit 1 após **708.11 s**:

```text
492 failed, 1990 passed, 9 skipped, 4 warnings, 187 errors
```

Esse resultado não é evidência de regressão nem de aceite da suíte completa.
O banco efêmero foi criado diretamente e não recebeu `alembic upgrade head`,
etapa que o pipeline executa antes dos testes. Ao final, `alembic_version` não
existia e havia zero tabelas no schema público (`missing|0`). A primeira
stacktrace visível foi um erro de teardown SQLAlchemy em
`test_the_pass_reaches_every_eligible_source_past_the_first_hundred`, mas a
saída total tinha 7.3 MB e foi truncada pelo terminal. Não houve repetição. O
resumo durável e o comando exato foram salvos localmente em
`.tmp/f53-validation/f53-tenancy-full-20261015-ba27db0-summary.log`.

## Execução completa preparada — aceite técnico local

Em seguida, o banco efêmero foi recriado do zero com credenciais sintéticas e
nome terminado em `_test`. Antes de qualquer teste, `alembic upgrade head`
chegou a `20261008_0069`. A inspeção posterior confirmou as tabelas de todos
os schemas de aplicação: `acquisition=11`, `company_radar=8`, `crm=2`,
`dashboard=1`, `matching=5`, `opportunities=11`, `platform=6`, `profile=7` e
`public=1` (controle de Alembic).

Com as duas guardas de integração ativas e o checkout montado somente para
leitura, uma única execução nomeada de `pytest -q -p no:cacheprovider
tests/backend` terminou com exit 0:

```text
2662 passed, 10 skipped, 15 warnings in 620.01s (0:10:20)
```

Antes dela, o recorte de tenancy, preflight de imagens e unidades systemd
terminou em **31 passed, 1 skipped em 18.63 s**. Ruff nos cinco arquivos
Python modificados retornou `All checks passed!`; mypy em
`src/opportunity_radar/matching/repository.py`, com cache temporário fora do
checkout somente leitura, retornou `Success: no issues found in 1 source
file`.

O log sanitizado dessa execução está em
`.tmp/f53-validation/full-backend-clean-2026-10-15.log`; os registros da
migração e da inspeção de schema estão em
`.tmp/f53-validation/alembic-upgrade-clean-2026-10-15.log` e
`.tmp/f53-validation/database-schema-clean-2026-10-15.log`.

Três tentativas concorrentes anteriores no mesmo banco foram interrompidas e
são explicitamente inválidas como evidência, pois compartilhavam o `_test`.
Seus logs parciais foram preservados como
`.tmp/f53-validation/invalid-concurrent-*.log`; eles não entram no resultado
acima nem devem ser usados para aceitar ou diagnosticar esta alteração.

## Estado do gate

Em 2026-10-16 UTC, a revisão independente aceitou tecnicamente este gate: o
Package 3 é ancestral, os oito testes HTTP RS256 com dois owners passaram, a
migração 0069 foi aplicada ao banco isolado e a suíte completa preparada
terminou green. Esta evidência, portanto, satisfaz o pré-requisito técnico para
`TENANCY_OWNER_API_READY` no workflow de publicação.

O aceite técnico não é aceite operacional. Migração contra um banco alcançável
pela API antiga, publicação, deploy e cutover continuam pendentes de seus
procedimentos e aprovações próprios. Ver o [gate de tenancy](../../superpowers/specs/2026-10-08-owner-tenancy-release-gate.md).
