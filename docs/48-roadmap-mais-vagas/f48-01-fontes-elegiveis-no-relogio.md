# F48-01 — Toda fonte elegível entra no relógio (V01)

## Resultado

`collect_enabled_sources` usa o novo `AcquisitionRepository.list_collectable_sources()`
(exposto em `AcquisitionService`): `enabled AND source_type <> 'manual'`, sem limite. Ordem:
fonte nunca coletada primeiro (`max(source_run.started_at)` nulo), depois prioridade da empresa
(`high`, `normal` ou sem empresa, `low`, `blocked`), depois nome. `list_sources(offset, limit)`
da API paginada não mudou.

## Contexto

O worker lia `list_sources(offset=0, limit=100)` (ordenado por nome) e filtrava depois, então as
fontes elegíveis além da posição 100 nunca rodavam (`docs/48-spec-mais-vagas.md` §4.1).

## Escopo

- `src/opportunity_radar/acquisition/repository.py`, `acquisition/service.py`, `worker.py`.
- O filtro `enabled`/`manual` saiu do laço do worker (agora está na consulta).
- Ordem pedida no brief (nunca coletada, prioridade, nome); a spec §4.1 cita prioridade antes.

## Critérios de aceite

- [x] `collect_enabled_sources` considera `enabled AND source_type <> 'manual'` sem limite.
- [x] Ordem: fonte nunca coletada primeiro, depois prioridade e nome.
- [x] `list_sources` paginado da API continua igual.

## Verificação

Testes em `tests/backend/acquisition/test_collectable_sources.py` (arquivo novo: o
`test_collection_job.py` está inteiro em `skip` por F10-03, então um teste lá não rodaria):
150 fontes elegíveis mais uma desabilitada e uma `manual` no meio, todas as 150 avaliadas e as
duas ignoradas; consulta sem limite e com nunca-coletadas primeiro.

```
docker compose -p f48w1 -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q
1189 passed, 11 skipped
```

Verificação real pendente: depois do deploy, `eligible_never_run` cai de 38 para 0.