# F51-13 — contratos de inventário ATS, paginação, 304 e parcial

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço:** M
- **Risco:** alto para encerramento incorreto de vagas se contrato de paginação, cache ou total for interpretado genericamente.
- **Dependências:** F51-02.

## Fatos e escopo

Coletores existentes declaram capacidades diferentes: Workday pagina por offset; Teamtailor e Workable declaram `pagination=False`; há suporte condicional 304 em alguns adaptadores. A auditoria não demonstrou defeito atual. Este card documenta e testa contratos reais por adaptador; não inventa cursor para endpoint sem paginação e não refatora todos os conectores.

## Arquivos existentes

- [`domain.py`](../../../src/opportunity_radar/acquisition/domain.py): capabilities e estado do run.
- [`registry.py`](../../../src/opportunity_radar/acquisition/registry.py): registro/adaptadores.
- [`service.py`](../../../src/opportunity_radar/acquisition/service.py): consolidação e aplicação de falhas.
- [`workday.py`](../../../src/opportunity_radar/acquisition/workday.py), [`teamtailor.py`](../../../src/opportunity_radar/acquisition/teamtailor.py), [`workable.py`](../../../src/opportunity_radar/acquisition/workable.py): exemplos com paginação/capacidades distintos.
- [`test_service.py`](../../../tests/backend/acquisition/test_service.py), [`test_run_telemetry.py`](../../../tests/backend/acquisition/test_run_telemetry.py), [`test_delta_presence_resume.py`](../../../tests/backend/acquisition/test_delta_presence_resume.py).

## Tarefas

1. Criar matriz por `source_type` com: mecanismo real de paginação (cursor/offset/nenhum), condição de término, total anunciado (conhecido/desconhecido/zero), limite local, escopo do 304, cache/hash/filtros envolvidos, significado de run completo e comportamento em erro. Preencher por inspeção de cada implementação e fixture; valor não conhecido fica “não verificável”, não presumido.
2. Para APIs paginadas, verificar cursor seguinte e progresso. Detectar cursor repetido e duplicatas por identidade estável com limite configurado; encerrar com razão e parcialidade sem loop infinito. Para APIs sem paginação, um único resultado pode ser completo somente pelo contrato documentado e resposta válida; nunca fabricar cursor.
3. Tratar total ausente como desconhecido e total zero como zero apenas quando resposta válida explicitamente o declara. Workday `total` em offset zero tem ressalvas/cap; não generalizar a semântica para outros ATS.
4. Aceitar 304 somente se cache anterior for do mesmo host/escopo, filtros e versão/hash compatíveis, e revalidação cobrir o inventário declarado. 304 sem manifesto/cache compatível vira estado não verificável/parcial, nunca lista vazia.
5. Timeout, quota ou parse falho depois de evidência válida mantém presença positiva observada, mas run fica parcial e não fecha ausências. Completude de listagem permanece separada da completude do detalhe (F51-04).

## Critérios de aceite

| ID | Critério | Given / When / Then | Teste proposto e evidência |
| --- | --- | --- | --- |
| AC01 | Matriz representa capacidade verdadeira por adaptador. | Dado Workday, Teamtailor e Workable, quando matriz é gerada, então apenas Workday declara paginação por offset; os dois outros não recebem cursor inventado. | `test_adapter_inventory_contract_matrix` (proposto em `tests/backend/acquisition/test_service.py`); matriz versionada ligada à fonte de código. |
| AC02 | Total nulo e zero permanecem distintos. | Dada resposta sem total e resposta válida com total 0, quando telemetria agrega, então primeira fica desconhecida e segunda reporta zero explícito. | `test_missing_announced_total_is_not_zero` (proposto); snapshot de métricas em fixture. |
| AC03 | 304 exige cache/escopo compatível. | Dado 304 com filtro/hash correspondente, quando run revalida todo escopo declarado, então inventário anterior é reaproveitado; com filtro ou manifesto diferente, marca parcial e não fecha ausências. | `test_304_requires_matching_inventory_scope` (proposto, extensão de `test_delta_presence_resume.py`); IDs presentes e decisão de fechamento. |
| AC04 | Paginação sem progresso termina com segurança. | Dada repetição do mesmo cursor ou página duplicada acima do limite, quando adaptador avança, então requests param no limite, run fica parcial com razão e sem fechamento. | `test_repeated_cursor_is_bounded_and_partial` (proposto); contador HTTP limitado e reason code. |
| AC05 | Falha após página válida preserva positivos sem presumir negativos. | Dada página 1 com vaga X e timeout antes da próxima página, quando run consolida, então X permanece observada, ausentes não são fechadas e inventário é parcial. | `test_timeout_after_page_preserves_positive_presence` (proposto, extensão de `test_run_telemetry.py`); estado run e presença em `_test`. |

## Negativos e rollout

Não reinterpretar 304 como zero, ausência de total como zero, um lote de detalhe como inventário, nem ausência de cursor como API paginada. Não alterar limite/fechamento sem caso reproduzível. Implementar documentação e regressões por adaptador; qualquer migration só se provar lacuna de telemetria que não possa ser derivada. Integração mutável usa `_test`. Rollback reverte somente uma interpretação nova; manter dados históricos e marcar a métrica como não comparável se contrato mudou. Entregáveis: matriz, fixtures e regressões, reason codes e relatório de gaps. Não há defeito de produção provado antes da execução dos cenários.

## Conferência dos critérios contra os testes (2026-10-07, sexta sessão)

Conferido critério por critério, lendo o corpo de cada teste. Caminhos relativos a
`tests/backend/`. "banco" é teste de integração com PostgreSQL real
(`RUN_DATABASE_INTEGRATION=1`); "unidade" usa dublês. Os marcados com PR #70 foram
escritos nesta sessão, sem mudança em `src`.

| AC | Teste | Tipo | Observação |
| --- | --- | --- | --- |
| AC01 | `acquisition/test_service.py::test_adapter_inventory_contract_matrix` | unidade | Percorre a matriz, não o registro: um coletor registrado fora da matriz passaria |
| AC02 | `acquisition/test_service.py::test_missing_announced_total_is_not_zero` | unidade |  |
| AC03 | `acquisition/test_delta_presence_resume.py::test_304_requires_matching_inventory_scope`; `::test_inventory_scope_hash_changes_with_every_dimension_of_the_scope` (PR #70); `::test_304_validator_and_inventory_reuse_are_scoped_to_filters_region_and_contract` (PR #70) | banco; unidade | Os testes novos variam palavras-chave, locais, região e versão do contrato |
| AC04 | `acquisition/test_service.py::test_repeated_cursor_is_bounded_and_partial`; `::test_lever_page_of_already_read_postings_is_no_progress`; `acquisition/test_workday_collector.py::test_repeated_page_raises_instead_of_claiming_complete_board` | unidade | O motivo gravado é `PARSER_SCHEMA_CHANGED`. Só página inteira repetida é detectada |
| AC05 | `acquisition/test_delta_presence_resume.py::test_timeout_after_valid_page_keeps_presence_and_closes_nothing`; `acquisition/test_run_telemetry.py::test_timeout_after_page_preserves_positive_presence` | banco; unidade |  |

Todos os critérios têm teste; os cinco nomes propostos no card existem. O relatório de lacunas listado nos entregáveis não tem teste.

**Observado na base de dev (2026-10-07, 13:25 UTC):** a execução da Accenture (Workday) terminou `PARTIAL` com `PARSER_SCHEMA_CHANGED` e o resumo "Workday pagination repeated a page without making progress", com 1.480 de 2.000 itens. É o comportamento do AC04: limitado, parcial e sem fechamento.

**Risco relatado pelo worker que escreveu os testes, não reproduzido pelo coordenador:** duas execuções seguidas de reuso por `304` com manifesto todo revalidado saem as duas `complete=True`, e `reconcile_run_closures` na segunda fecha as vagas vistas antes, porque a execução de reuso não grava observações (`opportunities/service.py`, por volta das linhas 510 a 535). Uma execução de reuso sozinha não fecha nada, e é isso que o teste confere. Na base de dev nenhuma vaga foi fechada por execução sem itens, e as execuções `304` de hoje saem `complete=false`. Precisa de teste que reproduza e, se confirmar, de correção: é código da SPEC 51 e pede decisão do dono, porque reabre a janela. O card não fecha enquanto isso não for conferido.
