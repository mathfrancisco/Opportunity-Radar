# Cards do roadmap de IA local e busca

Esta pasta transforma o [roadmap de IA local e busca](../38-roadmap-ia-e-busca.md) em
unidades pequenas de execução, na convenção de [`docs/33`](../33-roadmap-pos-mvp/README.md)
e [`docs/34`](../34-roadmap-interface/README.md): identificador `FNN-XX` estável, status
explícito no card, e `Done` só com critério demonstrado e verificação repetível no CI.

## Fases

| Fase | Objetivo | Cards | SPEC |
| --- | --- | ---: | --- |
| [Fase 16](fase-16/README.md) | Camada local de IA na GPU, medida e avaliada | 13 | [36](../36-spec-ollama.md) |
| [Fase 17](fase-17/README.md) | Busca de vagas: cobertura e precisão | 12 | [37](../37-spec-busca.md) |

## Dependências entre fases

| Card | Depende de | Por quê |
| --- | --- | --- |
| F16-10 | F17-03 | o gate da busca por significado compara com o full-text |
| F16-11 | F17-01 (opcional) | a marcação de relevância é uma das decisões recuperadas |
| F17-08 | F16-09 (opcional) | o vetor é o segundo sinal de duplicata |
| F17-05, F17-10, F17-11 | F17-02 | volume só depois do filtro de área |

## Regra de execução

Cada card declara o que o CI verifica e o que é medido na máquina de referência. O CI não
tem GPU e usa o Ollama falso; latência real, VRAM e relatórios de avaliação são anexados
ao PR do card. Nenhum card afrouxa gate de fonte, apaga evidência ou deixa o modelo
decidir score.
