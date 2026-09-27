# Estado local da Fase 20 — 2026-09-26

O trabalho está no [PR #25](https://github.com/mathfrancisco/Opportunity-Radar/pull/25),
branch `feature/f20-groq-e-consolidacao`. `8be7e4c` concentra Factorial e parte de
F20-39; `973b648` corrige a seleção do cliente PostgreSQL 17 no CI. Isto não fecha a fase.

## Inventário auditável

| Card | Feito e evidência | Restante |
| --- | --- | --- |
| F20-01 | Baseline e relatórios da busca. | Marcar relevância humana em acervo real. |
| F20-02 | `skills-v2` em `e46b755`; UNKNOWN 50,62%. | Curar o acervo real. |
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
| F20-21 | Harness em `2f5defd` e `94edd57`. | Rotular casos, revisar 41 descrições e executar baseline Groq. |
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
| F20-32 | Não iniciado. | Implementar coletor Gupy. |
| F20-33 | Palavras-chave do perfil em `b7f432e` e `e9be146`. | Fazer verificação manual do critério 4. |
| F20-34 | Buscas salvas em `5088e6`. | Cobrir componente Inbox/Overview. |
| F20-35 | Funil e rendimento em `102a53d`; janela de baseline de 7 dias iniciada em 2026-09-26 (T0 real salvo em `f20-search-metrics-baseline-2026-09-26.json`), termina 2026-10-04. | Medir a janela de 7 dias completa na máquina de referência (não pode terminar antes de 2026-10-04). |
| F20-36 | Descoberta limitada (`acquisition/limited_discovery.py`) e migração `20260926_0044` em `feature/f20-36-37-sites`; validada com dados reais em 2026-09-27 (ver `evidencias/sites-jobposting-2026-09-27.md`). | Sem pendência de implementação identificada. |
| F20-37 | Coletor JobPosting (`acquisition/jobposting.py`) em `feature/f20-36-37-sites`; validado com dados reais em 2026-09-27 (Qonto, Scaleway, Sonar via Lever). | Sem pendência de implementação identificada. |
| F20-38 | Agenda adaptativa e HTTP condicional em `f14bc6e`; confirmado em 2026-09-26 que os 4 coletores novos (F20-28 a F20-31) também não enviam ETag/If-Modified-Since ainda. | Medir operação real (comparação de 7 dias) e cabear condicionais HTTP nos coletores de produção (card futuro). |
| F20-39 | Hashes, presença por run e migração `0041` em `8be7e4c`; variantes de parser com migração `0042` (local, sem aceite); retomada explícita (`resume_of_run_id`, migração `0043`), manifesto 304 declarado (`CollectionTelemetry.record_manifest`) e métrica operacional (`presence_confirmed_without_reprocessing` em `/api/source-metrics`) implementados e testados; presença sem duplicação confirmada com dado real em 2026-09-26 (`make collect` 2x contra Seedtag). | Confirmar CI verde na branch; retomada real por cursor exige um coletor de produção que emita `CollectedItem.cursor` (nenhum dos 4 novos faz isso hoje); medição de bytes evitados fica fora do CI (depende de coletor real com condicionais). |
| F20-40 | Critérios aceitos com testes em `794b519`. | Sem pendência de implementação identificada. |
| F20-41 | Backup e manifesto AI em `a15d3b8` e `c9c291e`. | Sem pendência de implementação identificada. |
| F20-42 | Cliente e configuração Tavily implementados. | Sem pendência de implementação identificada. |
| F20-43 | Orçamento Tavily em `663c1ac`. | Sem pendência de implementação identificada. |
| F20-44 | Collector Tavily de descoberta implementado. | Sem pendência de implementação identificada. |
| F20-45 | Extração com cache em `2330f35`. | Sem pendência de implementação identificada. |
| F20-46 | Evidência e rollback de flush em `41a3ecf`, `fa93d15`, `c9c291e`. | Sem pendência de implementação identificada. |
| F20-47 | Não iniciado. | F20-17, F20-39, F20-40 e F20-25. |
| F20-48 | Não iniciado. | F20-41, F20-12 e F20-19. |
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
   `docs/44-roadmap-fase-20/evidencias/homologacao-real-2026-09-26.md`); implementar
   F20-32.
3. Produzir F20-21 antes de F20-18, F20-22, F20-23 e F20-24.
4. F20-36 e F20-37 implementados e validados com dados reais em 2026-09-27
   (`feature/f20-36-37-sites`); seguir com F20-47 a F20-50.
