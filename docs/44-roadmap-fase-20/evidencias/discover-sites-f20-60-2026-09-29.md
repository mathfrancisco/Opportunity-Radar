# discover_sites.py sobre as 13 empresas sem ATS do F20-60 (2026-09-29)

Pilha: apenas `f20manual` (`f20manual-postgres-1`, `f20manual-api-1`). Pilha real
`opportunity-radar` não tocada.

## Resultado: não executado — as 13 empresas estão sob o bloqueio de 30 dias

`scripts/discover_sites.py` não aceita filtro por empresa (só `--limit`, `--dry-run`,
`--concurrency`, `--progress-file`, `--min-interval-seconds`); ele varre
`companies.discovery.eligible_companies`, que exclui qualquer empresa com um
`discovery_attempt` nos últimos 30 dias. As 13 foram sondadas por `discover_ats.py` em
2026-09-28 (~22:27Z), então continuam fora até 2026-10-28. Nenhuma execução de
`discover_sites.py` (nem `--dry-run`) foi feita: não há como mirar só essas 13, e rodar
sobre o restante do catálogo elegível estaria fora do pedido. Nenhuma requisição HTTP a
site de empresa foi feita. Nenhum dado foi escrito.

Ordem correta preservada: `discover_sites.py` deve rodar ANTES de `discover_ats.py`, e só
em lote ainda não sondado no ciclo de 30 dias. Para estas 13, o portão só reabre em
2026-10-28.

## Por empresa

Consulta somente-leitura em `company_radar.discovery_attempt` (f20manual). Todas: 1
tentativa, `ats_found` vazio.

| Empresa | Última tentativa (UTC) | HTTP | Bloqueio | Desbloqueia | Site encontrado | Próximo passo |
|---|---|---|---|---|---|---|
| CloudDevs | 2026-09-28 22:27:29 | sem resposta | travada | 2026-10-28 | não rodou | backlog; rerodar `discover_sites` após 2026-10-28 (antes de `discover_ats`) |
| BossaBox | 2026-09-28 22:27:32 | 200 | travada | 2026-10-28 | não rodou | idem |
| IBM | 2026-09-28 22:27:32 | 200 | travada | 2026-10-28 | não rodou | idem |
| Crossover | 2026-09-28 22:27:35 | 200 | travada | 2026-10-28 | não rodou | idem (fonte na lista de exclusões desta rodada; nada tocado) |
| Encora | 2026-09-28 22:27:35 | 200 | travada | 2026-10-28 | não rodou | idem |
| BEON.tech | 2026-09-28 22:27:36 | 200 | travada | 2026-10-28 | não rodou | idem |
| Pipefy | 2026-09-28 22:27:38 | sem resposta | travada | 2026-10-28 | não rodou | idem; conferir URL de carreiras |
| Serasa Experian | 2026-09-28 22:27:38 | 200 | travada | 2026-10-28 | não rodou | idem |
| VanHack | 2026-09-28 22:27:39 | sem resposta | travada | 2026-10-28 | não rodou | idem; conferir URL de carreiras |
| Softtek | 2026-09-28 22:27:40 | 200 | travada | 2026-10-28 | não rodou | idem |
| Scopic | 2026-09-28 22:27:41 | 200 | travada | 2026-10-28 | não rodou | idem |
| NAVA | 2026-09-28 22:27:42 | 200 | travada | 2026-10-28 | não rodou | idem |
| Wipro | 2026-09-28 22:27:45 | 200 | travada | 2026-10-28 | não rodou | idem |

## Comandos usados

- `docker exec f20manual-api-1 python /app/scripts/discover_sites.py --help`
  (`MSYS_NO_PATHCONV=1`).
- `docker exec f20manual-postgres-1 psql -U opportunity_radar -d opportunity_radar -c
  "select ... from company_radar.company c left join company_radar.discovery_attempt a ..."`
  (somente `SELECT`).

## Tavily

0 créditos gastos.

## Alternativa (não adotada)

Adiantar sem esperar o bloqueio exigiria apagar/alterar `discovery_attempt` ou alterar o
script para aceitar filtro por empresa — ambos fora do escopo e contrários à proteção de
gentileza (SPEC 43).
