# R55: relatório final (2026-10-19)

Estado: `main` em `5bb8e08` (#116). Produção (VM Oracle) com as imagens do run 39185714092: api `3282f58e…`, worker `bbc8616f…`, proxy `efdfa25d…`. Neon `production` em `20261017_0075`. Medições sem DSN, sem tokens e sem identidade do dono.

## Deploy #4 (2026-10-19 ~01:50 UTC)

- Migrações `0073 -> 0074 -> 0075` aplicadas com `migrate.env`. O R56 já tinha aplicado a 0073. `migrate.env` foi removido depois (`migrate_env_absent`).
- api `healthy`, proxy `running`, timer horário ativo.
- Janela manual 01:52: `outcome=success`, 72 s, 0 falhas. Uma fonte vencida: 268 vistas, 22 gravadas, 103 fora dos 7 dias e 143 barradas pelo pré-filtro de área/país (B5).

## Tamanho do banco

| Momento | `pg_database_size` | Contexto |
|---|---|---|
| 16/10 (baseline) | 26,0 MB | 100 oportunidades |
| 17/10 manhã | 103,4 MB | lote 1 de A5, 1389 greenhouse sem data |
| 17/10 após limpeza | 107,5 MB | 1113 obsoletas apagadas; espaço não devolvido (sem `VACUUM FULL`) |
| 17/10 15:37 | 139,1 MB | lotes 2 a 4 |
| 18/10 23:36 | 181 MB | 429 fontes ligadas (427 após desligar 2 workday), backlog drenado |
| 19/10 01:55 | 183 MB | após o deploy #4; 6832 oportunidades, 12375 raw items |

Crescimento observado: cerca de 40 MB/dia sem retenção aplicada e sem o pré-filtro. O pré-filtro B5 barrou 53 % das vagas da primeira janela. A retenção diária está em dry-run (`OPPORTUNITY_RETENTION_APPLY=false`).

## Dry-run da retenção (2026-10-19 01:54 UTC, nada apagado)

Contexto: um único dono com perfil ativo; 1 área e 1 país no perfil; retenção 7 dias; fora do alvo 2 dias.

| Linhas que um run completo apagaria | Só 7 dias | 7 dias + fora do alvo 2 dias |
|---|---|---|
| opportunity | 96 | 785 (689 por estar fora do alvo) |
| raw_item / raw_item_payload | 144 / 144 | 973 / 973 |
| source_occurrence | 99 | 791 |
| source_occurrence_observation | 144 | 1043 |
| normalization_result | 144 | 1172 |
| match_assessment / match_factor | 107 / 856 | 788 / 6304 |
| current_assessment | 50 | 341 |
| opportunity_skill / opportunity_compensation | 149 / 49 | 1587 / 385 |
| duplicate_candidate | 1 | 2 |

Protegidas: 0 com candidatura e 0 com marca de relevância nesse corte. Ligar exige o OK do dono (`OPPORTUNITY_RETENTION_APPLY=true` no `pipeline.env`).

## Consumo do Neon

- Projeto criado em 16/10 14:05 UTC. Até 19/10 ~02:00 (cerca de 60 h): `compute_time_seconds=10147` (2,82 CU-h), `active_time_seconds=38156` (10,6 h ativas). Autoscaling de 0,25 a 2 CU, suspensão padrão.
- Projeção linear: 2,82 / 60 × 720 ≈ **34 CU-h/mês** (meta < 80). Está próxima da estimativa do E5 (31 típica, 62 pior caso).
- Armazenamento: 183 MB de 1 GB. Projeção: sem aplicar a retenção, os 600 MB chegariam em cerca de 10 dias. Com a retenção de 7 dias e o pré-filtro, o volume deve estabilizar. Isso só fica provado depois de ligar o apply e medir alguns dias: **sem prova ainda**.

## Cards

| Card | Situação | Prova |
|---|---|---|
| A1 | feito | `2026-10-16-r55-a1-inventario.md` |
| A2, A3 | feito | `2026-10-16-r55-a2-a3.md`, #107 |
| A4 | feito | `2026-10-17-r55-a4-producao.md` (ensaio em branch descartável e produção) |
| A5 | feito | `2026-10-19-r55-a5-lotes.md`: 427 fontes ligadas, 0 sem execução |
| B1, B2 | feito | `2026-10-16-r55-b1-b2-c1.md`; pendência do B1 fechada no #115 |
| B3, B4 | feito | `2026-10-16-r55-b3-b4-d1.md` |
| B5 | feito | #116; em produção 143 de 268 vagas barradas na primeira janela |
| B6 | feito | `2026-10-17-r55-b6.md`, #114 |
| B7 | coberto pelo E4 | `2026-10-16-r55-e4.md`; taxa de duplicatas em produção: **sem prova** |
| C1 | feito | `2026-10-16-r55-b1-b2-c1.md` |
| C2 a C6 | feito | `2026-10-17-r55-c2-c6.md`, #111; C3/C5 fechadas no #115. `cache_hit=true` em produção: **sem prova** |
| D1 | feito | `2026-10-16-r55-b3-b4-d1.md` |
| D2 a D6 | feito | `2026-10-17-r55-d2-d6.md`, #110; verificação visual da UI em produção: **sem prova** |
| E1, E3 | feito | `2026-10-16-r55-e1-e3-ingestao.md`; 103 fora dos 7 dias na janela de 19/10 |
| E2 | código feito, apply desligado | dry-run acima; apagar exige OK do dono |
| E4 | feito | `2026-10-16-r55-e4.md`; reeleição do primário no #115 |
| E5 | feito | timer horário, janela de 900 s; 34 CU-h/mês projetados |
| E6 | parcial | tamanho medido; meta < 600 MB com 7 dias: **sem prova** até ligar a retenção |

## Pendências conhecidas

- Aprovar e ligar `OPPORTUNITY_RETENTION_APPLY`, depois medir o tamanho por alguns dias (E2/E6).
- O espaço apagado não volta ao sistema operacional sem `VACUUM FULL`; o Postgres reutiliza o espaço livre.
- Amarelos de revisão listados nos PRs #115 e #116. Exemplo: linhas antigas sem o marcador `departments: none` só entram na retenção curta por país, não por área, até serem reingeridas.
