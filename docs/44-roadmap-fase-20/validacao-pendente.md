# Fase 20 — o que já fizemos e o que falta

Atualizado em 2026-09-29 (janela de 7 dias encerrada antes pelo usuário; stack real reconstruída, Passo 5 concluído; status dos cards alinhado ao `README.md`). Branch `feature/f20-groq-e-consolidacao` (PR #25), CI verde em
`13d6605` (backend, migrações, frontend, Compose E2E e Playwright).

"Verde na CI" prova o comportamento com fakes e fixtures. Por isso cada card abaixo separa
**código** (implementado e testado) de **validação real** (provado com dados, uso ou tempo
reais).

## 1. Restrições em vigor

| Restrição | Efeito |
| --- | --- |
| Janela de sete dias encerrada antes, em 2026-09-29, pelo usuário | F20-35, F20-38 e F20-49 fecharam como "medição parcial" (~1,24 dia válido, T0b `2026-09-28T12:01:55Z`); a medição completa de 7 dias está no backlog da próxima fase (§7). A stack real deixou de ter restrição de parar ou reconstruir. |
| Cota diária do Groq ≈ 170k tokens, compartilhada com o worker da stack real (`AI_ENABLED=true`) | Uma rodada de avaliação por dia, logo após a virada UTC, conferindo o uso do dia antes. |
| Stack real roda o código atual (rebuild de 2026-09-29, migração `20260929_0054`, `restart: unless-stopped`) | F20-23 (sugestões, desligadas por padrão), F20-24 e o `work_mode` v6 já estão no código da stack real; a `f20manual` e as demais stacks de teste foram removidas. |

Incidentes que afetaram a janela (registrados na medição parcial): Docker caiu ~`2026-09-28T16:20Z`, religado às 16:43Z; nenhuma `source_run` entre `2026-09-29T00:01Z` e ~12:10Z (Docker/host parado); causa da cadência abaixo do esperado (`0 */3 * * *`) não investigada.

## 2. Já feito

### Cards fechados (código + validação real)

| Card | Evidência principal |
| --- | --- |
| F20-01 / F17-03 | Gabarito full-text de 128 candidatos; `recall@10` full-text 0,3396 > `like` 0,2745 (`rotulagem/f20-01-relevancia-busca-fulltext.md`). Os demais checkboxes do F17-03 dependem da suíte de integração da CI. |
| F20-03 a F20-11, F20-13 a F20-17, F20-19, F20-20, F20-25, F20-26, F20-40 a F20-46 | Implementados com teste e CI verde (ver `README.md`). |
| F20-21 | 50 casos versionados (10 por grupo); baseline real `openai/gpt-oss-120b`: 50/50, p50 1.613 ms, 74.545 tokens. |
| F20-27 a F20-31 | Descoberta de ATS e coletores Workday, Teamtailor, Workable e Factorial homologados em boards reais. |
| F20-32 | Fechado como não viável: os termos da Gupy proíbem agregação. |
| F20-33, F20-34 | Critério 4 conferido; testes de componente da Inbox e do Overview. |
| F20-36, F20-37 | Descoberta limitada e coletor JobPosting validados em sites reais; endpoints de Anthropic e Apollo GraphQL homologados. |
| F20-39 | Retomada real: corte de conexão real gerou `PARTIAL` (20 vagas Adobe) e `resume_of_run_id` retomou 15, sem duplicata; `kill -9` confirmou o commit atômico; variantes de parser (`0042`) aceitas; 304 real em Greenhouse e Teamtailor. |
| F20-47 | E2E no navegador com falhas injetadas, verde na CI. |
| F20-48 | Upgrade do backup real e backfill retomado em 7 lotes, sem duplicata. |

### Validações reais feitas em cards

| Card | O que foi provado |
| --- | --- |
| F20-02 | Alias `ci` removido; acervo real reprocessado para `skills-v3` (1.735 linhas, `cicd` 221 → 112), com backup verificado. **Fechado — meta de UNKNOWN não atingida**: remedição de 2026-09-29 (`v6`/`seniority-v3`) deu UNKNOWN 49,42% (339/686; meta ~25%), JUNIOR+INTERN 0,73% (5 vagas); nenhuma vaga UNKNOWN tem título com palavra-chave. Continuação: [F20-76](fase-20/f20-76-senioridade-por-conteudo.md) (§7). |
| F20-18 | Prompt `v2` implementado; rodada real parcial (10/50) não justificou trocar. Decisão de 2026-09-28: `v1` segue padrão; a comparação completa dos 50 casos é opcional (§3, ordem 7). |
| F20-24 | Reserva interativa real: worker parou no teto (`skipped_budget=6`) e a análise pela UI concluiu. Falta a amostra de aging (§3). |
| F20-23 | Sugestões assistidas implementadas (desligadas por padrão); 30 vagas reais rotuladas (39 campos); regra `work_mode` corrigida (`13d6605`, normalizador `v6`): 11/13 casos resolvidos, 0 errado; rodada real do Groq: 69% de precisão geral, ver §3. Fechado; sugestões seguem desligadas e a reavaliação de `seniority` com gabarito maior está no §7. |

### Fechados na medição parcial e no rebuild de 2026-09-29

| Card | Resultado |
| --- | --- |
| F20-35 / F20-38 / F20-49 | "Feito — medição parcial (janela encerrada antes pelo usuário)". Janela válida ~1,24 dia: +33 vagas úteis novas (~26,6/dia), `collected_recently` 8 → 3 pelo buraco de ~12 h, fallback do Groq 23,3% e 429 22,3% (acima da meta, quota diária do modelo primário), `json_valid_rate` 100%, 0 rate limit nas coletas. Inconclusivo para custo de IA e cobertura; bytes evitados por ETag (F20-38) não medidos porque `source_run` não guarda bytes. Evidência: [`evidencias/rebuild-stack-real-2026-09-29.md`](evidencias/rebuild-stack-real-2026-09-29.md) §1. |
| F20-53 / F20-55 / F20-60 / F20-71 | Fontes importadas e habilitadas na stack real com probe (120 importadas, 120 `PASSED`, 137 habilitadas no total; HN com `0 18 3 * *`; DoorDash, Remotebase, Lemon.io, 26 do F20-71, 21 do F20-53). Braintrust excluída (proibida); talentpluto e Pearl Talent rejeitadas. Evidência: [`evidencias/rebuild-stack-real-2026-09-29.md`](evidencias/rebuild-stack-real-2026-09-29.md) §2 e §7. |
| F20-70 / F20-61 | Acervo real reprocessado para `v6`/`seniority-v3` (686 oportunidades preservadas, 1383 `normalization_result` v6). |

### Correções que surgiram na validação

- Quota Guard esperava ~10 h numa quase-estouro por minuto (`21c5ec8`).
- Coletores Workday, Teamtailor, Workable e Factorial não eram montados em execuções agendadas; `make collect` usava registro incompleto.
- Parser Factorial rejeitava vagas sem time.
- Cobertura de ATS do dashboard ignorava os ATS novos (`d0d3101`).
- Soak e E2E com literais desatualizados (`skills-v1`, métricas do Ollama, `seniority-v1`, job opcional do F20-23).
- Stack real sem `schedule` em nenhuma fonte: nada era coletado desde 2026-09-26. Corrigido para `0 */3 * * *`; 3 fontes de teste desativadas.
- 95 das 120 fontes importadas em 2026-09-29 vieram sem `schedule` (o worker pula fonte sem agenda): receberam `0 6 * * *` (Workday) ou `0 */3 * * *` (demais ATS), para maximizar vagas.

## 3. Falta — rodadas com o Groq real (uma por dia)

| Ordem | Card | Tarefa | Critério |
| --- | --- | --- | --- |
| 1 | F20-23 | **Feito em 2026-09-29** (`evidencias/precisao-f20-23-2026-09-29.md`): 69% geral (11/16), `seniority` 73%, `work_mode` 50%; 36,7 mil tokens do 20B; valores canônicos intactos; corrigido schema/prompt que causava HTTP 400. | Manter `worker_suggest_enabled=False`; reavaliar só `seniority` com gabarito maior. |
| 2–6 | F20-22 | Quota Groq `gpt-oss-120b` esgotada em 2026-09-29 13:27Z (169.522 tokens); rodadas a partir de **2026-09-30 00:00Z**, uma por dia: 120B baixo, 120B médio; 20B baixo e médio; Qwen baixo e médio (comandos em `docs/pesquisas/benchmark-modelos-groq.md`) | Depois das rodadas: revisão humana por relatório (rubrica; recomendações pré-autorizadas) e decisão por `scripts/benchmark_report.py`. |
| 7 (opcional) | F20-18 | Comparação completa dos 50 casos, `v2` × `v1`. A decisão de manter `v1` já vale (README, F20-18); esta rodada só roda com sobra de quota do Groq depois do F20-22 e não bloqueia o F20-50. | `coverage` e português sobem; `inventions` 0; nada piora no `reserved`. Só então reavaliar a troca do padrão. |
| 8 | F20-24 | Amostra de aging sob Groq real, na stack real (a `f20manual` foi removida) | Itens fora do topo processados na proporção configurada. |

## 4. Passo 5 — concluído em 2026-09-29

Executado em 2026-09-29, com a janela de 7 dias encerrada antes pelo usuário. Evidência
completa: [`evidencias/rebuild-stack-real-2026-09-29.md`](evidencias/rebuild-stack-real-2026-09-29.md).

1. **Medição T7 (F20-35, F20-38, F20-49): feito, parcial.** Janela válida de ~1,24 dia; veredito inconclusivo (§2). A medição completa de 7 dias e os bytes evitados por ETag foram para o §7.
2. **Backup e rebuild: feito.** Dump verificado (`pre-rebuild-2026-09-29.dump`, 9.469.563 bytes, sha256 `e1d9539a14c4...`; só `pg_restore --list`, sem restore-check), rebuild sem `down -v`, migrações até `20260929_0054` (head única), 686 oportunidades antes e depois. Acervo reprocessado para `v6`/`seniority-v3` (v6 = 1383 = total de `raw_item`).
3. **Backfills: feito.** `backfill_opportunity_company.py` (nada a ligar) e `backfill_startup_evidence.py` (21 propostas, todas `skipped: company not found`; item no §7), cada um com dry-run antes.
4. **Ativação das fontes: feito.** 120 fontes da `f20manual` importadas com probe (120 `PASSED`), 137 habilitadas na stack real: as 34 homologadas de 2026-09-28, F20-60 (incluindo DoorDash, Remotebase e Lemon.io), F20-71 (26), F20-53 (21), HN com `0 18 3 * *`. 95 fontes importadas sem `schedule` receberam `0 6 * * *` (Workday) e `0 */3 * * *` (demais ATS). Braintrust não foi importada (proibida); talentpluto e Pearl Talent rejeitadas.
5. **`restart: unless-stopped`: feito** (`815786f`; postgres, api, worker e frontend confirmados por `docker inspect`).
6. **Remedição de senioridade: feito, meta não atingida.** UNKNOWN 49,42% (339/686) antes e depois de `v6`/`seniority-v3` (meta ~25%); JUNIOR+INTERN 0,73%. As sugestões do F20-23 seguem desligadas. Continuação: [F20-76](fase-20/f20-76-senioridade-por-conteudo.md) (§7).

Pertencimento das fontes importadas é herdado da `f20manual` (o probe prova que o endpoint responde e que o coletor lê 1 item, não que o board é da empresa; Remotebase é a de evidência mais fraca).

## 5. Falta — sanidade e pendências menores

| Item | Estado |
| --- | --- |
| Testes instáveis por banco de teste compartilhado | Resolvido (`79d45c0`): 6 causas de vazamento entre testes corrigidas; 8 rodadas completas (ordem padrão + 7 sementes via `RANDOM_ORDER_SEED`) com 981 aprovados e 0 falhas |
| `alembic check` e head única (F20-05) | Resolvido (`79d45c0`): `env.py` sem `include_schemas=True` nunca comparava os schemas reais; corrigido, modelos alinhados ao banco (índices declarados, `ondelete` do modelo corrigido), head única `20260926_0052`, sem migração nova |
| F20-38: orçamento compartilhado entre duas fontes do mesmo host | Resolvido — par real achado (Airbyte + Temporal, ambas `ashby`, host físico `api.ashbyhq.com`); execução real de cada uma incrementou a mesma linha `host_budget_state` (19 → 20 → 21). Evidência: `evidencias/orcamento-host-compartilhado-2026-09-28.md` |
| F20-36: board da Airbyte | Resolvido — `greenhouse` continua `404` real, mas o board atual é `ashby` (`board_identifier=airbyte`, 200, 12 vagas reais). Mesmo achado para Temporal (`ashby`, `temporal`, 62 vagas) e ClickHouse (`ashby`, `clickhouse`, 186 vagas), citados no mesmo item. Todas as três probadas (`PASSED`), ativadas e com execução real `SUCCEEDED` na `f20manual`. Evidência: `evidencias/ativacao-fontes-2026-09-28.md` §2.3/§6 (atualizado) |
| API sem endpoint para editar `schedule` de fonte | Resolvido (`98161b4`): `PATCH /sources/{id}/schedule`, valida o cron com o mesmo `CronTrigger` do agendador, aceita `null` (sem agenda) e usa `expected_version` como as demais rotas; campo cheap no `SourceControlsPanel` com teste de componente |
| Fixture `pre_f20_dump.sql` com `normalizer_version` escrito à mão | Resolvido (`98161b4`): `_restore_fixture` reescreve o literal `v6` para `NORMALIZER_VERSION` antes de entregar o SQL ao `psql`; teste novo falha se o literal voltar sem a substituição |
| Frontend nginx cacheia o IP do container `api`; recriar `api` sozinho devolve 502 até reiniciar o frontend | Resolvido (`4f4a0ae`): `resolver 127.0.0.11 valid=10s ipv6=off;` e `proxy_pass` baseado em variável (`set $upstream_api api:8000;` + `rewrite` preservando o corte de `/api/`) em `docker/frontend/nginx.conf`; provado em projeto Compose isolado (`-p f20ngx`): depois de `up -d --force-recreate api`, `/api/health` respondeu 200 pelo frontend sem reiniciá-lo. Gate barato de sintaxe (`nginx -t`) adicionado ao job `frontend` de `.github/workflows/pipeline.yml` |
| Overview e Sources com ATS novos sem teste visual | Resolvido (`4f4a0ae`): testes de componente cobrindo `workday`, `teamtailor`, `workable`, `factorial` e `jobposting` em `apps/web/src/routes/SourcesPage.test.tsx` (novo) e `apps/web/src/routes/OverviewPage.test.tsx` (fontes com falha e métricas por fonte) |
| GitGuardian no PR #25 | Resolvido como falso positivo — 1 achado (`Bearer Token`, commit `17962c84e2074f58eb38544ed0869ae5d89554f7`, `tests/backend/platform/ai/test_sanitizer.py:96`): fixture de teste do sanitizador (`test_bearer_token_masked`), valor sintético (`abc123.def456.ghi789`), não é uma credencial real. Nenhuma rotação necessária. Repositório não tem convenção `.gitguardian.yaml`; nenhuma criada (fora do pedido) |
| Rotacionar a chave Groq usada nas rodadas | Com o usuário |
| [F20-61 — Filtro de recência (14 dias) com exceção para estágio/programas com prazo](fase-20/f20-61-filtro-de-recencia-14-dias.md) | Feito — mesclado em `feature/f20-groq-e-consolidacao` (`5a1e062`), CI verde em `13d6605`; critérios de aceite cobertos por teste (backend + componente). Volume real de vaga junior/estágio/programa-com-prazo no acervo real (item 5 do escopo do card, não critério de aceite) foi para o §7 |
| [F20-70 — Fechar lacunas de palavra-chave do normalizador de senioridade](fase-20/f20-70-lacunas-de-palavra-chave-senioridade.md) | Feito — regras e testes mesclados (`5a1e062`; `seniority-v2` → `seniority-v3`); acervo real reprocessado em 2026-09-29 (critério de aceite 4). O UNKNOWN geral não mudou (49,42%): ver F20-02 e [F20-76](fase-20/f20-76-senioridade-por-conteudo.md) (§7) |
| [F20-54 — Marcação "startup" com evidência e filtro na UI](fase-20/f20-54-marcacao-de-startup-e-filtro.md) | Feito — mesclado em `feature/f20-groq-e-consolidacao` (`12f7dfb`; ligação com a descoberta em `82ea977`, script `scripts/backfill_startup_evidence.py`); critérios cobertos por teste (backend + componente). Backfill na stack real em 2026-09-29: 21 propostas, todas `skipped: company not found`, 0 evidências gravadas; o filtro devolve vazio no acervo real até haver empresa ligada (§7) |
| [F20-74 — Workday: parar no `total` anunciado (cap de 2000)](fase-20/f20-74-workday-paginacao-cap-2000.md) | Validado na `f20manual` após a correção: Accenture com `items_seen` 2000, `persisted` 1989, `PARTIAL` com `INVALID_ITEM` (11 itens sem título; ver o card). O wrap de paginação está corrigido (sem `PARSER_SCHEMA_CHANGED`). **Resolvido 2026-09-29**: itens sem título contam como `skipped`, não `invalid` (novo card [F20-75](fase-20/f20-75-workday-postings-sem-titulo.md)); re-execução da Accenture na `f20manual` com o F20-75: `SUCCEEDED`, 2000 vistos, 1996 persistidos, 4 skipped, 0 invalid |
| [F20-72 — Perfil padrão inclui JUNIOR/INTERN](fase-20/f20-72-perfil-padrao-inclui-junior-intern.md) | Fechado sem mudança de código de produção; testes de domínio adicionados |
| [F20-55 — Coletor "Who is hiring?" da Hacker News](fase-20/f20-55-hn-who-is-hiring.md) | Feito — termos revisados (viável, risco residual em `pesquisas/termos-hn-who-is-hiring.md`); coletor `hacker_news` mesclado em `feature/f20-groq-e-consolidacao` (`198fade`), critérios cobertos por teste; execução real na `f20manual` (`evidencias/hn-who-is-hiring-2026-09-29.md`): `PARTIAL` (19 comentários sem empresa), 175 oportunidades, JUNIOR+INTERN 2,3%, 3 propostas de ATS. Fonte importada e habilitada na stack real em 2026-09-29 com schedule `0 18 3 * *` (mensal, dia 3, 18Z). Ampliar a extração de papel do corpo do texto (61 itens sem título) só com evidência |
| F20-60 — pendências do backlog de carreiras | Movidas para o backlog da próxima fase (§7); não bloqueiam o F20-50. Os 3 `activate` (DoorDash, Remotebase, Lemon.io) estão habilitados na stack real (§4 item 4). |

## 6. Último card

**F20-50 — Definition of Done e documentação final.** Começa quando as seções 3 e 5
estiverem fechadas (a §4 foi concluída em 2026-09-29). Não bloqueiam: a comparação opcional
do F20-18 (§3, ordem 7) e o backlog da próxima fase (§7). Critérios: corrigir a tabela de
status do `README.md`; documentação final; CI verde; depois, merge do PR #25 na `main`
**com confirmação do usuário**.

## 7. Backlog para a próxima fase

Itens que sobraram da fase (F20-60, medição parcial, senioridade, vínculo de empresas) e não bloqueiam o F20-50 nem o merge do PR #25. **Decisões de 2026-09-29:** o usuário delegou a escolha; cada item foi absorvido pelo card F48 correspondente da [SPEC 48](../48-spec-mais-vagas.md) (o que é medição continua aberto, com o passo que a fecha):

- `discover_sites.py` nas 13 empresas sem ATS, em ou depois de `2026-10-28` (fim do lock de
  30 dias), **antes** de `discover_ats.py`; Crossover excluído. Decidido: executar na data, sob
  o F48-21.
- 9 empresas `probe` sem decisão (Mercado Livre, Nuvemshop, FullStack, AgileEngine,
  Cognizant, TCS, Infosys, Terminal, AI/R Avenue Code): páginas dinâmicas ou bloqueio a bot
  impediram confirmar JSON-LD/ATS; não ativar os boards homônimos (`fullstack`, `terminal`,
  `tcs`, `aircompany`). Detalhes em `evidencias/careers-backlog-f20-60-2026-09-29.md`.
  Decidido: sem confirmação de JSON-LD/ATS em 2026-10-28 a empresa fica `no-site`, sem burlar bloqueio
  de bot (F48-21).
- Medição completa de 7 dias (F20-35, F20-38, F20-49): a de 2026-09-29 cobriu ~1,24 dia
  válido. Decidido: refazer **depois** de F48-06 (funil no `doctor`) e F48-07 (bytes por run e
  alarme de buraco), com 7 dias de agenda estável e o host sem suspensão. Ainda aberto (medição):
  bytes evitados por ETag, custo de IA, cobertura, a cadência abaixo do esperado (6 blocos em
  ~30 h em vez de ~10) e o buraco de ~12 h de 2026-09-29.
- [F20-76](fase-20/f20-76-senioridade-por-conteudo.md): classificar senioridade pelo corpo da
  vaga. Decidido: absorvido pelo F48-15 (`seniority-v4` com evidência citada, precisão ≥ 90 %
  em gabarito de ≥ 200 vagas antes de gravar; meta ≤ 30 % nas vagas com descrição). Sugestões
  do F20-23 seguem desligadas.
- Empresas sem vínculo: 61 fontes importadas na stack real estão sem `company_source`/empresa
  (21 "Proposed ..." e fontes criadas só com `company_name`), e as 21 propostas do
  `backfill_startup_evidence.py` foram `skipped: company not found` (0 linhas em
  `company_startup_evidence`). Decidido: F48-17 (criar/ligar empresas e reexecutar o backfill,
  dry-run antes). Contagem de 2026-09-29 ~20:04Z: 63 fontes habilitadas sem vínculo.
- F20-61: medir o volume real de vaga junior/estágio/programa-com-prazo no acervo real (item 5
  do card). Aberto (medição): entra no relatório do F48-06 depois da mudança de janela do
  F48-16 (30 dias, lente de 14).
- Restore-check do dump `pre-rebuild-2026-09-29` (`scripts/restore_check.py`; só o TOC foi
  listado) e revisão de pertencimento das fontes importadas (herdado da `f20manual`).
  Decidido: o restore-check roda **antes de qualquer reprocessamento em massa** do F48
  (F48-03 script, F48-09, F48-14, F48-15); a revisão de pertencimento fica no P2-2 do doc 47.
- Rotação da chave Groq usada nas rodadas (§5): continua com o usuário; é ação sobre segredo
  e não foi decidida aqui.
- Números de oportunidades desta página (686) são do rebuild de 2026-09-29, antes da importação
  de 120 fontes; o snapshot atual (11.267, ~20:04Z) está na SPEC 48 §2.
