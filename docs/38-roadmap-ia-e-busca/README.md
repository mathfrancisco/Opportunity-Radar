# Cards do roadmap de IA local e busca

Esta pasta transforma o [roadmap de IA local e busca](../38-roadmap-ia-e-busca.md) em
unidades pequenas de execução, na convenção de [`docs/33`](../33-roadmap-pos-mvp/README.md)
e [`docs/34`](../34-roadmap-interface/README.md): identificador `FNN-XX` estável, status
explícito no card, e `Done` só com critério demonstrado e verificação repetível no CI.

## Fases

| Fase | Objetivo | Cards | SPEC |
| --- | --- | ---: | --- |
| [Fase 16](fase-16/README.md) | Camada local de IA na GPU, medida e avaliada | 13 | [36](../36-spec-ollama.md) |
| [Fase 17](fase-17/README.md) | Busca de vagas: cobertura e precisão | 13 | [37](../37-spec-busca.md) |

A continuidade é a [Fase 18](../40-roadmap-varredura-produtiva/README.md),
definida pela [SPEC de varredura produtiva](../39-spec-varredura-produtiva.md).

## Dependências entre fases

| Card | Depende de | Por quê |
| --- | --- | --- |
| F16-07 | F18-07 | preservar experiências/projetos antes de usar o perfil |
| F16-07 | F16-08 | payload novo usa identidade completa do cache |
| F16-09 | F16-01, F16-05 | infraestrutura e limpador compartilhado |
| F17-02, F17-11 | F18-07 | edição preserva o perfil completo |
| F17-03 | F17-02 | documento e filtro usam área |
| F17-05 | F17-07 | expansão só com presença/completude corretas |
| F17-10 | F17-06, F17-07 | collector novo mapeia campos e prova completude |
| F16-10 | F17-03 | o gate da busca por significado compara com o full-text |
| F16-11 | F17-01 (opcional) | experimento pós-Milestone P; usa decisões compatíveis |
| F17-08 | F16-09 (opcional) | o vetor é o segundo sinal de duplicata |
| F17-05, F17-10, F17-11 | F17-02 | volume só depois do filtro de área |
| F17-13 | F16-09, F17-01 | a relevância aprendida usa os vetores e as marcações |

## Regra de execução

Cada card declara o que o CI verifica e o que é medido na máquina de referência. O CI não
tem GPU e usa o Ollama falso; latência real, VRAM e relatórios de avaliação são anexados
ao PR do card. Nenhum card afrouxa gate de fonte, apaga evidência ou deixa o modelo
decidir score.
