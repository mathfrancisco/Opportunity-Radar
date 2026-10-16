# Roadmap 55 — busca, IA, regras de negócio e migração dos dados locais

**Estado: aprovado pelo dono em 16/10/2026; execução em andamento, começando pela Frente E.**

Base de evidência: piloto online de 16/10, descrito em
[2026-10-16-f53-fechamento-piloto](../53-roadmap-hospedagem/evidencias/2026-10-16-f53-fechamento-piloto.md),
e inventário somente leitura do banco Docker local `opportunity-radar-dev-postgres-1`.

## Fatos que orientam o plano

| Fato | Origem |
| --- | --- |
| Banco local com 2,0 GB; o Neon gratuito permite 1 GB por branch | `pg_database_size` local; projeto Neon `free_v3` |
| Banco local na migração `20261008_0068`, antes da tenancy `0069`: registros sem `owner_sub` | `alembic_version` local |
| 442 fontes (inhire 257, ashby 66, greenhouse 61, workday 19, lever 15, workable 11, teamtailor 7, factorial 2, manual 2, remotive 1, hacker_news 1) | `acquisition.source_definition` |
| 36 195 oportunidades, 8 031 raw items (490 MB com payload), 600 675 observações, 5 513 avaliações com 44 104 fatores (735 MB) | `pg_stat_user_tables` (contagens aproximadas) |
| Na nuvem, a janela finita só tem collect, normalize e evaluate; a análise por IA roda só sob demanda | `scripts/run_pipeline_once.py:81-85` |
| A normalização processa 100 itens por janela (94 de 100 de um total de 225 coletados) | janela de 16/10 15:22 |
| Fonte com agendamento manual é pulada pela janela | janela de 16/10 13:32 (`skipped: 1`) |
| Descrição Greenhouse exibida com HTML escapado; a IA respondeu que a vaga "não lista requisitos", embora o texto cite Ruby e GraphQL | E2E de 16/10 |
| "Intermediate" virou senioridade `UNKNOWN`; `COUNTRY_ALLOWED` ficou `NOT_APPLICABLE` em vagas de UK, US e CA com perfil BR; 23 vagas ficaram entre 48 e 53 pontos | E2E de 16/10 |
| Uma análise IA custou 1 568 tokens (1 099 de prompt e 469 de resposta) e levou 1,7 s; teto de 1 000 requisições/dia no `gpt-oss-120b` | `platform.ai_call_record`, `ai_quota_usage` |

## Frente A — migração dos dados locais para a nuvem

| Card | Entrega | Critério de aceite |
| --- | --- | --- |
| R55-A1 | Inventário exato do banco local (contagens com `count(*)`, não estatística), incluindo tabelas `company_radar` e `profile`, que a estatística mostra vazias | relatório datado sem PII |
| R55-A2 | Decisão de escopo: catálogo completo (fontes, empresas, estado de homologação), evidências recentes (por exemplo, 30 dias de raw items ainda abertos) e nada de avaliações antigas, que são reprocessadas | projeção abaixo de 60% do limite de 1 GB do Neon (`scripts/project_neon_budget.py`) |
| R55-A3 | Script idempotente de exportação e importação: exporta do banco local já migrado para a `0069` numa cópia descartável e grava com o `owner_sub` do dono, lido de arquivo protegido e nunca impresso. Inserção com `ON CONFLICT` nas chaves de identidade (tipo + config da fonte, `uq_raw_item_source_identity_hash`) | re-execução sem duplicatas; teste em banco `_test` |
| R55-A4 | Ensaio num branch Neon descartável, depois aplicação no `production` de São Paulo | contagens antes e depois por tabela; branch removido |
| R55-A5 | Agendamento distribuído das fontes migradas (cron por fonte, espalhado na janela) e uma janela completa | coleta > 0 nas fontes habilitadas; nenhuma falha de lease; consumo de CU-h medido |

Risco: 257 fontes inhire e 19 workday têm teto de requisições por host
(`host_request_ceilings`). A janela de 1 h precisa caber nisso; R55-B2 trata do
caso.

## Frente B — busca e coleta de vagas

| Card | Entrega | Critério de aceite |
| --- | --- | --- |
| R55-B1 | Normalização sem teto fixo de 100 por janela: lote em laço até esvaziar ou até o deadline | 225 coletadas, 225 normalizadas (menos as inválidas) numa janela |
| R55-B2 | Janela cobre fontes "manual" vencidas e respeita o orçamento por host; ordena por prioridade e idade do último sucesso | métrica de fontes executadas/elegíveis por janela |
| R55-B3 | Limpeza de HTML da Greenhouse (`content=true` retorna HTML escapado) e dos outros ATS antes de normalizar e de enviar à IA | descrição em texto limpo; teste por ATS com fixture real |
| R55-B4 | Extração de skills e senioridade a partir do texto limpo (taxonomia `skills-v5`), mapeando "Intermediate", "Mid", "II/III", "Staff" etc. | queda de `UNKNOWN` em senioridade e tecnologia, medida antes e depois |
| R55-B5 | Filtro de área e país antes de gravar oportunidade (hoje 131 de 225 vagas eram de outra área) e retenção mais curta para vagas fora do alvo | storage por fonte medido; nenhuma vaga do alvo descartada |
| R55-B6 | Descoberta de novos boards a partir do catálogo de empresas (Tavily só quando o ATS não for conhecido; respeitar `tavily_credit_budget_per_run`) | fontes propostas na fila de homologação, sem habilitação automática |
| R55-B7 | Deduplicação entre fontes (mesma vaga em Greenhouse e LinkedIn/Remotive) com `duplicate_candidate` | taxa de duplicatas medida |

## Frente C — uso da IA

| Card | Entrega | Critério de aceite |
| --- | --- | --- |
| R55-C1 | Etapa `analyze_pending` na janela finita, limitada por `worker_analyze_daily_cap_fraction` e pelos vereditos `HIGH_PRIORITY,RECOMMENDED` | análises por janela visíveis em `ai_call_record`, sem erro de quota |
| R55-C2 | Prompt com texto limpo e truncado por seção (requisitos e responsabilidades primeiro), sem o texto institucional da empresa | tokens de prompt por análise caem (hoje 1 099) sem perder campos |
| R55-C3 | Cache por `content hash + profile version + prompt version`, para não reanalisar vaga inalterada | `cache_hit=true` em re-run |
| R55-C4 | Modelo por tarefa: `gpt-oss-20b` para classificação e extração, `120b` só para análise de encaixe; fallback com breaker | custo médio por vaga e taxa de fallback no painel |
| R55-C5 | IA para extrair o que as regras não acharam (senioridade, país, autorização de trabalho) como sugestão auditável, sem alterar o score determinístico sem revisão | campos sugeridos com origem `ai`; teste que impede a IA de mudar o veredito |
| R55-C6 | Orçamento diário explícito no painel (requisições e tokens restantes por modelo) | painel mostra 1 000/dia e o consumo |

## Frente D — regras de negócio

| Card | Entrega | Critério de aceite |
| --- | --- | --- |
| R55-D1 | `COUNTRY_ALLOWED` usa a localização estruturada da vaga ("Remote, United Kingdom") quando não houver texto de elegibilidade explícito | vaga UK-only com perfil BR fica fora ou em revisão, com explicação |
| R55-D2 | Peso de `UNKNOWN` no score: separar "desconhecido" de "neutro" para não empatar 20 vagas em 52,8 | distribuição de score menos concentrada; testes de fronteira |
| R55-D3 | Senioridade por faixa (Júnior/Pleno aceita "Intermediate"/"Mid"; "Senior" vira penalidade, não eliminação) | casos de tabela no teste de matching |
| R55-D4 | Feedback "Não é para mim" (área, senioridade, local, empresa) vira ajuste do perfil sugerido, nunca automático | sugestão visível no Perfil |
| R55-D5 | Regras de ausência e reabertura com 2 execuções completas consecutivas, documentadas na UI | teste e texto na tela da vaga |
| R55-D6 | Defeitos de UI vistos no piloto: `homologation_audit` como `[object Object]`, cartão de IA "Desligada" enquanto carrega, Status com texto "Ambiente local" e sem métricas por fonte | correções com teste de componente |

## Frente E — janela de 7 dias, coleta horária e teto de 1 GB

Decisão do dono (16/10): manter só vagas publicadas até 7 dias antes da coleta,
coletar de hora em hora e nunca gravar vaga duplicada. O banco precisa caber em
1 GB no Neon.

| Card | Entrega | Critério de aceite |
| --- | --- | --- |
| R55-E1 | Filtro na ingestão: descartar antes de gravar a vaga com `published_at` (ou a primeira observação, se a fonte não informar data) anterior a `coleta - 7 dias`; contar como `skipped_stale` em `source_run` | teste com vagas de 6, 7 e 8 dias; nada com mais de 7 dias é gravado |
| R55-E2 | Retenção diária: apagar em lotes oportunidades, raw items, payloads, observações, avaliações e fatores de vagas com mais de 7 dias, exceto vagas com candidatura ou marcadas como relevantes pelo dono | dry-run com contagens; execução idempotente; candidaturas preservadas |
| R55-E3 | Sem duplicata: identidade por `source + external_id`, ou `url` canônica, ou hash semântico (título, empresa, local); re-coleta sem mudança não grava raw item novo, payload novo nem observação nova, só atualiza `last_seen_at` | re-run horário com 0 linhas novas por vaga inalterada (medido) |
| R55-E4 | Duplicata entre fontes: mesma vaga em duas fontes vira uma oportunidade, com ocorrências ligadas | teste com a mesma vaga na Greenhouse e na Remotive |
| R55-E5 | Coleta horária: timer `OnCalendar=hourly`, janela curta (deadline de cerca de 15 min), `Persistent=false`, sem sobreposição (lock do claim) | 24 janelas/dia sem catch-up; projeção do Neon abaixo de 80 CU-h/mês |
| R55-E6 | Redução de dados, ver lista abaixo | `pg_database_size` medido antes e depois; abaixo de 600 MB com 7 dias de dados |

Formas de reduzir os dados (R55-E6), da maior economia para a menor:
1. **Payload bruto:** depois de normalizar, guardar só o hash e um texto limpo
   truncado. O `raw_item_payload` local tinha 207 MB para 8 031 itens.
2. **Observações:** gravar só em mudança de estado. Hoje há uma linha por vaga por
   execução (600 675 linhas no local); com coleta horária isso explode.
3. **Avaliações:** manter só a avaliação corrente e a anterior por vaga. Na
   inserção, apagar os `match_factor` de avaliações antigas (375 + 360 MB no local).
4. **Fora do alvo:** não persistir vagas fora da área e do país do perfil. Na
   coleta de 16/10, 131 de 225 vagas eram de outra área.
5. **Descrição:** guardar texto limpo, sem HTML e sem o bloco institucional
   repetido da empresa.
6. **Compressão e índices:** TOAST com `lz4` nas colunas grandes; remover índices
   não usados (`pg_stat_user_indexes.idx_scan = 0`); `VACUUM` depois da retenção.
7. **Cache Tavily e registros de IA:** TTL curto, e `ai_call_record` com 7 dias em
   vez de 30.
8. **Medição contínua:** `scripts/retention_report.py` e
   `project_neon_budget.py` na janela diária, com alerta a 70% do limite.

## Ordem proposta

0. Frente E (R55-E1, E3, E2, E6 e por fim E5): o teto de 1 GB vale antes de migrar
   ou ampliar a coleta.

1. R55-B3, R55-B4 e R55-D1: corrigem a qualidade do dado que a IA e o score recebem.
2. R55-B1, R55-B2 e R55-C1: o pipeline da nuvem faz o ciclo completo sozinho.
3. Frente A, migração dos dados locais, com o dado já limpo e o pipeline completo.
4. R55-C2 a R55-C6 e R55-D2 a R55-D6: otimização e ajuste fino com dados reais.

Cada card segue a definição de pronto da F53: alteração revisada, teste positivo
e negativo, prova operacional datada e rollback.
