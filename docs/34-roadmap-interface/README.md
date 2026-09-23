# Cards do roadmap de interface

Esta pasta transforma o [roadmap de interface](../34-roadmap-interface.md) em unidades
pequenas de execução. O roadmap continua sendo a fonte de escopo e decisões; os cards são a
fonte de ordem, dependências, aceite e verificação.

A convenção é a mesma do [roadmap pós-MVP](../33-roadmap-pos-mvp/README.md): identificador
`FNN-XX` estável, status explícito no card, e `Done` só depois de critério demonstrado e
verificação repetível no pipeline.

## Fases

| Fase | Objetivo | Cards | Entrada |
| --- | --- | ---: | --- |
| [Fase 14](fase-14/README.md) | Cadastrar e curar fonte, empresa e vaga pela interface | 5 | Fase 13 concluída |
| [Fase 15](fase-15/README.md) | Um sistema visual consistente, acessível e responsivo | 9 | Fase 13 concluída |

## Ordem macro

1. F15-01 e F15-02 primeiro: tokens e componentes evitam que a Fase 14 crie mais três
   variações de botão, campo e badge.
2. F14-01 a F14-03: fonte e vaga manual, que só dependem de contratos que já existem.
3. F14-04 e F14-05: empresa e vínculo, que exigem contrato novo de API.
4. F15-03 a F15-05: estados, acessibilidade e responsividade sobre o conjunto completo.

As duas fases podem avançar em paralelo desde que não disputem o mesmo arquivo. O ponto de
contato é `apps/web/src/components/`: um card da Fase 14 que precise de um componente ainda
não extraído deve criá-lo lá, no formato que a Fase 15 define, em vez de estilizar no lugar.

## Dependências

| Card | Depende de | Bloqueia |
| --- | --- | --- |
| F14-01 | Fase 13 | F14-02, F14-03 |
| F14-02 | F14-01 | Milestone M |
| F14-03 | F14-01 | Milestone M |
| F14-04 | Fase 13 | F14-05 |
| F14-05 | F14-04 | Milestone M |
| F15-01 | Nenhum | F15-02 |
| F15-02 | F15-01 | F15-03, F15-04, F15-05 |
| F15-03 | F15-02 | F15-09, Milestone N |
| F15-04 | F15-02 | Milestone N |
| F15-05 | F15-02 | Milestone N |
| F15-06 | F15-01 | F15-07, F15-08, F15-09 |
| F15-07 | F15-06 | Milestone N |
| F15-08 | F15-06 | Milestone N |
| F15-09 | F15-03, F15-06 | Milestone N |

## Regra de execução

Nenhum card desta pasta pode afrouxar um gate de domínio para simplificar uma tela. Se a
interface precisa de um caminho que o domínio não oferece, o card cria o contrato no
backend com as mesmas regras que o resto do sistema já cumpre — evidência antes de
inferência, procedência preservada, concorrência explícita.
