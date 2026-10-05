# CARD F48-07 — Alarme de buraco de coleta e bytes por run (V16)

- **Status:** Implementado (2026-09-29).
- **Spec:** [`../48-spec-mais-vagas.md`](../48-spec-mais-vagas.md) §4.16, §5.

## Resultado

- `operations/collection_alarm.py`: `collection_gap_report(session, now=...)`. Uma fonte
  habilitada, não `manual` e com `schedule` alarma quando a última run `SCHEDULED` é mais
  velha que 2x a cadência (maior intervalo entre disparos do cron; sem run, conta desde a
  criação da fonte). O alarme global compara a última run agendada de qualquer fonte com 2x
  a cadência mais rápida.
- `doctor`: check `collection gap` (`WARN` com as piores fontes e as últimas passadas de
  coleta). `GET /source-health` devolve `collection_gap` e `collection_overdue` por fonte.
- `source_run.bytes_received` (tamanho serializado dos payloads recebidos) e
  `newest_item_age_seconds` (idade do item datado mais novo ao fim da run), gravados em
  `AcquisitionService.execute` e expostos no `/source-health`. Nulos em runs anteriores.
- `platform.worker_pass_history`: uma linha por passada de cada job do worker (início, fim,
  duração, sucesso), podada em 200 por job; o job de coleta anota `due_sources` (fontes que
  chegaram à execução ou falharam nela) e o resumo da passada. Fora do backup, como
  `worker_job_state`.
- Migração `20260929_0055` (revisa `20260929_0054`).

## Contexto

V16: em 2026-09-29 houve um buraco de ~9 h sem coleta e nada avisou. `worker_job_state` só
guarda a última passada, sem histórico nem contagem de fontes DUE.

## Escopo

`operations/` (`collection_alarm.py`, `models.py`, `service.py`), `acquisition/domain.py`
(telemetria), `acquisition/models.py`, `acquisition/service.py`, migração, `scripts/doctor.py`,
`dashboard/queries.py`, `presentation/http/dashboard.py`, `worker.py` (uma chamada
`annotate_pass`), `platform/backup.py` (exclusão documentada).

## Critérios de aceite

- [x] `doctor` e `/source-health` avisam quando nenhuma run agendada ocorreu em > 2x a
  cadência, global e por fonte (`tests/backend/operations/test_collection_alarm.py`, relógio
  controlado, incluindo o limite exato de 2x; `tests/backend/test_funnel_http_integration.py`).
- [x] `source_run.bytes_received` e `newest_item_age_seconds` gravados
  (`tests/backend/acquisition/test_run_telemetry.py`).
- [x] Histórico curto de passadas com duração e fontes DUE (tabela `worker_pass_history`,
  em vez de colunas em `worker_job_state`, que guarda uma linha por job).
- [x] Migração ida e volta (`tests/backend/test_collection_alarm_migration.py`: upgrade head,
  downgrade `20260929_0054`, upgrade head num banco descartável; o passo do CI
  `alembic upgrade/downgrade base/upgrade` também cobre).

## Verificação

```
docker compose -p f48w3 -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q
1210 passed, 11 skipped, 13 warnings in 136.64s (0:02:16)
ruff check src scripts tests/backend -> All checks passed
```
