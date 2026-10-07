# F51-06 — worker: relógio por fonte, deadline e progresso

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** M
- **Risco:** alto para agenda atrasada e ownership duplicado durante cancelamento; separar deadline do passe, da fonte e do transporte.
- **Dependências:** F51-01.

## Problema, fatos e hipótese

`collect_enabled_sources` em `worker.py` captura um único instante e percorre fontes serialmente; o worker tem `max_instances=1`. No snapshot operacional, Workday levava minutos e houve skips enquanto uma instância estava ativa. Em execução posterior observada, o passe começado às 17:38:55 ainda não tinha finalizado às 17:54; isso não prova a causa de runs históricos abertos. `scripts/collect.py` já usa `asyncio.Semaphore` e `gather`, mas este card não propõe concorrência entre fontes.

Hipótese: reavaliar o relógio por fonte e dar deadline com cancelamento/cleanup observável reduz atraso sem duplicar chamadas. É necessário manter serialização por fonte/host enquanto uma operação HTTP ainda vive.

## Objetivo e exclusões

Usar `now` atual ao decidir cada fonte, acompanhar estado e concluir deadline somente depois de finalizar recursos. Não aumentar paralelismo, alterar orçamento, redesenhar lease/claim de vários hosts (F51-07/08), nem liberar slot porque apenas a coroutine externa recebeu cancelamento. Run parcial nunca fecha ausências; presenças positivas já observadas continuam válidas.

## Arquivos e símbolos existentes

- [`worker.py`](../../../src/opportunity_radar/worker.py): `collect_enabled_sources` e `run_async`.
- [`operations/service.py`](../../../src/opportunity_radar/operations/service.py): `observe_job` e anotação de execução.
- [`scheduling.py`](../../../src/opportunity_radar/acquisition/scheduling.py): cálculo de próxima execução/gate.
- [`scripts/collect.py`](../../../scripts/collect.py): exemplo existente de `Semaphore` e `gather`; não é scheduler do worker.
- O teste do worker/deadline será proposto em `tests/backend/test_worker_collection_deadline.py`; validar estrutura e fixtures disponíveis ao implementador.

## Comportamento e checkpoints

1. Injetar relógio monotônico para duração/deadline e relógio UTC para agenda/registro. Capturar horário dentro do loop, imediatamente antes de avaliar cada fonte; não reutilizar timestamp do início do passe.
2. Registrar início, source id, run id, deadline, última atividade, conclusão parcial/total e motivo terminal em logs estruturados/estado já existente. `observe_job` indica execução do job, não substitui progresso por fonte.
3. Definir limites explícitos: deadline por chamada HTTP vem do cliente/transporte; deadline por fonte cobre coleta e cleanup; prazo do passe impede novo trabalho. Respeitar menor limite vigente e registrar qual terminou.
4. No deadline, pedir cancelamento da operação e aguardar finalizadores, fechar sessão/resposta e concluir persistência do run. Enquanto transporte não confirma encerramento, manter single-flight/claim existente ativo e não começar execução substituta para a mesma fonte. Se cliente HTTP não suportar cancelamento efetivo, marcar estado “cleanup pendente” e preservar serialização até resolução.
5. Encerrar em estado parcial/timeout com página/cursor e motivo conhecidos. Não chamar fechamento de ausências; presenças positivas transacionadas podem permanecer. O ciclo segue para outras fontes elegíveis após cleanup ou ao término do prazo de passe, conforme limite definido.

## Critérios de aceite

| ID | Critério | Given / When / Then | Teste proposto e evidência |
| --- | --- | --- | --- |
| AC01 | A agenda é recalculada para cada fonte. | Dado A leva 90 s e B vence aos 30 s, quando A termina, então o worker consulta o relógio atual e executa B no mesmo passe. | `test_worker_rechecks_due_time_per_source` (proposto); relógio fake e ordem de chamadas. |
| AC02 | Cancelamento aguarda cleanup. | Dada fonte bloqueada em fake HTTP, quando deadline expira, então cancellation é solicitada e sessão/response são fechadas antes de concluir estado terminal. | `test_deadline_waits_for_http_cleanup` (proposto); eventos `cancel`, `close`, `finished` ordenados. |
| AC03 | Request vivo impede liberação de ownership. | Dado transporte que ignora cancelamento até sinal controlado, quando deadline externo vence, então claim/single-flight não é liberado nem segundo HTTP iniciado antes do sinal de término. | `test_live_transport_keeps_source_single_flight` (proposto); exatamente um request concorrente. |
| AC04 | Timeout marca parcial e não fecha ausências. | Dado que deadline ocorre antes de concluir páginas, quando finaliza o run, então estado não é completo, não usa ausências desse run para fechar vagas e preserva presenças positivas observadas. | `test_worker_timeout_preserves_positive_presence_only` (proposto); DB `_test` com vaga presente e ausente. |
| AC05 | Prazo do passe impede início tardio. | Dado próximo item devido após esgotar deadline global do passe, quando o worker volta do cleanup, então não inicia nova fonte e registra motivo “pass deadline”. | `test_pass_deadline_skips_new_source_after_cleanup` (proposto); log/estado do passe. |

## Rollout, rollback e entregáveis

Começar com relógio fake e transporte fake em testes isolados; depois ativar deadline conservador em um ambiente controlado, observando duração, timeout, cleanup pendente e fontes adiadas. Não alterar o max_instances nem permitir duas chamadas simultâneas por fonte. Rollback desativa o novo deadline configurável mantendo timeouts existentes e a serialização; nunca resolve problema liberando ownership de request ainda vivo. Entregáveis: política de limites, estado/log de progresso, cancelamento aguardado, testes determinísticos e procedimento para cleanup pendente. Testes e operação não foram executados nesta tarefa documental.

## Conferência dos critérios contra os testes (2026-10-07, sexta sessão)

Conferido critério por critério, lendo o corpo de cada teste. Caminhos relativos a
`tests/backend/`. "banco" é teste de integração com PostgreSQL real
(`RUN_DATABASE_INTEGRATION=1`); "unidade" usa dublês. Os marcados com PR #70 foram
escritos nesta sessão, sem mudança em `src`.

| AC | Teste | Tipo | Observação |
| --- | --- | --- | --- |
| AC01 | `test_worker.py::test_worker_rechecks_due_time_after_each_source` | unidade | O portão é substituído por um que sempre responde vencido; o teste confere os instantes passados a ele |
| AC02 | `acquisition/test_service.py::test_deadline_cancels_then_closes_http_resource_then_persists_terminal_state` (PR #70); `::test_source_deadline_waits_for_generator_cleanup_and_finishes_partial`; `::test_external_cancel_waits_for_live_collector_cleanup_and_logs_pending` | unidade | O teste novo confere a ordem: cancelamento, fechamento do recurso HTTP, gravação do estado terminal |
| AC03 | `acquisition/test_source_run_claim_fencing.py::test_live_transport_keeps_source_single_flight` | banco |  |
| AC04 | `acquisition/test_source_run_claim_fencing.py::test_worker_timeout_preserves_positive_presence_only`; `acquisition/test_delta_presence_resume.py::test_source_deadline_commits_positive_prefix_without_closing_absent_occurrence` | banco |  |
| AC05 | `test_worker.py::test_pass_deadline_skips_next_source_after_prior_cleanup_finishes`; `acquisition/test_collection_host_concurrency.py::test_the_pass_deadline_starts_no_new_host_once_it_has_passed` | unidade |  |

Os nomes propostos no card (`test_worker_rechecks_due_time_per_source`, `test_deadline_waits_for_http_cleanup`, `test_pass_deadline_skips_new_source_after_cleanup`, arquivo `test_worker_collection_deadline.py`) não existem; os testes reais são os da tabela. Todos os critérios têm teste. O fechamento depende da janela do F51-18.
