# F48-02 — Sonda de quota com tokens e sem `AI_FAILED` (V17)

## Resultado

A sonda de admissão do `analyze_pending` reserva a estimativa de tokens de uma chamada ao
modelo primário (`probe_tokens`, teto de entrada + saída da tarefa `job_match`) em vez de 0.
Sem saldo, o item é adiado (`skipped_budget`): nenhuma chamada ao provedor, nenhuma linha
`match_analysis` `AI_FAILED`, nenhuma tentativa consumida.

## Contexto

Com `estimated_tokens = 0` a sonda passava com 169.522 de 170.000 tokens usados e a chamada
real falhava com `QUOTA_EXHAUSTED`, gravando `AI_FAILED` (2.008 linhas) e consumindo a
tentativa (limite 3/24 h). Ver `docs/48-spec-mais-vagas.md` §4.17.

## Escopo

- `src/opportunity_radar/worker.py`: `analyze_pending` lê `adapter.probe_tokens` (0 se o
  adaptador não declara) e o passa a `quota_guard.reserve`.
- `src/opportunity_radar/matching/groq.py`: `GroqAnalysisAdapter.probe_tokens`.
- Fora do escopo: a sonda de `suggest_fields_pending` continua com 0 (job desligado por padrão);
  ordenação por score e restrição de veredito da fila dependem de V04.

## Critérios de aceite

- [x] A sonda reserva a estimativa de tokens do modelo primário.
- [x] Sem saldo, o lote termina com `skipped_budget` e nenhuma linha `AI_FAILED`.
- [x] Nenhuma tentativa é consumida pelo defer (a avaliação continua na fila).

## Verificação

Testes em `tests/backend/matching/test_analysis_queue.py`
(`test_the_probe_reserves_the_model_estimate_and_defers_without_ai_failed_rows`: contador a
169.900 de 170.000, 0 chamadas, 0 `match_analysis` novos; `..._when_the_estimate_fits`: com saldo,
chama).

```
docker compose -p f48w1 -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q tests/backend/matching/test_analysis_queue.py
25 passed
```