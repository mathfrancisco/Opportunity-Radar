# CARD F48-05 — Compose repassa as variáveis e some com as mortas (V18)

- **Status:** Implementado (2026-09-29).
- **Spec:** [`../48-spec-mais-vagas.md`](../48-spec-mais-vagas.md) §4.18, §5.

## Resultado

- `compose.yaml` (`x-app-environment`, herdado pelo worker) passa `WORKER_SUGGEST_ENABLED`
  (`false`), `WORKER_SUGGEST_BATCH_SIZE` (`20`), `WORKER_ANALYZE_AGING_SAMPLE_RATIO`
  (`0.10`), `AI_INTERACTIVE_RESERVE_REQUESTS` (`100`), `AI_CALL_RECORD_RETENTION_DAYS`
  (`30`) e `AI_REASONING_EFFORT_JOB_MATCH/CLASSIFICATION/EXTRACTION` (vazio = usa
  `AI_REASONING_EFFORT`), todos com o padrão de `platform/config.py` `Settings`.
- `WORKER_CONCURRENCY` e `ANALYSIS_CONCURRENCY` removidas de `compose.yaml` e
  `.env.example` (não são lidas em `src/` nem em `scripts/`).
- `.env.example` ganha `WORKER_SUGGEST_ENABLED` e `WORKER_SUGGEST_BATCH_SIZE`.
- Passo de CI `Verify the kill switches reach the worker` sobe o worker com
  `WORKER_SUGGEST_ENABLED=true` e passa a exigir `suggest_fields_pending: True` no log
  `worker jobs configured` (os demais continuam `False`).

## Contexto

O worker herda só o bloco `x-app-environment`; variável ausente ali não pode ser operada sem
editar código. O doc 48 §4.18 listou as faltantes e as duas mortas.

## Escopo

`compose.yaml`, `.env.example`, `.github/workflows/pipeline.yml`.

## Critérios de aceite

- [x] As variáveis listadas chegam ao worker com o padrão do `Settings` (saída de
  `docker compose config` abaixo).
- [x] `WORKER_CONCURRENCY` e `ANALYSIS_CONCURRENCY` removidas (`docker compose config` sem
  ocorrências; nenhum outro arquivo do código as referencia).
- [x] Passo do CI cobre `WORKER_SUGGEST_ENABLED=true` e confere o log de partida (o passo
  roda só no GitHub Actions; não foi executado localmente).

## Verificação

```
docker compose -p f48w2 -f compose.yaml config | grep -E "SUGGEST|AGING|RESERVE|RETENTION_DAYS|EFFORT_JOB"
  AI_CALL_RECORD_RETENTION_DAYS: "30"
  AI_INTERACTIVE_RESERVE_REQUESTS: "100"
  AI_REASONING_EFFORT_JOB_CLASSIFICATION: ""
  AI_REASONING_EFFORT_JOB_EXTRACTION: ""
  AI_REASONING_EFFORT_JOB_MATCH: ""
  WORKER_ANALYZE_AGING_SAMPLE_RATIO: "0.10"
  WORKER_SUGGEST_BATCH_SIZE: "20"
  WORKER_SUGGEST_ENABLED: "false"
docker compose -p f48w2 -f compose.yaml -f compose.dev.yaml config | grep -c CONCURRENCY
0
RUN_DATABASE_INTEGRATION=1 pytest -q -x tests/backend  ->  1181 passed, 11 skipped
```
