# F20-38 — orçamento por host compartilhado entre duas fontes reais — 2026-09-28

Evidência de execução real, pilha Docker Compose manual `f20manual` (código da PR, cópia
do banco real, `AI_ENABLED=false`, porta `127.0.0.1:8001`). A pilha real
`opportunity-radar` (janela de sete dias) não foi tocada nesta sessão.

## Contexto

`validacao-pendente.md` §5 registrava F20-38 como "sem par real no catálogo": o
mecanismo (`HostBudgetState`, `acquisition/scheduling.py`, chave de host em
`_PROVIDER_HOST_BY_SOURCE_TYPE`/`acquisition/service.py:88-98`) está implementado e
testado (fixtures), mas nunca fora observado com duas fontes reais e distintas do mesmo
provedor, ambas executando e contando contra a mesma linha de `host_budget_state`.

Esta mesma sessão resolveu F20-36 (Airbyte/Temporal/ClickHouse — ver
`ativacao-fontes-2026-09-28.md` atualizado) ativando três fontes reais `ashby` novas:
Airbyte, Temporal e ClickHouse. `_host_for_source_type("ashby")` mapeia todas para o
mesmo host físico, `api.ashbyhq.com` (`service.py:88-98`) — o par real que faltava.

## Par usado

| Fonte | Tipo | `board_identifier` | Host físico (`_host_for_source_type`) |
| --- | --- | --- | --- |
| Airbyte | ashby | `airbyte` | `api.ashbyhq.com` |
| Temporal | ashby | `temporal` | `api.ashbyhq.com` |

(ClickHouse, também `ashby`, ativada na mesma rodada, soma ao mesmo host — ver §3.)

## 1. Estado antes

```sql
select host, requests_used, requests_ceiling from acquisition.host_budget_state
where host = 'api.ashbyhq.com';
```

```
      host       | requests_used | requests_ceiling
-----------------+---------------+------------------
 api.ashbyhq.com |            19 |              200
```

(A janela — `window_start` 2026-09-28T21:01:23Z — já continha uso de outras fontes
`ashby` reais e pré-existentes no catálogo — Apollo GraphQL, LangChain, Oyster, Retell
AI, LlamaIndex, Plaid, Sentry, Linear — mais as três execuções `SUCCEEDED` de ativação de
Airbyte/Temporal/ClickHouse feitas minutos antes deste teste controlado, ver
`ativacao-fontes-2026-09-28.md`.)

## 2. Execução real — POST .../runs (nunca simulado)

```
POST /sources/{airbyte_id}/runs   {"max_items": 1}
→ 200 SUCCEEDED, http_requests=1

select host, requests_used from acquisition.host_budget_state where host='api.ashbyhq.com';
→ 20   (19 → 20, +1, atribuído à execução da Airbyte)

POST /sources/{temporal_id}/runs  {"max_items": 1}
→ 200 SUCCEEDED, http_requests=1

select host, requests_used from acquisition.host_budget_state where host='api.ashbyhq.com';
→ 21   (20 → 21, +1, atribuído à execução da Temporal — MESMA linha de host)
```

Duas fontes reais e distintas (tenants Ashby diferentes — `airbyte` e `temporal`, sem
relação entre as empresas), cada uma com sua própria `SourceDefinitionModel` e
`SourceRunModel`, cada execução aumentou o **mesmo** contador `requests_used` da
**mesma** linha `host_budget_state` (`host='api.ashbyhq.com'`) — não duas linhas
separadas. Isso é exatamente o comportamento que `source_host_key`/
`_host_for_source_type` foram desenhados para produzir (SPEC 39 §7,
`concurrency.py:59-79`, `service.py:88-98`): o orçamento é por *provedor físico*, não por
fonte, e por tenant nenhum dos dois teria disparado esse compartilhamento.

## 3. Terceira fonte no mesmo host (ClickHouse)

A rodada de ativação anterior desta sessão (`ativacao-fontes-2026-09-28.md`) já havia
corrido `POST .../runs` para Airbyte, Temporal e ClickHouse (`ashby`) em sequência,
19 → 20 → 21 → 22 antes deste teste controlado dedicado ter reiniciado a contagem em 19 —
ou seja, o mesmo efeito já tinha ocorrido três vezes sobre a mesma linha antes de eu
isolar o par de duas fontes em §2 para uma leitura antes/depois mais limpa.

## Conclusão

Confirmado com dados reais do banco, não fixture: duas (na prática, três) fontes `ashby`
reais e distintas, de tenants sem qualquer relação entre si, compartilham uma única
linha de orçamento por host (`api.ashbyhq.com`), e cada execução real de qualquer uma
delas consome do mesmo teto (`requests_ceiling=200` na janela observada). F20-38 fecha
como validado com par real.
