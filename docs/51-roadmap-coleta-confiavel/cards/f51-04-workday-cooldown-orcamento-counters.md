# F51-04 — Workday: cooldown 429, orçamento e contadores

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** M
- **Risco:** alto para tráfego duplicado ou quota excedida em workers concorrentes; reserva persistente deve preceder toda chamada externa.
- **Dependências:** F51-03.

## Problema e evidência

F50-03 registra que o cooldown por 429 não persiste, o orçamento pode não ser aplicado à chamada de detalhe e os contadores específicos de detalhe ficam em memória. O código atual já possui estado de orçamento por host e persistência de cooldown (`HostBudgetStateModel`/repositório), além de `CollectionTelemetry.detail_requests`, `detail_failures` e `detail_skipped`; a integração de detalhe com esses contratos precisa ser verificada. A telemetria em memória não é evidência durável após reinício.

## Objetivo e limites

Garantir orçamento atômico compartilhado entre processos, respeitar `Retry-After` de forma persistente e expor contagens duráveis por fonte/run. Não elevar teto, criar orçamento concorrente separado, repetir 429 em loop, nem transformar detalhe em prova de inventário. Uma tentativa que iniciou transporte consome quota, mesmo se falhar; bloqueio antes do transporte não consome request.

## Arquivos e interfaces existentes

- [`workday.py`](../../../src/opportunity_radar/acquisition/workday.py): transporte de detalhe e parsing de resposta.
- [`scheduling.py`](../../../src/opportunity_radar/acquisition/scheduling.py): gate e decisão de cooldown.
- [`repository.py`](../../../src/opportunity_radar/acquisition/repository.py): `record_host_budget_usage` e transação de orçamento por host.
- [`models.py`](../../../src/opportunity_radar/acquisition/models.py): `HostBudgetStateModel` e `SourceRunModel`.
- [`domain.py`](../../../src/opportunity_radar/acquisition/domain.py): `CollectionTelemetry` com contadores de detalhe em memória.
- [`test_host_budget_scheduling.py`](../../../tests/backend/acquisition/test_host_budget_scheduling.py), testes novos de persistência marcados como propostos.

## Tarefas executáveis

1. Antes de alterar schema, mapear se os contadores genéricos de run já persistem detalhe separadamente. Se não, propor migração aditiva para novas métricas: legado sem observação permanece `NULL`/desconhecido; zero só representa métrica nova efetivamente observada sem ocorrências. Manter leitura compatível com runs anteriores e nunca sobrescrever totais genéricos.
2. Criar operação transacional que reserva uma unidade do orçamento do hostname antes de abrir HTTP. A reserva/consumo deve ser indivisível entre workers; em falha do processo após reserva, registrar tentativa consumida e permitir auditoria, sem “devolver” quota que talvez tenha chegado ao servidor.
3. Em 429, interpretar `Retry-After` (segundos ou data HTTP válida), guardar `cooldown_until` persistente e motivo, e consultar esse horário antes da próxima reserva. Resposta malformada usa fallback já configurado ou bloqueia conservadoramente; não inventar espera menor.
4. Definir contadores duráveis: `detail_requests` = transportes iniciados; `detail_failures` = respostas/parse falhos; `detail_skipped` = elegíveis impedidos antes do transporte, com motivo estruturado quota/cooldown/cap/ineligível. Documentar 304 sem classificá-lo como descrição recebida.
5. Atualizar transação e telemetria no mesmo fluxo de run, mantendo associação por `source_id` e `run_id`. Logs não podem gravar tokens, cookies ou headers sensíveis.

## Critérios de aceite

| ID | Critério | Given / When / Then | Teste proposto e evidência |
| --- | --- | --- | --- |
| AC01 | `Retry-After` impede request antes do vencimento e permite no instante devido. | Dado fake HTTP 429 com `Retry-After: 120` às 12:00, quando nova sessão roda às 12:01, então faz zero HTTP; quando roda às 12:02, então pode retomar após nova reserva. | `test_workday_429_retry_after_persists_across_sessions` (proposto); registros de request e `cooldown_until`. |
| AC02 | Dois workers não excedem a última unidade disponível. | Dado saldo compartilhado 1, quando dois workers tentam detalhe simultaneamente, então exatamente um inicia HTTP e o consumo persistido final é 1. | `test_workday_budget_reservation_is_atomic_across_workers` (proposto); eventos sincronizados e linha de orçamento. |
| AC03 | Cooldown continua efetivo ao virar a janela de consumo. | Dado 429 cujo `cooldown_until` ultrapassa a janela de quota, quando a janela reinicia antes desse horário, então nenhum request começa até o vencimento. | `test_workday_cooldown_survives_budget_window_rollover` (proposto); estado após nova janela e zero request. |
| AC04 | Contadores persistem e distinguem tentativa, falha e skip. | Dada tentativa com timeout, tentativa 304 e item bloqueado por cooldown, quando o run é lido após reinício do worker, então totais e motivos permanecem associados ao mesmo source/run. | `test_detail_telemetry_round_trips_with_source_run` (proposto); fixture isolada/consulta de auditoria. |
| AC05a | Falha de detalhe não rebaixa inventário de listagem completo. | Dada paginação da listagem concluída normalmente e detalhe respondendo 429, quando o run é consolidado, então inventário fica completo, conteúdo de detalhe fica parcial e o fechamento de ausências segue exclusivamente o contrato de completude da listagem. | `test_detail_429_keeps_completed_listing_inventory` (proposto); estado separado de inventário/conteúdo e fechamento conforme contrato da listagem. |
| AC05b | Falta de orçamento que interrompe a paginação mantém inventário parcial. | Dada quota esgotada antes de concluir todas as páginas da listagem, quando o run é consolidado, então inventário fica parcial e nenhuma ausência é fechada. | `test_listing_budget_exhaustion_does_not_close_absences` (proposto); página/cursor interrompido, razão de parcialidade e vagas ausentes preservadas. |

## Rollout e reversão

Implementar com detalhe desativado por padrão. Se a inspeção confirmar necessidade de migração, torná-la aditiva, compatível com legado desconhecido (`NULL`) e testada em `_test`; zero é válido somente para métrica nova observada. Verificar upgrade e downgrade antes de piloto. Liberar primeiro em fake HTTP; ativação e piloto de fonte cabem ao F51-05 após aprovação humana. Rollback: desligar detalhe por fonte e reverter a versão do worker; manter registros de uso/cooldown para evitar tráfego prematuro. Entregáveis: contrato dos contadores, reserva atômica, cooldown persistente e testes concorrentes. Testes não foram executados nesta tarefa documental.
