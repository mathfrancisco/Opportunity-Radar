# F51-07 — worker: claim, lease, recuperação e fencing

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** M
- **Risco:** alto — worker e CLI/manual podem coletar a mesma fonte; fencing só ao fim não protege gravações durante a execução.
- **Dependências:** F51-06

## Problema e evidência

**Fato:** Passes históricos apareceram abertos, mas a causa não foi demonstrada. `WorkerPassHistoryModel` registra o passe e `AcquisitionService.execute` persiste efeitos durante a execução; os leases de análise existentes não provam ownership por `source_id` para a coleta. Portanto, um claim somente no fim não protege uma entrada CLI/manual concorrente.
**Hipótese a validar:** recuperar execução interrompida sem fila nova, duplicidade ou escrita tardia; não introduzir infraestrutura de mensageria. Não houve teste de implementação nesta fase documental.

## Objetivo e não escopo

Objetivo: recuperar execução interrompida sem fila nova, duplicidade ou escrita tardia; não introduzir infraestrutura de mensageria.
Não escopo: provedores novos, embeddings, scrape indiscriminado ou mudança de decisão determinística.

## Arquivos e símbolos existentes

- [operations/service.py](../../../src/opportunity_radar/operations/service.py) (`observe_job`).
- [operations/models.py](../../../src/opportunity_radar/operations/models.py) (`WorkerPassHistoryModel`).
- [acquisition/service.py](../../../src/opportunity_radar/acquisition/service.py) (`AcquisitionService.execute`).
- [worker.py](../../../src/opportunity_radar/worker.py) (`collect_enabled_sources`) e [scripts/collect.py](../../../scripts/collect.py).
- [test_collection_job.py](../../../tests/backend/acquisition/test_collection_job.py).
- Arquivos/migrações novos são propostos somente após reutilização comprovadamente insuficiente.

## Tarefas detalhadas

1. Criar ou reutilizar uma linha durável de claim identificada por `source_id` e tipo de tarefa; `collect_enabled_sources` e `scripts/collect.py` devem chamar a mesma aquisição antes de criar `AcquisitionService.execute`.
2. Passar `claim_id` e fencing token ao contexto de `AcquisitionService.execute`; renovar o lease por `UPDATE ... WHERE token_atual = :token AND expires_at > agora`, para que um dono atrasado não renove o claim de B.
3. Colocar a verificação do token atual nas gravações duráveis feitas durante `execute`: raw item, ocorrência, checkpoint, presença, fechamento, `SourceRun` e métricas. Cada repositório deve rejeitar escrita sem o token corrente, não apenas a conclusão da tarefa.
4. Recuperar apenas linha expirada por compare-and-swap; o recuperador grava um token maior, marca a correlação anterior como recuperada e recomeça no checkpoint idempotente sem infraestrutura de fila nova.
5. Publicar em `observe_job` os eventos `claim_acquired`, `claim_contended`, `lease_renewed`, `fence_rejected` e `claim_recovered`, com `source_id`, correlação e token mascarado/ordinal para auditoria.

## Contratos e invariantes

- Uma lease vencida pode ser adquirida por exatamente um executor.
- Resultado de fence menor não atualiza raw item, ocorrência, checkpoint, presença, fechamento, run ou métricas.
- Worker e CLI/manual disputam a mesma chave source_id/tarefa.
- Recuperação não reexecuta fechamento de presença de run parcial.
- Expiração não substitui cancelamento: F51-06 encerra trabalho vivo antes do release normal.

## Critérios de aceite

| ID | Arranjo e ação | Assert e evidência |
| --- | --- | --- |
| AC01 | Barreira inicia worker e CLI para mesma fonte/tarefa. | Uma entrada adquire claim e faz HTTP; outra recebe claimed_elsewhere e faz zero HTTP. |
| AC02 | A com token 7 inicia `execute` e fica bloqueado antes de cada repositório; o relógio expira, B recebe token 8, grava e A é liberado. | As tentativas de A para raw, ocorrência, checkpoint, presença, fechamento, `SourceRun` e métricas retornam `fence_rejected`; somente B deixa linhas persistidas. |
| AC03 | Duas recuperações disputam a mesma lease vencida. | Um UPDATE condicional vence; existe uma correlação recuperada e uma execução. |
| AC04 | Worker e CLI coletam duas fontes distintas. | Claims independentes permitem ambas sem bloqueio cruzado. |

## Falhas e casos negativos

- Falha de rede ou crash deixa lease observável; não vira sucesso.
- Teste de integração que escreve usa banco isolado com sufixo _test.

## Rollout, rollback e entregáveis

Rollout inicia em uma fonte de baixa prioridade, com aquisição compartilhada pelo worker e CLI/manual e consulta de claims por correlação. Se houver rejeição inesperada, o rollback desliga recuperação automática, impede novos claims dessa coorte, aguarda execuções vivas e preserva fences/histórico para diagnóstico. Entregar migração justificada, consulta operacional de leases e os quatro testes acima.
