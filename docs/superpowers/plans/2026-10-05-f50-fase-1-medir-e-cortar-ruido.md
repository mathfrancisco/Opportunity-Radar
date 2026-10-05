# F50 Fase 1 — Medir e cortar ruído: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar a fase 1 da SPEC 50: linha de base de classificação por fonte (F50-01), corte de ruído na coleta (F50-04) e Hacker News sem `PARTIAL` recorrente (F50-12 item 1).

**Architecture:** Três mudanças independentes, com arquivos disjuntos. F50-12.1 troca um contador no coletor. F50-01 estende o script de medição, que continua somente leitura. F50-04 mede a parcela de vagas nas áreas-alvo por execução e, abaixo de um piso, deixa de persistir vagas novas fora da área.

**Tech Stack:** Python 3, SQLAlchemy, Alembic, pytest, Docker Compose, GitHub Actions.

**Spec:** [docs/50-spec-motor-de-busca.md](../../50-spec-motor-de-busca.md). As fases 2 a 5 ganham um plano próprio cada, escrito depois das medições desta fase.

## Global Constraints

- Base: branch `f50-motor-de-busca`, criada de `75d688b`. Workers não criam branch e não fazem commit; o coordenador faz o commit por tarefa.
- Decisões do dono (2026-10-05): Q2 piso de 30% medido nas três últimas execuções completas; Q5 áreas-alvo `SOFTWARE_ENGINEERING` e `DATA`, contrato `full-time`; Q1 detalhe Workday adiado; Q3 sim, como na spec; Q4 só investigar.
- `role_family = UNKNOWN` nunca é descartado na coleta.
- Rótulos do gold set são humanos. Nenhum script ou worker gera `valor_recomendado`.
- Nenhuma regra de conteúdo é ligada com precisão abaixo de 90% (`PRECISION_GATE`). `content_classification_v4_enabled` continua `False` nesta fase.
- Testes: `docker compose -p <único> -f compose.yaml -f compose.dev.yaml run --rm api pytest -q <alvo>`. Sem rebuild de imagem. Suíte de integração de banco só em banco terminado em `_test`, uma vez, no fim.
- O banco da stack `spec46full` é somente leitura para este plano.
- Próxima migração livre: `20261005_0062`.
- Código, comentários e mensagens de commit em inglês; documentação em português. Sem trailer `Co-Authored-By`.
- Verificação estática antes de entregar: `ruff check .` e `mypy`.

## Review Focus

1. Vaga fora da área já persistida, sem mudança de conteúdo, em fonte com filtro ligado: deve continuar recebendo observação de presença, para não ser fechada como ausente. Teste na Tarefa 3.
2. Fonte com menos de três execuções completas medidas: o filtro fica desligado. Teste na Tarefa 3.
3. Perfil ativo ausente ou sem `target_role_families`: o filtro fica desligado e nada é descartado. Teste na Tarefa 3.
4. Gold set com tipo de fonte desconhecido ou sem texto embutido: o caso é contado como não mensurável, e o script não falha. Teste na Tarefa 2.
5. Comentário do Hacker News sem empresa identificável mas com link para um ATS suportado: continua fora da fila de propostas, porque sem empresa não há item. O comportamento atual é mantido e fixado por teste na Tarefa 1.

---

### Task 1: F50-12.1 — Hacker News ignora comentário sem empresa

**Files:**
- Modify: `src/opportunity_radar/acquisition/hacker_news.py` (docstring do módulo, linhas 11-14; ramo `parsed is None`, linhas 269-273)
- Test: `tests/backend/acquisition/test_hacker_news_collector.py`
- Test: `tests/backend/acquisition/test_service.py` (só se já houver teste de execução com `hacker_news`; senão, o teste de status fica no arquivo do coletor)

**Interfaces:**
- Consumes: `CollectionTelemetry.record_skipped_item()` (já usado na linha 281).
- Produces: nenhuma interface nova.

- [ ] **Step 1: Teste que falha.** Em `test_hacker_news_collector.py`, localizar o teste que hoje espera `telemetry.invalid_items` para um comentário sem cabeçalho `Company | Role`. Alterar a expectativa: `telemetry.invalid_items == 0`, `telemetry.skipped_items == 1`, e nenhum item emitido para esse comentário. Acrescentar um caso com comentário sem empresa que contém link `boards.greenhouse.io/...`: também `skipped`, zero itens.
- [ ] **Step 2: Rodar e confirmar a falha.** `pytest -q tests/backend/acquisition/test_hacker_news_collector.py`. Esperado: falha em `invalid_items == 0`.
- [ ] **Step 3: Implementar.** No ramo `if parsed is None:` trocar `request.telemetry.record_invalid_item(...)` por `request.telemetry.record_skipped_item()`. Atualizar a docstring do módulo: comentário sem empresa ou cargo identificável é item ignorado, não inválido.
- [ ] **Step 4: Teste de status da execução.** Teste que executa `AcquisitionService.execute` com um coletor Hacker News falso (padrão dos testes existentes em `test_service.py`) cuja telemetria registra só itens ignorados e ao menos um item válido: `run.status == "SUCCEEDED"`, `run.error_code is None`, `run.items_invalid == 0`.
- [ ] **Step 5: Rodar os dois arquivos de teste; `ruff check` nos arquivos tocados.** Esperado: tudo passa.

---

### Task 2: F50-01 — Linha de base e gold set por fonte

**Files:**
- Modify: `scripts/measure_content_classification.py`
- Modify: `tests/backend/opportunities/test_measure_content_classification.py`
- Create: `docs/50-roadmap-motor-de-busca/rotulagem/f50-01-gold.json` (gold versionado; começa com os 39 casos de `docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json` convertidos, sem rótulo novo)
- Modify: `.github/workflows/pipeline.yml` (job "Backend / tests and migrations", depois de "Run backend tests")
- Create: `docs/pesquisas/f50-01-linha-de-base-classificacao.md` (escrito pelo coordenador com a saída real do script; o worker entrega o script, não o relatório)

**Interfaces:**
- Consumes: `classify_seniority_v4`, `classify_work_mode_v7`, `gate_passes`, `PRECISION_GATE` (`opportunities/content_classification.py`); `resolve_allowed_countries_v2(location, description) -> (tuple[str, ...], evidence | None)` (`opportunities/regions.py`).
- Produces:
  - `MEASURED_FIELDS = ("seniority", "work_mode", "allowed_countries")`.
  - `Case` ganha `source_type: str | None`.
  - Relatório JSON ganha `by_source_type: {<tipo>: {"rules": {<regra>: {emitted, correct, precision}}, "fields": {<campo>: {cases, unknown_after, coverage}}}}` e `fields[<campo>]["coverage"]`.
  - `--gold-text`: usa `title`, `location_text`, `trecho_descricao` e `source_type` gravados no próprio gold; não abre o banco.
  - `--per-source-type N` junto de `--sample-out`: amostra estratificada, N vagas com descrição por tipo de fonte.
  - `gate.rules_passing: list[str]`: regras com precisão ≥ 0,90 e pelo menos 20 emissões. A fase 2 lê esta lista.

- [ ] **Step 1: Testes que falham** em `test_measure_content_classification.py`:
  - `test_measure_reports_precision_and_coverage_per_source_type`: seis `Case` em dois tipos (`greenhouse`, `lever`); confere `by_source_type["greenhouse"]["rules"]` e `coverage = (cases - unknown_after) / cases`.
  - `test_allowed_countries_is_measured`: caso `field="allowed_countries"`, esperado `"BR"`, descrição com frase de país; o valor emitido é comparado como lista ordenada unida por vírgula; a regra vem de `evidence["rule"]`.
  - `test_gold_text_mode_needs_no_database`: `main(["--gold", <tmp>, "--gold-text"])` retorna 0 sem `DATABASE_URL`.
  - `test_case_without_embedded_text_is_counted_as_unmeasurable`: entrada sem `trecho_descricao` em `--gold-text` não quebra e aparece em `report["unmeasurable"]`.
  - `test_stratified_sample_takes_n_per_source_type`: 3 tipos, `--per-source-type 2`, cada tipo com no máximo 2 vagas, todas com `valor_recomendado is None`.
  - `test_rules_passing_requires_precision_and_volume`: regra com 19 emissões corretas fica fora; com 20 emissões e 18 corretas entra.
  - `test_versioned_gold_runs`: `main(["--gold", "docs/50-roadmap-motor-de-busca/rotulagem/f50-01-gold.json", "--gold-text"])` retorna 0.
- [ ] **Step 2: Rodar e confirmar a falha.**
- [ ] **Step 3: Implementar no script.**
  - `_fetch_rows`: acrescentar `allowed_countries` e o tipo de fonte da vaga. Descobrir a junção lendo `opportunities/models.py` (ocorrência de fonte → `source_definition.source_type`); uma vaga com várias fontes usa a mais antiga.
  - `classify`: ramo `allowed_countries` com `resolve_allowed_countries_v2(case.location_text, case.description)`.
  - `measure`: acumular por `source_type` (`None` vira `"unknown"`).
  - `build_label_sample`: gravar `source_type` em cada entrada; estratificar quando `per_source_type` vier.
  - `stats["unknown_before"]` continua contando todos os casos só para os campos do gold antigo; documentar no relatório que o gold novo não é restrito a campos `UNKNOWN`.
  - O script continua só com `SELECT`.
- [ ] **Step 4: Gold versionado.** Converter os 39 casos para o arquivo novo, mantendo `valor_recomendado` e `evidencia` como estão. Onde não houver `trecho_descricao`, usar `evidencia` como texto e marcar `"texto": "evidencia"` na entrada. Não inventar rótulo nem tipo de fonte.
- [ ] **Step 5: CI.** Novo passo em `pipeline.yml`: `python scripts/measure_content_classification.py --gold docs/50-roadmap-motor-de-busca/rotulagem/f50-01-gold.json --gold-text`. Sem `--check-gate`: o gold ainda não tem 200 vagas rotuladas.
- [ ] **Step 6: Rodar** `pytest -q tests/backend/opportunities/test_measure_content_classification.py`, `ruff check scripts tests/backend/opportunities`, `mypy`.

---

### Task 3: F50-04 — Corte de ruído na coleta

**Files:**
- Create: `migrations/versions/20261005_0062_source_run_target_area_counts.py` (`down_revision` = revisão de `20261004_0061`)
- Modify: `src/opportunity_radar/acquisition/models.py` (`SourceRunModel`)
- Modify: `src/opportunity_radar/acquisition/domain.py` (`SourceRun`)
- Modify: `src/opportunity_radar/acquisition/repository.py`
- Modify: `src/opportunity_radar/acquisition/service.py` (`execute`, `_persist_item`, `_copy_run`)
- Modify: `src/opportunity_radar/platform/config.py`
- Modify: `src/opportunity_radar/matching/service.py` e `matching/repository.py` (`pending_evaluation_ids`)
- Modify: `.env.example` (variável nova)
- Test: `tests/backend/acquisition/test_service.py`, `tests/backend/matching/test_evaluation_queue.py`

**Interfaces:**
- Consumes: `classify_role_family(title=..., departments=...)` e `departments_from_metadata(metadata)` (`opportunities/role_family.py`); `RoleFamily.UNKNOWN`; `profile.snapshot.preferences.target_role_families` (mesmo acesso de `MatchingService._target_role_families`, `matching/service.py:459`).
- Produces:
  - Colunas `source_run.items_target_area` e `source_run.items_off_target`, `Integer`, anuláveis (nulo = execução anterior à medição).
  - `Settings.collection_target_area_floor: float = 0.30` (env `COLLECTION_TARGET_AREA_FLOOR`; `0` desliga o filtro; validado em `[0, 1]`).
  - `AcquisitionRepository.target_area_share(source_id, *, runs: int = 3) -> float | None`: `sum(items_target_area) / sum(items_target_area + items_off_target)` das últimas `runs` execuções com `complete = true` e contadores não nulos; `None` se houver menos de `runs` execuções ou soma zero. `UNKNOWN` fica fora do numerador e do denominador.
  - `AcquisitionService.__init__` ganha `target_role_families: Callable[[], tuple[str, ...]] | None = None` e `target_area_floor: float = 0.0`. Os pontos de montagem do serviço (worker, API, scripts) passam o perfil ativo e o valor de `Settings`.
  - `_persist_item(..., persist_new: bool = True)`: com `False`, item já existente segue o caminho atual (observação de presença, retorna `False`); item novo não é gravado e retorna `False`.

- [ ] **Step 1: Testes que falham** em `test_service.py` (usar os coletores e repositórios falsos já existentes no arquivo):
  - `test_run_records_target_area_counts`: três itens (título de engenharia, título de vendas, título sem regra); `items_target_area == 1`, `items_off_target == 1`.
  - `test_source_above_floor_persists_every_item`: parcela 0,5 e piso 0,3; o item de vendas novo é persistido.
  - `test_source_below_floor_skips_new_off_target_items`: parcela 0,1; o item de vendas novo não é persistido e conta em `items_skipped`; os itens de engenharia e `UNKNOWN` são persistidos.
  - `test_filter_keeps_presence_of_existing_off_target_item`: item de vendas já persistido e inalterado recebe observação de presença com o filtro ligado.
  - `test_filter_off_with_fewer_than_three_measured_runs`: `target_area_share` retorna `None`; nada é descartado.
  - `test_filter_off_without_target_role_families`: perfil sem áreas; nada é descartado e os contadores ficam nulos.
  - `test_floor_zero_disables_filter`.
  - `test_filtered_run_is_still_complete`: itens descartados contam em `items_seen`, então `evaluate_completeness` não muda.
- [ ] **Step 2: Teste de integração do repositório** (`target_area_share`): três execuções completas 2/10, 3/10, 1/10 → `0.2`; uma execução incompleta no meio é ignorada; duas execuções medidas → `None`.
- [ ] **Step 3: Teste da fila** em `test_evaluation_queue.py`: com perfil de áreas-alvo `SOFTWARE_ENGINEERING` e `DATA`, vaga `SALES` sem avaliação não entra em `pending_evaluation_ids`; vagas `SOFTWARE_ENGINEERING` e `UNKNOWN` entram. Perfil sem áreas-alvo: comportamento atual.
- [ ] **Step 4: Rodar e confirmar as falhas.**
- [ ] **Step 5: Migração e modelos.** Duas colunas anuláveis; `downgrade` remove as duas. `SourceRun` ganha os dois contadores e `record_target_area(*, target: int = 0, off_target: int = 0)`; `_copy_run` copia os dois.
- [ ] **Step 6: Serviço.** No início de `execute`, depois de resolver a fonte: `targets = frozenset(self._target_role_families())` se o callable existir; `filter_active = bool(targets) and floor > 0 and share is not None and share < floor`. No laço, antes de `_persist_item`: classificar o título; `UNKNOWN` não conta; contar alvo ou fora; chamar `_persist_item(..., persist_new=not (filter_active and off_target))`. Fonte `manual` nunca é filtrada.
- [ ] **Step 7: Fila de avaliação.** `pending_evaluation_ids` recebe as áreas-alvo e restringe a `role_family IN (alvos) OR role_family = 'UNKNOWN'` quando a lista não é vazia. Conferir como `role_family` desconhecido é gravado (`'UNKNOWN'` ou nulo) em `opportunities/models.py` e cobrir os dois se existirem.
- [ ] **Step 8: Rodar** os dois arquivos de teste, o round trip da migração (`alembic upgrade head && alembic downgrade -1 && alembic upgrade head` em banco `_test`), `ruff check .`, `mypy`.

---

## Depois das três tarefas (coordenador)

- [ ] Commit por tarefa, com caminhos explícitos.
- [ ] Rodar a medição do F50-01 contra o banco `spec46full` (somente `SELECT`) e escrever `docs/pesquisas/f50-01-linha-de-base-classificacao.md` com a saída literal.
- [ ] Exportar a amostra estratificada sem rótulo (`--sample-out ... --per-source-type 50`) para o dono rotular. Enquanto o gold não tiver 200 vagas rotuladas, F50-02 não liga nenhuma regra.
- [ ] Revisão de bugs do diff da fase com `cavecrew-reviewer`.
- [ ] Suíte completa uma vez, mais integração em banco `_test`.
- [ ] Atualizar o §1 e o status dos cards na SPEC 50.
