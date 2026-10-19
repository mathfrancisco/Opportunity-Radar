# R55: fechamento (2026-10-19)

Complementa `2026-10-19-r55-relatorio-final.md`. Medições sem DSN, sem tokens, sem identidade do dono e sem IPs além da regra de SSH.

## Deploys

| Deploy | Run | Imagens | Neon |
|---|---|---|---|
| #4 (19/10 ~01:50 UTC) | 39185714092 | api `3282f58e…`, worker `bbc8616f…`, proxy `efdfa25d…` | `20261017_0075` |
| #5 (19/10) | 39193063863 | api `3c389c6b…`, worker `b4ebe59b…`, proxy `d5e34b0e…` | `20261018_0076` (head única) |

O deploy #5 levou `main` em `bbf49da`: #119 (busca geral), #121 (drop do índice redundante de `match_factor`), #122 (`raw_item` enxuto atrás do apply) e #124 (descrição limpa com teto de 4000 caracteres).

## Busca geral

Decisão do dono: a coleta é geral; o perfil só filtra o que cada pessoa vê. Em produção: `COLLECTION_PREFILTER_ENABLED=false`, `OPPORTUNITY_OFF_TARGET_RETENTION_DAYS=0`, `COLLECTION_TARGET_AREA_FLOOR=0`. O código do pré-filtro e da retenção fora do alvo (B5) fica como opção desligada por padrão (decisão do dono, 19/10).

## Retenção de 5 dias

- Dry-run antes de ligar (fora do alvo = 0): 7 dias apagaria 96 oportunidades; 5 dias apagaria 1543 de 6832.
- Ligada em `/etc/opportunity-radar/pipeline.env` (backup `pipeline.env.bak-r55`): `OPPORTUNITY_RETENTION_APPLY=true`, `OPPORTUNITY_RETENTION_DAYS=5`, `OPPORTUNITY_OFF_TARGET_RETENTION_DAYS=0`. O `prepare_envs.py` local gera os mesmos valores.
- Primeiro apply: oportunidades de 6832 para 5097. A diferença para o dry-run vem das janelas entre as duas medições.
- A etapa `retention` roda uma vez por dia; nas demais janelas aparece como `skipped`.

## Trim das descrições

`scripts/trim_stored_descriptions.py` aplicado: 822 linhas, 5,73 M para 3,23 M caracteres. Termos que existiam só no trecho cortado deixam de ser encontrados pela busca; é uma limitação aceita.

## Regra de SSH

O IP de administração mudou. A regra da porta 22 no NSG `opportunity-radar-api` foi trocada para o novo `/32` pelo console, com OK do dono. Em 19/10 a variável `admin_cidr` do stack do Resource Manager foi alinhada ao mesmo valor (sem apply) e um job de Plan foi executado (plan-job-20261019105112, 13:53 UTC): `Succeeded`, "No changes. Your infrastructure matches the configuration." O NSG e o Terraform estão alinhados.

## Tamanho e consumo do Neon (19/10 ~12:30 UTC)

| Tabela | Total | Vivas | Mortas |
|---|---|---|---|
| opportunities.opportunity | 59 MB | 5166 | 899 |
| acquisition.raw_item | 33 MB | 9047 | 0 |
| matching.match_assessment | 21 MB | 4023 | 0 |
| matching.match_factor | 19 MB | 32184 | 0 |
| acquisition.raw_item_payload | 18 MB | 9432 | 0 |
| opportunities.source_occurrence | 9,0 MB | 6053 | 391 |

- `pg_database_size`: 189 MB (183 MB antes da retenção; o espaço apagado é reutilizado, não devolvido).
- `VACUUM FULL`: não executado. Há poucas tuplas mortas e o banco está bem abaixo da meta; reavaliar se passar de cerca de 300 MB.
- CU-h: `compute_time_seconds=11802` desde 16/10 14:05 UTC (cerca de 70 h) = 3,28 CU-h, projeção de cerca de **34 CU-h/mês** (meta < 80).
- Janelas de 19/10: todas com `exit_code=0`, exceto uma recusada por `claim_unavailable` (janela sobreposta a uma execução manual).

## Cards

| Card | Situação | Prova |
|---|---|---|
| E2 | feito, retenção ligada | apply 6832 para 5097; estabilidade do tamanho por vários dias: **sem prova** (um dia de dados) |
| E5 | feito | 34 CU-h/mês medidos em ~70 h; mês completo: **sem prova** |
| E6 | feito | 189 MB < 600 MB; tendência após vários dias: **sem prova**, remedir em ~22/10 |
| B5 | opção desligada | decisão do dono |
| Amarelos #115, #121, #124 | ver PRs de 19/10 | testes positivo e negativo em cada PR |

## Rollback

- Retenção: `OPPORTUNITY_RETENTION_APPLY=false` no `pipeline.env` (ou restaurar `pipeline.env.bak-r55`).
- `admin_cidr`: editar a variável do stack de volta e rodar um Plan.
