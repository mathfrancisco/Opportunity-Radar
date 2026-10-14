# F53-12/13 — caminho Postgres da medição e relatório de retenção

Data: 2026-10-14 (UTC). Branch `fix/f53-12-13-db-paths`, base `origin/main` `1a42fb8`.
Commits: `16e3014` (correção), `6ff462e` (teste de retenção).

## Bug

`scripts/measure_host_resources.py::_postgres_connections` chamava
`connection.set_session(...)`, que existe no psycopg2 mas não no psycopg 3.3.5
fixado no projeto, e passava a URL do SQLAlchemy (esquema `postgresql+psycopg`)
direto a `psycopg.connect`, que só aceita o esquema `postgresql`. Os testes
unitários usavam um fake com `set_session`, então nunca pegaram o erro.

## Correção (`16e3014`)

- DSN normalizado por `postgres_dsn` (`opportunity_radar.platform.backup`), que
  só troca o esquema e preserva usuário, host, caminho e query params; nada é
  registrado em log.
- `connection.read_only = True` com `autocommit` no padrão (False): a leitura
  roda numa transação somente leitura que termina em `rollback()`; `close()`
  continua em `finally`. `connect_timeout` e `options` mantidos.
- Fake unitário restrito à superfície do psycopg 3 (`__slots__`, sem
  `set_session`).
- Teste de integração com Postgres real, parametrizado pelas duas formas de
  URL (`postgresql+psycopg` e `postgresql`), validando saída agregada
  (`state`/`count`), `read_only`, ausência de autocommit e conexão fechada.
  Guardado como os demais testes de banco (`RUN_DATABASE_INTEGRATION=1`,
  `DATABASE_INTEGRATION_ISOLATED=1`, banco `*_test`).

## Retenção F53-13 AC01 (`6ff462e`)

`test_report_counts_seeded_protections_without_writing` semeia avaliações
elegíveis e protegidas (análise, claim, candidatura, ponteiro atual, uma com
sobreposição de proteções, a mais recente e uma na fronteira da janela), chama
`retention_report.build_report` e verifica: `dry_run` verdadeiro no relatório e
na retenção; candidatas (+6), apagáveis (+1) e proteções por tipo (análise 2,
claim 2, candidatura 2, atual 1; soma 7 > 6 por sobreposição) como delta sobre
a linha de base do banco compartilhado; e contagens de avaliações, fatores,
análises, claims, candidaturas, ponteiros e totais das tabelas idênticas antes
e depois.

## Comandos

Banco descartável (rede + pgvector, `alembic upgrade head`, removidos ao final),
DSN omitido:

```sh
DATABASE_URL=<DSN> RUN_DATABASE_INTEGRATION=1 DATABASE_INTEGRATION_ISOLATED=1 \
  pytest -q -p no:cacheprovider -rA tests/backend/test_measure_host_resources.py \
  tests/backend/test_retention_report.py
```

### Prova do bug (script original `1a42fb8`, testes novos)

```text
>           connection.set_session(readonly=True, autocommit=False)
E           AttributeError: '_TrackedConnection' object has no attribute 'set_session'
2 failed, 2 deselected in 0.25s
```

(A variante com esquema `postgresql+psycopg` também falhou no original, na
interpretação do DSN por `psycopg.conninfo`.)

### Com a correção (`16e3014` + `6ff462e`)

```text
PASSED tests/backend/test_measure_host_resources.py::test_measurement_emits_only_aggregate_metrics_and_uses_stats_only
PASSED tests/backend/test_measure_host_resources.py::test_measurement_does_not_copy_environment_or_database_url
PASSED tests/backend/test_measure_host_resources.py::test_postgres_measurement_reads_aggregates_and_closes_connection[postgresql+psycopg]
PASSED tests/backend/test_measure_host_resources.py::test_postgres_measurement_reads_aggregates_and_closes_connection[postgresql]
PASSED tests/backend/test_retention_report.py::test_report_is_read_only_aggregate_and_counts_protected_references
PASSED tests/backend/test_retention_report.py::test_report_reads_the_isolated_database
PASSED tests/backend/test_retention_report.py::test_report_counts_seeded_protections_without_writing
7 passed in 1.21s
```

Junto de `tests/backend/operations/test_assessment_retention.py`: `25 passed in 12.33s`, sem skips.

### Espelho unitário completo (sem banco, `6ff462e`)

`ruff check .`: `All checks passed!`; `mypy`: `Success: no issues found in 143 source files`.

```text
9 failed, 1724 passed, 734 skipped, 4 warnings in 33.59s
```

As 9 falhas são as ambientais já conhecidas (`test_pacing_table` x3,
`test_auth::test_execute_source_uses_the_verified_owner_for_target_roles` x2,
`opportunities/test_service::test_merged_normalization_bumps_version_when_skill_changes`,
`test_tokenharbor_provider` x3), não relacionadas a esta mudança.

## Não comprovado

- Execução na VM (OCI) e contra Neon real: não executadas.
- Três janelas de medição (antes/pico/depois) em ambiente real: não executadas.
- Custos e quotas: não medidos.
- O teste de retenção prova o modo `dry_run` num Postgres local descartável, não
  o volume nem a duração em dados de produção.
