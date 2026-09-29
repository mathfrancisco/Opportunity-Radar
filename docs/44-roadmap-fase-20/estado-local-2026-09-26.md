# Estado local da Fase 20 — 2026-09-26

O trabalho está no [PR #25](https://github.com/mathfrancisco/Opportunity-Radar/pull/25),
branch `feature/f20-groq-e-consolidacao`. `8be7e4c` concentra Factorial e parte de
F20-39; `973b648` corrige a seleção do cliente PostgreSQL 17 no CI. Isto não fecha a fase.

## Inventário auditável

| Card | Feito e evidência | Restante |
| --- | --- | --- |
| F20-01 | Baseline e relatórios da busca; 86 casos rotulados `aceito`; medição real refeita (like recall@10=1,0, fulltext=0,817) reconfirma o viés conhecido. **2026-09-28 (`feature/f20-rotulos-2`):** 128 candidatos por full-text sobre `description` (16 consultas, inclui `kubernetes`/`frontend`), rotulados (68 relevantes/19 ambíguos/41 não relevantes), `queries.json` reconstruído; `eval_search.py --mode both` rodado depois que o stack real voltou (`recall@10 fulltext=0,3396 > like=0,2745`) — ver `docs/44-roadmap-fase-20/rotulagem/f20-01-relevancia-busca-fulltext.md`. | **Resolvido.** F17-03/F20-01: o critério de recall@10 está satisfeito com gabarito sem viés; os demais critérios do card (acento, sinônimo, filtro) dependem só da suíte de CI, não reverificada nesta sessão. |
| F20-02 | `skills-v2` em `e46b755`; UNKNOWN 50,62%; curadoria humana concluída (11 decisões `aceito`); alias `ci` removido, `SKILL_TAXONOMY_VERSION`→`skills-v3`, `NORMALIZER_VERSION`→`v5`; reprocessamento oficial rodado e verificado no acervo real em 2026-09-27 (`docs/44-roadmap-fase-20/evidencias/reprocessamento-skills-v3-2026-09-27.md`) — 648 oportunidades antes/depois, zero linha `skills-v2` órfã, 22 falhas idênticas. | F17-06 ainda não fecha: `seniority-v2` (`UNKNOWN` à metade do baseline) não atingido no acervo real (328/648 = 50,62%), achado fora do escopo deste card. |
| F20-03 | Critérios herdados mapeados para evidência. | Sem pendência de implementação identificada. |
| F20-04 | Ollama removido em `0e541aa`. | Sem pendência de implementação identificada. |
| F20-05 | Embeddings locais removidos em `82022dd`; migração passou nos gates registrados. | Sem pendência de implementação identificada. |
| F20-06 | Health, doctor e testes sem Ollama em `0e541aa`. | Sem pendência de implementação identificada. |
| F20-07 | Porta `LLMProvider` e `GroqProvider` implementada. | Sem pendência de implementação identificada. |
| F20-08 | Configuração cloud e segredos implementados. | Sem pendência de implementação identificada. |
| F20-09 | `AITask` e roteamento implementados. | Sem pendência de implementação identificada. |
| F20-10 | Retry e fallback em `1c90af6`. | Sem pendência de implementação identificada. |
| F20-11 | Circuit breaker em `1c90af6`. | Sem pendência de implementação identificada. |
| F20-12 | Quota Guard persistente em `b5072fd`; correção mínima em 2026-09-27 no chute de `next_available_at` (um quase-esgotamento de janela de minuto chutava 10h de espera em vez de 60s — achado ao rodar o baseline real de F20-21). | Sem pendência de implementação identificada. |
| F20-13 | Token Guard em `1c90af6`. | Sem pendência de implementação identificada. |
| F20-14 | Saída estruturada em `0ad7b34`. | Sem pendência de implementação identificada. |
| F20-15 | Sanitização PII e perfil mínimo em `0ad7b34`. | Sem pendência de implementação identificada. |
| F20-16 | Chave de cache por provedor em `e8c1600`. | Sem pendência de implementação identificada. |
| F20-17 | Adaptador Groq em `e8c1600`. | Sem pendência de implementação identificada. |
| F20-18 | Artefato `prompts/opportunity_analysis/v2/` (pt-BR, evidência conferida, `posting`/`profile_history` no payload); rodada real `v1`×`v2` no Groq em 2026-09-28 (parou em 10/50 casos, quota diária compartilhada), decisão tomada: manter `v1`, `Settings.ai_analysis_prompt` continua `"v1"`, `.env.example` intocado. | Rodada completa dos 50 casos fica pendente para uma janela sem concorrência de outros workers no mesmo `GROQ_API_KEY` — ver `docs/pesquisas/prompt-v2-vs-v1.md`. |
| F20-19 | Telemetria sem PII em `c3e7606`. | Sem pendência de implementação identificada. |
| F20-20 | Métricas API, Overview e doctor em `b45ff84`. | Sem pendência de implementação identificada. |
| F20-21 | Harness em `2f5defd` e `94edd57`; os 26 drafts de lacuna (Java/fullstack/IA) revisados e promovidos para `eval/cases/`; `eval/cases/` tem 50 arquivos, exatamente 10 Java/10 fullstack/10 IA/10 fora de área/10 inelegíveis, versionados; `test_eval_scoring.py` verde (22 passed); baseline real no Groq rodada em 2026-09-27 (`openai/gpt-oss-120b` pinado, 50/50 `AI_COMPLETED`, `inventions = 0`, latência e tokens registrados) — ver `docs/44-roadmap-fase-20/evidencias/baseline-groq-f20-21-2026-09-27.md`. | Sem pendência de implementação identificada. |
| F20-22 | Em andamento (`feature/f20-22-benchmark`). Critério de decisão escrito antes de rodar; gerador de comparação (`matching/benchmark.py`, `scripts/benchmark_report.py`) e ponto de extensão de roteamento por tarefa (`AI_REASONING_EFFORT_JOB_MATCH`/`_JOB_CLASSIFICATION`/`_JOB_EXTRACTION` em `Settings`, lido por `default_routes`; todos `None` por padrão, comportamento inalterado) — tudo com testes de fake, sem chamada ao Groq; ver `docs/pesquisas/benchmark-modelos-groq.md`. | Faltam 5 das 6 rodadas (120B×medium, 20B×low/medium, Qwen×low/medium; 120B×low já é o baseline de F20-21) e a rubrica humana de acerto de rótulo — plano dia a dia em `docs/pesquisas/benchmark-modelos-groq.md`. Rota `job_match` continua `openai/gpt-oss-120b`/`low` até a decisão sair de "pendente". |
| F20-23 | Tabela `opportunities.field_suggestion`, gatilho/descarte por evidência/aceitar-rejeitar em `opportunities/suggestions.py`, job `suggest-fields` desligado por padrão, endpoints HTTP; implementado em `feature/f20-23-classificacao` (sem Groq real, usa a rota `job_classification` já existente do F20-09). | Medição de precisão no acervo real (328/648 = 50,62% `UNKNOWN` de senioridade é o baseline) — ver `docs/pesquisas/sugestoes-f20-23.md`. **2026-09-28 (`feature/f20-rotulos-2`), depois do stack voltar:** amostra real de 30 vagas com `role_family`/`seniority`/`work_mode` `UNKNOWN` (39 campos), 30 corrigidos com evidência literal e 9 mantidos `UNKNOWN` por falta de evidência convincente — ver `docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.md`. Falta só a rodada real do Groq contra esse gabarito (fora do escopo deste worker). |
| F20-24 | Fila por valor (score, prioridade da empresa, amostra de aging) e reserva interativa de quota (`QuotaGuard.reserve(ceiling_requests=...)`) implementadas em `feature/f20-24-orcamento`; CI local verde (925 passed, ruff/mypy limpos); reserva interativa medida contra o Groq real em 2026-09-28 (teto reduzido do worker gera `skipped_budget=6`, análise interativa continua `AI_COMPLETED`). | Amostra de aging (`worker_analyze_aging_sample_ratio`) ainda não medida contra Groq real (só em CI com fake) — ver `docs/44-roadmap-fase-20/evidencias/analise-sob-orcamento-f20-24-2026-09-27.md`. |
| F20-25 | Fila de homologação em `99d2067`. | Sem pendência de implementação identificada. |
| F20-26 | Recusa por versão e bloqueio de ciclo em `c9be16e`. | Sem pendência de implementação identificada. |
| F20-27 | Descoberta e modelos de ATS implementados; relatório real executado em 2026-09-26 (115 empresas, 4 ATS revelados: `homologacao-real-2026-09-26.md` §1). | Sem pendência de implementação identificada. |
| F20-28 | Coletor Workday em `7516acb`; validado com dados reais (Adobe, Workday) e homologado/coletando (Adobe) em 2026-09-26; fix de integração `f51fa77`/`676339c`. | Sem pendência de implementação identificada. |
| F20-29 | Coletor Teamtailor em `919c4b5`; validado com dados reais (Seedtag, Lingokids) e homologado/coletando 2x (Seedtag) em 2026-09-26; fix de integração `f51fa77`/`676339c`. | Sem pendência de implementação identificada. |
| F20-30 | Coletor Workable em `ae1ee79`; validado com dados reais (Workable, Wantable) e homologado/coletando (Wantable) em 2026-09-26; fix de integração `f51fa77`/`676339c`. | Sem pendência de implementação identificada. |
| F20-31 | `factorial.py` e testes de fixture em `8be7e4c`; validado com dados reais (Factorial, Agentero) e homologado/coletando (Agentero) em 2026-09-26; bug de parser corrigido em `cbe206b`; fix de integração `f51fa77`/`676339c`. | Sem pendência de implementação identificada. |
| F20-32 | Fechado — não viável em 2026-09-27. Termos de Uso da Gupy proíbem nominalmente agregar/copiar/duplicar vagas (`docs/pesquisas/termos-gupy.md`); nenhum código de coletor foi escrito. | Sem pendência de implementação — card encerrado pela revisão de termos. |
| F20-33 | Palavras-chave do perfil em `b7f432e` e `e9be146`; critério 4 confirmado (`git diff --stat b7f432e~1..e9be146 -- scripts/enable_sources.py` vazio; roteiro em `docs/44-roadmap-fase-20/rotulagem/f20-33-verificacao-criterio-4.md`). | Sem pendência de implementação identificada. |
| F20-34 | Buscas salvas em `5088e6`; testes de componente da Inbox (`SaveSearchForm`, `SavedSearches`) e da Overview (`SavedSearchesWithNews`) em `70a0a40` (`apps/web/src/routes/InboxPage.test.tsx`, `OverviewPage.test.tsx`); `npm run check` verde (lint, types, 28 arquivos/145 testes, build). | Sem pendência de implementação identificada. |
| F20-35 | Funil e rendimento em `102a53d`; janela de baseline de 7 dias iniciada em 2026-09-26 (T0 real salvo em `f20-search-metrics-baseline-2026-09-26.json`), termina 2026-10-05. | Medir a janela de 7 dias completa na máquina de referência (não pode terminar antes de 2026-10-05). |
| F20-36 | Descoberta limitada (`acquisition/limited_discovery.py`) e migração `20260926_0044` em `feature/f20-36-37-sites`; validada com dados reais em 2026-09-27 (ver `evidencias/sites-jobposting-2026-09-27.md`). Endpoint real do board homologado em 2026-09-28 via probe real (Anthropic e Apollo GraphQL aceitos; Airbyte não resolve mais, `404` real) — ver `evidencias/retomada-real-e-endpoints-2026-09-28.md` §6. | Aplicar a correção de `CompanySource.endpoint` (Anthropic, Apollo GraphQL) na pilha real depois da janela de 7 dias; reinvestigar o board da Airbyte. |
| F20-37 | Coletor JobPosting (`acquisition/jobposting.py`) em `feature/f20-36-37-sites`; validado com dados reais em 2026-09-27 (Qonto, Scaleway, Sonar via Lever). | Sem pendência de implementação identificada. |
| F20-38 | Agenda adaptativa e HTTP condicional em `f14bc6e`; em 2026-09-27, os 8 coletores HTTP (ashby/greenhouse/lever/remotive/workday/teamtailor/workable/factorial) passaram a enviar `If-None-Match`/`If-Modified-Since` e reportar 304/`ETag`/`Last-Modified` via `acquisition/http_conditional.py`; 304 real confirmado em Greenhouse (Lokalise) e Teamtailor (Seedtag) na pilha isolada `f20cond`, com bytes evitados medidos (19.820 e 345.111 bytes). | Medir operação real (comparação de 7 dias, depende da janela do F20-35) e orçamento por host compartilhado entre duas fontes reais do mesmo host (nenhum par do catálogo importado compartilha host ainda). |
| F20-39 | Hashes, presença por run e migração `0041` em `8be7e4c`; retomada explícita (`resume_of_run_id`, migração `0043`), manifesto 304 declarado (`CollectionTelemetry.record_manifest`) e métrica operacional (`presence_confirmed_without_reprocessing` em `/api/source-metrics`) implementados e testados; presença sem duplicação confirmada com dado real em 2026-09-26 (`make collect` 2x contra Seedtag). Em 2026-09-27: Workday passou a ler `request.cursor` e preencher `CollectedItem.cursor` (real, confirmado contra Adobe: 10 itens + 5 novos via `cursor="10"`, offset 10→15, sem repetição); variantes de parser (migração `0042`) **aceitas** com `test_a_real_parser_upgrade_appends_a_variant_instead_of_colliding`, teste de integração contra Postgres real. Em 2026-09-28: `kill -9` real do processo confirma zero estado persistido antes do commit final; um corte real de conexão TCP na 2ª página de uma coleta real contra Adobe produziu um `PARTIAL` retomável (20 vagas reais), e a retomada via `resume_of_run_id` + cursor operacional buscou 15 vagas reais novas sem duplicata — ver `evidencias/retomada-real-e-endpoints-2026-09-28.md`. | Confirmar CI verde na branch. Os outros 3 coletores novos (teamtailor/workable/factorial) continuam sem paginação real, então a retomada explícita por `resume_of_run_id` não se aplica a eles (sem "meio de página"). |
| F20-40 | Critérios aceitos com testes em `794b519`. | Sem pendência de implementação identificada. |
| F20-41 | Backup e manifesto AI em `a15d3b8` e `c9c291e`. | Sem pendência de implementação identificada. |
| F20-42 | Cliente e configuração Tavily implementados. | Sem pendência de implementação identificada. |
| F20-43 | Orçamento Tavily em `663c1ac`. | Sem pendência de implementação identificada. |
| F20-44 | Collector Tavily de descoberta implementado. | Sem pendência de implementação identificada. |
| F20-45 | Extração com cache em `2330f35`. | Sem pendência de implementação identificada. |
| F20-46 | Evidência e rollback de flush em `41a3ecf`, `fa93d15`, `c9c291e`. | Sem pendência de implementação identificada. |
| F20-47 | Percurso E2E no navegador (Playwright) e falhas injetadas (Groq 429/500/inválido, paginação parcial, 304, restart do worker) em `feature/f20-47-e2e`; 7/7 verde na pilha isolada `-p f20e2e47` (`docs/44-roadmap-fase-20/evidencias/e2e-falhas-injetadas-2026-09-27.md`). | Confirmação em CI real depende do push do coordenador; `opportunity-radar` não foi tocada. |
| F20-48 | Critérios provados em CI e contra o dump real (`f20up`); ver `docs/44-roadmap-fase-20/evidencias/upgrade-banco-populado-2026-09-27.md`. | Sem pendência de implementação identificada. |
| F20-49 | Não iniciado. | F20-47 e F20-48. |
| F20-50 | Não iniciado. | Aceitar F20-01 a F20-49 com evidência. |

## Evidência de validação e CI

- A CI `36279883936` para `973b648` aprovou backend lint, backend tests, migrations e
  frontend, mas falhou no Compose E2E ao verificar aquisição manual pela API pública.
  A asserção que falha é a verificação de `/api/opportunities` após normalizar 2 itens
  (`processed: 2, succeeded: 2`): o script comparava `skill['taxonomy_version']` (e,
  numa etapa seguinte, `data['taxonomy_version']` do matching) contra o literal
  desatualizado `"skills-v1"`. `SKILL_TAXONOMY_VERSION` subiu para `"skills-v2"` em F20-02
  (`docs/pesquisas/curadoria-skills-v2.md`), e o próprio F20-02 registra ter corrigido
  todos os literais de teste — exceto estes dois em `.github/workflows/pipeline.yml`, que
  ficaram para trás. Reproduzido localmente com
  `docker compose -p f20e2e -f compose.yaml -f compose.ci.yaml` (projeto isolado, nunca
  `opportunity-radar`): a resposta real de `/api/opportunities` trazia `taxonomy_version`
  `"skills-v2"` em ambas as skills, confirmando a asserção como a causa raiz, não o
  comportamento do backend. Corrigido nas duas linhas do pipeline (aquisição manual e
  matching). O ambiente `f20e2e` foi desligado com `down --volumes` ao final, sem tocar o
  projeto `opportunity-radar`.
- Local, 2026-09-26, banco Postgres recriado do zero (`docker compose -p f20w down
  --volumes` seguido de `pytest -q` com `RUN_DATABASE_INTEGRATION=1`): 858 testes backend
  aprovados, 10 ignorados, 0 falhas. `ruff check .` e `mypy` (115 arquivos) aprovados.
- Há uma falha externa do GitGuardian, cuja causa não foi confirmada nesta atualização.

## Próxima sequência

1. Abrir PR/empurrar a branch e confirmar o Compose E2E verde na CI real com a correção
   de `taxonomy_version` e o trabalho de F20-39 (retomada, manifesto 304, métrica).
2. F20-28 a F20-31 homologados com dados reais em 2026-09-26 (ver
   `docs/44-roadmap-fase-20/evidencias/homologacao-real-2026-09-26.md`); F20-32 fechado
   como não viável em 2026-09-27 pela revisão de termos (ver
   `docs/44-roadmap-fase-20/evidencias/homologacao-gupy-2026-09-27.md` e
   `docs/pesquisas/termos-gupy.md`) — nenhuma implementação pendente para este card.
3. F20-21 concluído em 2026-09-27 (baseline real no Groq, ver
   `docs/44-roadmap-fase-20/evidencias/baseline-groq-f20-21-2026-09-27.md`). Dos cards
   que citavam F20-21 como dependência, apenas **F20-18** e **F20-22** estavam
   bloqueados só por este baseline — ambos desbloqueados, nenhum implementado nesta
   sessão. F20-23 continua bloqueado (depende de F20-22, ainda não feito, além de
   F20-02/F20-03). F20-24 e F20-12 não dependiam deste baseline (F20-12 já estava
   "Implementado"; F20-24 depende de F20-39/F20-17/F20-16/F20-12, sem F20-21 na lista) —
   F20-12 recebeu apenas uma correção pontual em `QuotaGuard.next_available_at` achada
   ao rodar o baseline, não relacionada a esta dependência.
4. F20-36 e F20-37 implementados e validados com dados reais em 2026-09-27
   (`feature/f20-36-37-sites`); seguir com F20-47 a F20-50.
5. F20-49 (relatório de produtividade e custo) iniciado em 2026-09-27
   (`feature/f20-49-relatorio`): metas pré-registradas e baseline T0 (busca/cobertura do
   F20-35, custo de IA do F20-21) preenchidos com dados reais em
   `docs/pesquisas/produtividade-fase-20.md`; nenhuma chamada ao Groq feita nesta sessão
   (quota diária já esgotada pela rodada F20-21). A janela de 7 dias aberta pelo F20-35
   em `2026-09-27T00:52:16Z` só fecha em 2026-10-05 — todas as células de resultado (T7)
   ficam marcadas "pendente"/"inconclusivo" até lá, com o comando exato para preenchê-las
   documentado na §4 do relatório. Nenhum teste novo (card não muda comportamento de
   sistema).


> **Reinício da janela de sete dias (2026-09-28).** O T0 anterior (`2026-09-27T00:52:16Z`) não valia: a stack real `opportunity-radar` ficou parada depois do reprocessamento `skills-v3` e o Docker Desktop esteve desligado, então não houve operação contínua. A stack real foi religada com o código atual e um novo T0 foi capturado em `2026-09-28T00:45:09Z` (`docs/44-roadmap-fase-20/evidencias/f20-janela-7d-t0-2026-09-28.json`: 20 fontes ativas, 648 oportunidades). A janela termina em `2026-10-05T12:02Z`; a stack precisa ficar ligada sem interrupção até lá.


> **Segundo reinício da janela (2026-09-28T12:01:55Z).** O T0 de `00:45Z` também não valia: as 19 fontes ativas da stack real não tinham `schedule`, então o worker pulava todas (`NOT_SCHEDULED`) e nenhuma coleta rodou desde 2026-09-26. Com autorização do usuário, as fontes reais ganharam `schedule = 0 */3 * * *` (a cada 3 horas) e 3 fontes de teste que sobraram no banco real (`Probe board …`, `CI Ashby activation`, todas `SOURCE_NOT_FOUND`) foram desativadas. A primeira passada coletou 16 fontes com sucesso. Novo T0 em `docs/44-roadmap-fase-20/evidencias/f20-janela-7d-t0-2026-09-28b.json`; a janela termina em `2026-10-05T12:02Z`. Houve também uma queda do Docker Desktop por volta de 11:39Z, já recuperada. A API não tem endpoint para editar `schedule` — lacuna registrada.

> **Bug determinístico de `work_mode` corrigido (2026-09-28, `feature/f20-work-mode`, sem
> tocar a stack real).** O gabarito de F20-23 (`f20-23-amostra-unknown.json`) mostrou que os
> 13 casos `work_mode=UNKNOWN` eram um bug de `infer_work_mode`
> (`src/opportunity_radar/opportunities/domain.py`), não uma limitação do LLM: a função
> nunca recebia `description`, então a seção padronizada "Work Model for this Role" (várias
> vagas Nubank/Greenhouse) nunca era lida. Corrigido de forma restrita, sem scan genérico de
> `remote`/`hybrid`/`onsite` na descrição inteira (evita falso positivo com status de colega
> ou boilerplate "remote-friendly"). 11/13 casos do gabarito resolvem certo agora, 2/13
> mantidos `UNKNOWN` por decisão (evidência indireta demais), zero errado.
> `NORMALIZER_VERSION` v5→v6 (`service.py` e a fixture `tests/backend/fixtures/
> pre_f20_dump.sql`, único outro literal `v5` do repo). Suíte completa +
> `RUN_DATABASE_INTEGRATION=1` + `ruff` + `mypy` verdes. Detalhe em
> `docs/pesquisas/sugestoes-f20-23.md`. Reprocessamento oficial do acervo real fica para
> depois de `2026-10-05T12:02Z`, fora do escopo deste branch.


> **Sanidade (2026-09-28, `feature/f20-sanidade`, `79d45c0`).** Testes instáveis e `alembic check` resolvidos; detalhes em `validacao-pendente.md` §5.
