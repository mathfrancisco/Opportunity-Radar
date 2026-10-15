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

## Estado do gate

Esta evidência não aceita nem libera `TENANCY_OWNER_API_READY`. O gate continua
dependendo do Package 3 integrado, dos testes de autorização com dois usuários
e da revisão independente aceita. Os resultados focalizados e de reparo não
substituem uma execução completa do backend após a correção. Não autoriza
migração em banco alcançável pela API antiga, publicação, deploy ou cutover. Ver
o [gate de tenancy](../../superpowers/specs/2026-10-08-owner-tenancy-release-gate.md).
