# Estado local da Fase 20 — 2026-09-26

O trabalho está no [PR #25](https://github.com/mathfrancisco/Opportunity-Radar/pull/25),
branch `feature/f20-groq-e-consolidacao`. `8be7e4c` concentra Factorial e parte de
F20-39; `973b648` corrige a seleção do cliente PostgreSQL 17 no CI. Isto não fecha a fase.

## Inventário auditável

| Card | Feito e evidência | Restante |
| --- | --- | --- |
| F20-01 | Baseline e relatórios da busca; 86 casos rotulados `aceito`; medição real refeita (like recall@10=1,0, fulltext=0,817) reconfirma o viés conhecido. | F17-03 continua "Em revisão": falta gabarito com candidatos de full-text/descrição (não só título) para `kubernetes`/`frontend`. |
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
| F20-12 | Quota Guard persistente em `b5072fd`. | Executar baseline Groq de F20-21. |
| F20-13 | Token Guard em `1c90af6`. | Sem pendência de implementação identificada. |
| F20-14 | Saída estruturada em `0ad7b34`. | Sem pendência de implementação identificada. |
| F20-15 | Sanitização PII e perfil mínimo em `0ad7b34`. | Sem pendência de implementação identificada. |
| F20-16 | Chave de cache por provedor em `e8c1600`. | Sem pendência de implementação identificada. |
| F20-17 | Adaptador Groq em `e8c1600`. | Sem pendência de implementação identificada. |
| F20-18 | Não iniciado. | Baseline de F20-21. |
| F20-19 | Telemetria sem PII em `c3e7606`. | Sem pendência de implementação identificada. |
| F20-20 | Métricas API, Overview e doctor em `b45ff84`. | Sem pendência de implementação identificada. |
| F20-21 | Harness em `2f5defd` e `94edd57`; os 26 drafts de lacuna (Java/fullstack/IA) revisados e promovidos para `eval/cases/`; `eval/cases/` tem 50 arquivos, exatamente 10 Java/10 fullstack/10 IA/10 fora de área/10 inelegíveis, versionados; excedente (2 backend + 15 fora_de_area + 9 synthetic) preservado em `eval/cases-secondary/`; `test_eval_scoring.py` verde (22 passed). | Executar baseline real no Groq (ainda não feito nesta sessão, fora do escopo/orçamento). |
| F20-22 | Não iniciado. | F20-21. |
| F20-23 | Não iniciado. | F20-22, F20-02 e F20-03. |
| F20-24 | Não iniciado. | F20-39, F20-17, F20-16 e F20-12. |
| F20-25 | Fila de homologação em `99d2067`. | Sem pendência de implementação identificada. |
| F20-26 | Recusa por versão e bloqueio de ciclo em `c9be16e`. | Sem pendência de implementação identificada. |
| F20-27 | Descoberta e modelos de ATS implementados; relatório real executado em 2026-09-26 (115 empresas, 4 ATS revelados: `homologacao-real-2026-09-26.md` §1). | Sem pendência de implementação identificada. |
| F20-28 | Coletor Workday em `7516acb`; validado com dados reais (Adobe, Workday) e homologado/coletando (Adobe) em 2026-09-26; fix de integração `f51fa77`/`676339c`. | Sem pendência de implementação identificada. |
| F20-29 | Coletor Teamtailor em `919c4b5`; validado com dados reais (Seedtag, Lingokids) e homologado/coletando 2x (Seedtag) em 2026-09-26; fix de integração `f51fa77`/`676339c`. | Sem pendência de implementação identificada. |
| F20-30 | Coletor Workable em `ae1ee79`; validado com dados reais (Workable, Wantable) e homologado/coletando (Wantable) em 2026-09-26; fix de integração `f51fa77`/`676339c`. | Sem pendência de implementação identificada. |
| F20-31 | `factorial.py` e testes de fixture em `8be7e4c`; validado com dados reais (Factorial, Agentero) e homologado/coletando (Agentero) em 2026-09-26; bug de parser corrigido em `cbe206b`; fix de integração `f51fa77`/`676339c`. | Sem pendência de implementação identificada. |
| F20-32 | Fechado — não viável em 2026-09-27. Termos de Uso da Gupy proíbem nominalmente agregar/copiar/duplicar vagas (`docs/pesquisas/termos-gupy.md`); nenhum código de coletor foi escrito. | Sem pendência de implementação — card encerrado pela revisão de termos. |
| F20-33 | Palavras-chave do perfil em `b7f432e` e `e9be146`; critério 4 confirmado (`git diff --stat b7f432e~1..e9be146 -- scripts/enable_sources.py` vazio; roteiro em `docs/44-roadmap-fase-20/rotulagem/f20-33-verificacao-criterio-4.md`). | Sem pendência de implementação identificada. |
| F20-34 | Buscas salvas em `5088e6`. | Cobrir componente Inbox/Overview. |
| F20-35 | Funil e rendimento em `102a53d`; janela de baseline de 7 dias iniciada em 2026-09-26 (T0 real salvo em `f20-search-metrics-baseline-2026-09-26.json`), termina 2026-10-04. | Medir a janela de 7 dias completa na máquina de referência (não pode terminar antes de 2026-10-04). |
| F20-36 | Descoberta limitada (`acquisition/limited_discovery.py`) e migração `20260926_0044` em `feature/f20-36-37-sites`; validada com dados reais em 2026-09-27 (ver `evidencias/sites-jobposting-2026-09-27.md`). | Sem pendência de implementação identificada. |
| F20-37 | Coletor JobPosting (`acquisition/jobposting.py`) em `feature/f20-36-37-sites`; validado com dados reais em 2026-09-27 (Qonto, Scaleway, Sonar via Lever). | Sem pendência de implementação identificada. |
| F20-38 | Agenda adaptativa e HTTP condicional em `f14bc6e`; em 2026-09-27, os 8 coletores HTTP (ashby/greenhouse/lever/remotive/workday/teamtailor/workable/factorial) passaram a enviar `If-None-Match`/`If-Modified-Since` e reportar 304/`ETag`/`Last-Modified` via `acquisition/http_conditional.py`; 304 real confirmado em Greenhouse (Lokalise) e Teamtailor (Seedtag) na pilha isolada `f20cond`, com bytes evitados medidos (19.820 e 345.111 bytes). | Medir operação real (comparação de 7 dias, depende da janela do F20-35) e orçamento por host compartilhado entre duas fontes reais do mesmo host (nenhum par do catálogo importado compartilha host ainda). |
| F20-39 | Hashes, presença por run e migração `0041` em `8be7e4c`; retomada explícita (`resume_of_run_id`, migração `0043`), manifesto 304 declarado (`CollectionTelemetry.record_manifest`) e métrica operacional (`presence_confirmed_without_reprocessing` em `/api/source-metrics`) implementados e testados; presença sem duplicação confirmada com dado real em 2026-09-26 (`make collect` 2x contra Seedtag). Em 2026-09-27: Workday passou a ler `request.cursor` e preencher `CollectedItem.cursor` (real, confirmado contra Adobe: 10 itens + 5 novos via `cursor="10"`, offset 10→15, sem repetição); variantes de parser (migração `0042`) **aceitas** com `test_a_real_parser_upgrade_appends_a_variant_instead_of_colliding`, teste de integração contra Postgres real. | Confirmar CI verde na branch; retomada explícita (`resume_of_run_id`) por uma queda real de processo (não só o cursor) ainda não exercida com um coletor de produção — os outros 3 coletores novos continuam sem paginação real. |
| F20-40 | Critérios aceitos com testes em `794b519`. | Sem pendência de implementação identificada. |
| F20-41 | Backup e manifesto AI em `a15d3b8` e `c9c291e`. | Sem pendência de implementação identificada. |
| F20-42 | Cliente e configuração Tavily implementados. | Sem pendência de implementação identificada. |
| F20-43 | Orçamento Tavily em `663c1ac`. | Sem pendência de implementação identificada. |
| F20-44 | Collector Tavily de descoberta implementado. | Sem pendência de implementação identificada. |
| F20-45 | Extração com cache em `2330f35`. | Sem pendência de implementação identificada. |
| F20-46 | Evidência e rollback de flush em `41a3ecf`, `fa93d15`, `c9c291e`. | Sem pendência de implementação identificada. |
| F20-47 | Não iniciado. | F20-17, F20-39, F20-40 e F20-25. |
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
3. Produzir F20-21 antes de F20-18, F20-22, F20-23 e F20-24.
4. F20-36 e F20-37 implementados e validados com dados reais em 2026-09-27
   (`feature/f20-36-37-sites`); seguir com F20-47 a F20-50.
