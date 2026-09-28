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
| Cota diária do Groq ≈ 170k tokens, compartilhada com o worker da stack real (`AI_ENABLED=true`, ~2 chamadas por minuto em 2026-09-28); uma rodada de 50 casos custa ≈ 75k com `v1` e bem mais com `v2` | Na prática, uma rodada por dia, iniciada logo após a virada UTC, e checando o uso do dia antes. |
| Stack real roda o código de `0d55de6` (sem F20-24) | F20-24 só entra na stack real depois da janela. |

## 2. Validações com o Groq real

Todas usam a stack isolada, nunca `opportunity-radar`.

| Card | O que ainda não foi provado | Teste que fecha | Critério de aceite |
| --- | --- | --- | --- |
| F20-18 | **Resolvido (2026-09-28).** Rodada real feita, parou em 10/50 casos (a cota diária da chave é compartilhada com o worker da stack real `opportunity-radar`, que analisa vagas continuamente com `AI_ENABLED=true` durante a janela de sete dias; F20-22 e F20-23 não chamaram o Groq. `v2` custa ~2-3× mais tokens que o assumido). No `reserved` (só 2 casos), `v2` piorou `completed_rate` e custo de token. Decisão provisória: manter `v1`; a amostra é pequena demais para descartar o `v2`. Ver `docs/pesquisas/prompt-v2-vs-v1.md`. Rodada completa dos 50 casos fica para uma janela sem concorrência de quota. | Rodar `eval_analysis.py --prompt v2 --model openai/gpt-oss-120b --baseline evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json` (comando completo em `docs/pesquisas/prompt-v2-vs-v1.md`) | `coverage` sobe de 0; português sobe de ≈0,11; `inventions` continua 0; nenhum critério da divisão `reserved` piora. Só então `ai_analysis_prompt=v2` vira padrão. |
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

- **Testes instáveis — Resolvido (2026-09-28), branch `feature/f20-sanidade`.** Reproduzido
  com ordem aleatória (conftest com `RANDOM_ORDER_SEED`, já que nem `pytest-randomly` nem
  `pytest-random-order` estavam instalados) em oito rodadas completas sobre o mesmo banco
  nunca truncado (ordem padrão + sementes 1, 42, 999, 777, 31415, 2, 5 — 981 aprovados, 10
  ignorados, 0 falhas em todas). Causas raiz encontradas (todas por linha de código, não
  por "instabilidade genérica"):
  - `tests/backend/dashboard/test_metrics.py`: `_source()` cria por padrão uma fonte
    `enabled=True`, `schedule="* * * * *"`, `source_type="greenhouse"` já homologada, e
    seis testes nunca a apagavam — exatamente o que `worker.collect_enabled_sources`
    (chamado pelo soak) tenta coletar. É a causa direta de `test_soak` falhar com
    "collector not registered: greenhouse" dias depois, sem nenhuma relação de código com
    o teste que a criou. Corrigido com um `_cleanup()` que desfaz a fonte e tudo o que ela
    gerou (run, raw item, ocorrência, observação, resultado de normalização), chamado em
    `finally` pelos seis testes.
  - `tests/backend/test_source_probe_integration.py::test_probe_refuses_stale_enabled_and_manual_sources`
    também deixava uma fonte `greenhouse` `enabled=True`/confirmada permanente pela mesma
    razão; agora apagada em `finally`.
  - `tests/backend/acquisition/test_delta_presence_resume.py::test_revisits_before_normalization_keep_per_run_observations`
    fazia `select(SourceOccurrenceObservationModel)` sem filtro nenhum, assumindo ser dona
    da tabela inteira — falha com qualquer linha alheia presente. Filtrado por
    `source_run_id` dos dois runs que o teste realmente criou.
  - `tests/backend/acquisition/test_tavily_proposals.py::test_catalog_owner_resolves_real_tavily_collector_item_without_company_name`
    fazia `session.scalar(select(...).where(company_source_id IS NOT NULL AND
    source_type == "greenhouse"))` sem escopo — `tests/backend/dashboard/test_queries.py`
    (`test_list_source_health_filters_by_status_proposed` e
    `test_list_source_health_orders_by_company_priority`) cria permanentemente outras
    linhas com esse mesmo par, e `session.scalar()` explode com `MultipleResultsFound`
    dependendo da ordem. Filtrado por `configuration["company_name"]` (único por teste,
    já como os outros testes do arquivo fazem no `_purge()`).
  - **F20-24, "leftovers ordenados por valor" (a nota do card): confirmado e mais amplo do
    que o card registrava.** `tests/backend/matching/test_analysis_queue.py` tinha pelo
    menos quatro testes que semeavam avaliações `HIGH_PRIORITY`/`score` alto e nunca as
    concluíam nem as apagavam (`test_pending_analysis_reserves_aging_sample` — o próprio
    "retiro" nunca commitava, então nunca acontecia de verdade —,
    `test_the_job_defers_a_pending_id_when_the_worker_ceiling_is_exhausted`, e dois testes
    de enumeração pura de fila que nunca chamavam `analyze_pending`). Qualquer uma dessas
    20+ linhas, deixada pendente, permanece no topo da fila (por prioridade/score) pelo
    resto da execução e rouba uma vaga de lote de um teste posterior — reproduzido contra
    `test_the_job_analyzes_a_bounded_batch_and_commits_each_result`. Corrigido com uma
    fixture `autouse` no arquivo que, ao final de cada teste, "aposenta" (marca
    `AI_COMPLETED`) qualquer avaliação nova que ainda esteja pendente — resolve para
    qualquer teste futuro do arquivo, não só os quatro encontrados.
    `tests/backend/dashboard/test_queries.py::test_overview_counts_reflect_the_catalogue_and_flag_the_missing_pipeline`
    tinha o mesmo problema (empresa `high`, `HIGH_PRIORITY`, nunca concluída) e foi
    corrigido da mesma forma, no padrão já usado por outro teste do próprio arquivo.
  - `tests/backend/matching/test_repository.py::test_assessment_persistence_is_idempotent_and_keeps_factors`
    usava `input_hash="a" * 64` fixo — `SqlAlchemyMatchingRepository.add()` deduplica só
    por `input_hash`, globalmente, sem escopo por oportunidade, então a segunda vez que
    este teste específico roda contra o mesmo banco (nunca truncado) ele encontra a
    própria linha de uma execução anterior e compara contra um snapshot antigo. Trocado
    por `uuid4().hex + uuid4().hex`, como o resto da suíte já faz.
  - `tests/backend/dashboard/test_saved_searches.py`: três testes chamavam `new_count()`
    sem `all_areas`/`area`, e `new_count` cai para o `target_role_families` do *perfil
    ativo* quando nenhum dos dois vem no filtro — um valor que
    `tests/backend/profile/test_profile_preservation.py` deixa não-vazio permanentemente
    neste mesmo banco. Corrigido passando `"all_areas": True`, igualando o comportamento
    de `list_opportunity_inbox` (que não aplica esse fallback).
  - Ferramenta: `tests/backend/conftest.py` ganhou um `pytest_collection_modifyitems`
    opcional, ativado só por `RANDOM_ORDER_SEED=<n>` (nenhum efeito por padrão, `pytest -q`
    da CI continua determinístico), para reproduzir isolamento sem depender de instalar
    `pytest-randomly`.
- **Alembic (F20-05) — Resolvido (2026-09-28).** `alembic check` nunca tinha rodado de
  verdade: `migrations/env.py` não passava `include_schemas=True` para
  `context.configure()`, então a comparação só via o schema `public` (vazio) e reportava o
  banco inteiro como "adicionado" mesmo em head. Corrigido, e isso revelou três drifts
  reais, todos sem nenhuma migração pendente de fato:
  - `platform.ai_quota_usage` e `platform.ai_call_record` são `sa.Table` numa `MetaData`
    própria (deliberadamente fora do ORM — ver seus módulos); excluídos da comparação via
    `include_object`.
  - `ix_opportunity_embedding_hnsw` é criado por SQL bruto (`CREATE INDEX ... USING hnsw
    (embedding vector_cosine_ops)`, sem forma portável em `sa.Index`); excluído da mesma
    forma.
  - `Company.normalized_name`, `CompanyAlias.normalized_alias`,
    `Opportunity.allowed_countries` e `Opportunity.search_document` tinham índices reais no
    banco (criados por migração) que o modelo nunca declarava — `alembic check` só os viu
    depois do `include_schemas=True` acima. Declarados explicitamente nos modelos, com o
    nome exato já existente no banco; nenhuma migração nova foi necessária (banco e modelo
    já concordam, só faltava o modelo dizer isso).
  - Um quarto candidato a drift (`raw_item_id` das duas tabelas de ocorrência, `RESTRICT`
    vs `CASCADE` trocados entre modelo e banco) foi investigado e **descartado**: escrever
    a migração "corrigindo" o modelo quebrou
    `tests/backend/acquisition/test_tavily_proposals.py` (seu `_purge()` depende do
    `CASCADE` que já existe no banco desde a migração `20260926_0041`). O código do
    modelo, não o banco, estava desatualizado — corrigido nos dois lugares de
    `opportunities/models.py` para bater com o banco real, sem nova migração.
  - `alembic heads` confirma uma única head, `20260926_0052` — nenhuma migração nova nesta
    passada.
- **Frontend:** o E2E cobre as telas principais; Overview e Sources com os ATS novos não têm teste visual.
- **Segurança:** falha externa do GitGuardian no PR #25 sem causa confirmada. Rotacionar a chave Groq usada nas rodadas.

## 6. Cards ainda não implementados

| Card | Estado em 2026-09-28 |
| --- | --- |
| F20-22 | Preparação sem Groq em andamento (`feature/f20-22-benchmark`) |
| F20-23 | Implementação sem Groq concluída (`feature/f20-23-classificacao`); falta a medição de precisão no acervo real (seção 2, linha F20-23, e item 2 da seção 7) |
| F20-50 | Último card. Só começa depois das seções 2 a 5 |

## 7. Ordem recomendada

1. ~~F20-18 (v2 × v1)~~ — resolvido em 2026-09-28 (manter `v1`; ver §2). F20-22 (20B), depois F20-22 (Qwen) e decisão seguem pendentes.
2. F20-23 no acervo real, com o modelo escolhido; ~~medição de F20-24~~ — reserva interativa resolvida em 2026-09-28, amostra de aging ainda pendente (ver §2).
3. ~~Sanidade da seção 5 (testes instáveis, `alembic check`)~~ — resolvido em 2026-09-28 (branch `feature/f20-sanidade`, ver §5).
4. F20-39: queda real e retomada.
5. Depois de `2026-10-05T00:45Z`: T7 de F20-35/38/49, reconstrução da stack real.
6. F20-01 com gabarito full-text.
7. F20-50.
