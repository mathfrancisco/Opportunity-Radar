# F51-08 — worker: concorrência limitada por host e orçamento

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** G
- **Risco:** alto — reserva não transacional entre processos pode exceder a quota e paralelismo por host pode multiplicar tráfego antes do cooldown.
- **Dependências:** F51-04, F51-07

## Problema e evidência

**Fato:** O worker é serial e Workday observado foi muito mais lento que Ashby/Greenhouse. scripts/collect.py já usa semáforo; orçamento de host deve ser verificado antes de nova arquitetura.
**Hipótese a validar:** permitir paralelismo limitado entre hosts independentes com sessões isoladas e quota atômica; não aumentar max_instances cegamente. Não houve teste de implementação nesta fase documental.

## Objetivo e não escopo

Objetivo: permitir paralelismo limitado entre hosts independentes com sessões isoladas e quota atômica; não aumentar max_instances cegamente.
Não escopo: provedores novos, embeddings, scrape indiscriminado ou mudança de decisão determinística.

## Arquivos e símbolos existentes

- [worker.py](../../../src/opportunity_radar/worker.py) (`collect_enabled_sources`).
- [scripts/collect.py](../../../scripts/collect.py).
- [acquisition/concurrency.py](../../../src/opportunity_radar/acquisition/concurrency.py).
- [acquisition/scheduling.py](../../../src/opportunity_radar/acquisition/scheduling.py).
- [test_concurrency.py](../../../tests/backend/acquisition/test_concurrency.py).
- [test_host_budget_scheduling.py](../../../tests/backend/acquisition/test_host_budget_scheduling.py).
- Arquivos/migrações novos são propostos somente após reutilização comprovadamente insuficiente.

## Tarefas detalhadas

1. Mapear o semáforo e a serialização já usados por `scripts/collect.py`; centralizar a decisão de limite em `acquisition/concurrency.py` sem alterar o limite efetivo até a coorte de rollout.
2. Antes de iniciar uma tarefa, exigir slot global, slot do host e claim de F51-07; antes de cada página ou detalhe, executar a reserva transacional de F51-04 e só chamar o transporte após o commit.
3. Fazer a reserva condicional com contador persistido e comparação do saldo (`remaining > 0`) na mesma transação, de modo que dois processos não possam observar o mesmo último request disponível.
4. Instanciar sessão HTTP e sessão/transação SQLAlchemy por tarefa, propagar cancelamento para o transporte e fechá-las em `finally`; cliente mutável, cookies, cabeçalhos e sessão do banco não atravessam fontes nem o loop do worker.
5. No deadline de F51-06, cancelar e aguardar a conclusão/cancelamento do transporte antes de liberar slots, reserva pendente ou claim; registrar o resultado como parcial quando não houver inventário completo.

## Contratos e invariantes

- A reserva persistida é confirmada antes do HTTP; dois processos com uma requisição restante produzem uma vencedora e no máximo um HTTP.
- Hosts distintos progridem até o limite global; mesmo host respeita seu limite.
- Sessões HTTP e SQLAlchemy não vazam entre tarefas; run parcial não fecha vaga.
- Cancelamento encerra transporte antes de liberar claim.

## Critérios de aceite

| ID | Arranjo e ação | Assert e evidência |
| --- | --- | --- |
| AC01 | Em tests/backend/acquisition/test_concurrency.py, duas fontes de hosts distintos bloqueiam em barreira, limite global 2. | Ambas entram no transporte antes da barreira liberar; relatório tem duas correlações. |
| AC02 | Duas fontes do mesmo host, limite host 1; primeira bloqueada no fake HTTP. | Segunda não inicia HTTP até a primeira encerrar; máximo simultâneo é 1. |
| AC03 | Em [test_host_budget_scheduling.py](../../../tests/backend/acquisition/test_host_budget_scheduling.py), duas sessões em barreira tentam reservar quando resta 1 request; o fake HTTP conta chamadas. | A transação vencedora confirma a reserva antes de liberar o fake HTTP; há exatamente uma chamada, uma linha de uso e saldo 0 mesmo em processos/sessões separados. |
| AC04 | Uma fonte retorna timeout após lista incompleta e outra, de host distinto, conclui inventário com item válido. | A primeira fica parcial e não fecha presença; a segunda persiste normalmente e só pode reconciliar presença se cumprir o contrato de inventário completo. |

## Falhas e casos negativos

- A falha de reserva, rede ou timeout não vira sucesso nem consome o slot de outra fonte.
- Run parcial não fecha vaga; lease vencido não pode gravar sob o claim novo.
- Teste de integração que altera dados usa banco isolado com sufixo `_test`.

## Rollout, rollback e entregáveis

Ativar em coorte não Workday, limite global 2 e orçamento observado; rollback reduz a um, cancela/aguarda tarefas e conserva métricas. Entregar scheduler bounded, testes de barreira e painel de uso.
