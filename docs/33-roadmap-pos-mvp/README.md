# Cards do roadmap pós-MVP

Esta pasta transforma o
[roadmap pós-MVP](../33-roadmap-pos-mvp.md) em unidades pequenas de execução. O roadmap
continua sendo a fonte de escopo e decisões; os cards são a fonte de ordem, dependências,
aceite e verificação.

## Fases

| Fase | Objetivo | Cards | Entrada |
| --- | --- | ---: | --- |
| [Fase 10](fase-10/README.md) | Automatizar coleta, normalização, matching e análise | 6 | MVP concluído |
| [Fase 11](fase-11/README.md) | Reavaliar sem reescrever o histórico | 4 | Gate da Fase 10 |
| [Fase 12](fase-12/README.md) | Ampliar fontes com cobertura e qualidade mensuradas | 5 | Gate da Fase 10 |
| [Fase 13](fase-13/README.md) | Operar continuamente, observar e alertar | 6 | Gates das Fases 11 e 12 |
| [Documentação](documentacao/README.md) | Fechar rastreabilidade e operação | 1 | Cards que alteram operação |

## Ordem macro

1. Concluir a Fase 10.
2. Executar as Fases 11 e 12 em paralelo quando não disputarem o mesmo arquivo.
3. Concluir a Fase 13 depois que reavaliação e cobertura estiverem estáveis.
4. Atualizar a documentação ao longo das fases e fechar DOC-01 antes do aceite final.

## Continuação

Com a Fase 13 concluída, o ciclo opera sozinho. O que ainda exige terminal é o cadastro, e
a interface acumulou dívida visual enquanto crescia. Os dois pontos seguem em
[Cards do roadmap de interface](../34-roadmap-interface/README.md).

## Status dos cards

- `Backlog`: escopo registrado, mas dependências ainda não confirmadas.
- `Ready`: dependências concluídas e arquivos de trabalho identificados.
- `In progress`: existe implementação ativa.
- `Blocked`: há impedimento explícito registrado no card.
- `Done`: critérios de aceite e verificação foram satisfeitos.

## Regra de execução

Antes de iniciar um card:

1. Confirme todos os cards em **Depende de** como `Done`.
2. Releia **Fora de escopo** para não absorver o card seguinte.
3. Confirme os cenários de **Verificação** e onde eles entram no CI.
4. Mude somente o card ativo para `In progress`.

Um card só pode virar `Done` quando:

- o comportamento e o tratamento de erro estiverem implementados;
- migrations e backfills aplicáveis estiverem cobertos;
- logs e contratos públicos aplicáveis estiverem atualizados;
- os critérios de aceite estiverem demonstrados;
- a verificação repetível estiver no pipeline do repositório;
- a documentação afetada estiver atualizada;
- não houver regressão conhecida de idempotência ou procedência.

## Convenção

O identificador `FNN-XX` é estável. Renomear um título não altera o identificador nem as
dependências. Novos cards entram no final da fase, salvo quando forem pré-requisito de um
card ainda não iniciado.

