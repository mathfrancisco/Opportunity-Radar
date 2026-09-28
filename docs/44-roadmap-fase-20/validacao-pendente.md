# Fase 20 — o que falta validar de verdade

Atualizado em 2026-09-28. Branch `feature/f20-groq-e-consolidacao`, CI verde em `77ff56b`
(backend, migrações, frontend, Compose E2E e Playwright).

"Verde na CI" prova o comportamento com fakes e fixtures. Este documento lista o que
**ainda não foi provado com dados, uso ou tempo reais**, card por card, com o teste que
fecha cada lacuna. Nada aqui é trabalho de código novo, exceto onde indicado.

## 1. Restrições que definem a ordem

| Restrição | Efeito |
| --- | --- |
| Janela de sete dias iniciada em `2026-09-28T00:45:09Z` na stack real `opportunity-radar` (T0 em `evidencias/f20-janela-7d-t0-2026-09-28.json`) | F20-35, F20-38 e F20-49 só fecham depois de `2026-10-05T00:45Z`. A stack não pode parar, ser reconstruída nem reiniciada até lá. |
| Cota diária do Groq ≈ 170k tokens; uma rodada de 50 casos custa ≈ 75k | No máximo duas rodadas completas por dia. |
| Stack real roda o código de `0d55de6` (sem F20-24) | F20-24 só entra na stack real depois da janela. |

## 2. Validações com o Groq real

Todas usam a stack isolada, nunca `opportunity-radar`.

| Card | O que ainda não foi provado | Teste que fecha | Critério de aceite |
| --- | --- | --- | --- |
| F20-18 | **Resolvido (2026-09-28).** Rodada real feita, parou em 10/50 casos (quota diária compartilhada com F20-22/F20-23; `v2` custa ~2-3× mais tokens que o assumido). No `reserved`, `v2` já piora `completed_rate` e custo de token — decisão: manter `v1`. Ver `docs/pesquisas/prompt-v2-vs-v1.md`. Rodada completa dos 50 casos fica para uma janela sem concorrência de quota. | Rodar `eval_analysis.py --prompt v2 --model openai/gpt-oss-120b --baseline evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json` (comando completo em `docs/pesquisas/prompt-v2-vs-v1.md`) | `coverage` sobe de 0; português sobe de ≈0,11; `inventions` continua 0; nenhum critério da divisão `reserved` piora. Só então `ai_analysis_prompt=v2` vira padrão. |
| F20-22 | Qual modelo usar por tarefa | Rodar os mesmos 50 casos em 20B e Qwen (120B já tem baseline), um modelo por dia; plano no card F20-22 | Tabela de qualidade × latência × tokens por tarefa; decisão registrada e roteamento configurado. |
| F20-23 | A IA reduz UNKNOWN sem sobrescrever valores determinísticos | Rodar a classificação assistida no acervo anonimizado e depois no real | UNKNOWN de senioridade cai de 50,62% (328/648) rumo à metade (meta do F17-06); nenhum valor determinístico alterado. |
| F20-24 | **Resolvido (2026-09-28)** para a reserva interativa: teto reduzido do worker (`ceiling_requests=3`) gerou `skipped_budget=6` real, e a análise pedida pela UI (`MatchingService.analyze`, sem `ceiling_requests`) concluiu `AI_COMPLETED` no mesmo momento. Ver `docs/44-roadmap-fase-20/evidencias/analise-sob-orcamento-f20-24-2026-09-27.md` §5. Ainda em aberto: amostra de aging (`worker_analyze_aging_sample_ratio`) sob Groq real. | Worker com `AI_INTERACTIVE_RESERVE_REQUESTS=100` até `skipped_budget` aparecer; nesse momento, pedir uma análise pela UI | Análise pela UI conclui; `platform.ai_quota_usage` mostra o worker parado no teto e a fila por valor processando primeiro os itens de maior veredito/prioridade. |
| F20-12/13 | Guardas de cota e tokens sob uso real prolongado | Coberto pelas rodadas acima | Nenhuma espera maior que a virada da janela (bug de ~10h corrigido em `21c5ec8`); 429 < 2%. |

## 3. Validações que dependem da janela de sete dias

Executar depois de `2026-10-05T00:45Z`, na stack real, antes de reconstruí-la.

| Card | O que falta | Como medir |
| --- | --- | --- |
| F20-35 | Critério 4: rendimento e cobertura em sete dias de operação real | `GET /search-metrics?window=7d` e comparação com o T0 |
| F20-38 | Comparação real de 7 dias da agenda adaptativa; orçamento por host compartilhado entre fontes reais | Métricas de fonte e `acquisition.source_run` do período; incluir duas fontes no mesmo host antes de medir o orçamento compartilhado |
| F20-49 | Coluna T7 do relatório de produtividade e custo | Os cinco comandos da §4 de `docs/pesquisas/produtividade-fase-20.md` |

Depois da medição: reconstruir a stack real com o código atual (inclui F20-24) e conferir
`/health`, `doctor` e uma coleta.

## 4. Validações com dados reais ainda abertas

| Card | Lacuna | Teste que fecha |
| --- | --- | --- |
| F20-01 / F17-03 | O gabarito veio de busca por título, o que favorece `like`; `kubernetes` e `frontend` não têm gabarito | Montar candidatos por full-text (não por título), rotular e reexecutar `eval_search.py --mode both` |
| F20-02 | Curadoria e reprocessamento `skills-v3` feitos; a meta de UNKNOWN de senioridade (F17-06) não foi atingida | Depende do F20-23 |
| F20-39 | A retomada por `resume_of_run_id` depois de uma queda real só está coberta por fakes; o cursor real foi provado só com cursor explícito | Interromper uma coleta Workday real no meio (matar o worker), confirmar a execução `PARTIAL` e retomar com `resume_of_run_id` |
| F20-38/39 | Os bytes evitados foram medidos com `curl`, não pelo coletor em operação contínua | Sai da janela de sete dias (checkpoints com ETag em produção) |
| F20-36 | `CompanySource.endpoint` gravado é a página onde o ATS foi achado, não o board | Homologação humana corrige o endpoint antes de ativar as 3 fontes achadas (Airbyte, Anthropic, Apollo GraphQL) |
| F20-47 | O E2E no navegador roda com fakes | Opcional: percurso manual na stack real depois da janela |

## 5. Verificações de sanidade que ninguém rodou

- **Testes instáveis:** `test_revisits_before_normalization_keep_per_run_observations` e um teste Tavily falharam com ordem aleatória e passaram com ordem fixa. Causa provável: banco de teste compartilhado sem limpeza (achado do F20-24). Rodar `pytest -p randomly` três vezes e corrigir o isolamento.
- **Alembic (F20-05):** o card diz "a conferir na validação final". Conferir `alembic check` na head atual.
- **Frontend:** o E2E cobre as telas principais; Overview e Sources com os ATS novos não têm teste visual.
- **Segurança:** falha externa do GitGuardian no PR #25 sem causa confirmada. Rotacionar a chave Groq usada nas rodadas.

## 6. Cards ainda não implementados

| Card | Estado em 2026-09-28 |
| --- | --- |
| F20-22 | Preparação sem Groq em andamento (`feature/f20-22-benchmark`) |
| F20-23 | Implementação sem Groq em andamento (`feature/f20-23-classificacao`) |
| F20-50 | Último card. Só começa depois das seções 2 a 5 |

## 7. Ordem recomendada

1. ~~F20-18 (v2 × v1)~~ — resolvido em 2026-09-28 (manter `v1`; ver §2). F20-22 (20B), depois F20-22 (Qwen) e decisão seguem pendentes.
2. F20-23 no acervo real, com o modelo escolhido; ~~medição de F20-24~~ — reserva interativa resolvida em 2026-09-28, amostra de aging ainda pendente (ver §2).
3. Sanidade da seção 5 (testes instáveis, `alembic check`).
4. F20-39: queda real e retomada.
5. Depois de `2026-10-05T00:45Z`: T7 de F20-35/38/49, reconstrução da stack real.
6. F20-01 com gabarito full-text.
7. F20-50.
