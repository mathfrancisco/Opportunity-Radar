# Fase 12 — Escala e qualidade de fontes

Cards atômicos para transformar o catálogo pesquisado em aquisição mensurável, sem
confundir empresa catalogada com uma fonte executável.

## Ordem recomendada

1. [F12-01 — Baseline e relatório de cobertura](f12-01-cobertura-de-fontes.md)
2. [F12-02 — Senioridade com procedência](f12-02-senioridade-com-procedencia.md)
3. [F12-03 — Descoberta de fontes](f12-03-descoberta-de-fontes.md)
4. [F12-04 — Detecção de fonte pela UI](f12-04-deteccao-na-ui.md)
5. [F12-05 — Homologação e expansão](f12-05-homologacao-e-expansao.md)

## Dependências

| Card | Depende de | Bloqueia |
| --- | --- | --- |
| F12-01 | Fase 10 | F12-05, métricas da Fase 13 |
| F12-02 | Fase 10 | F12-05, métricas da Fase 13 |
| F12-03 | Fase 10 | F12-04, F12-05 |
| F12-04 | F12-03 | descoberta por operadores na UI |
| F12-05 | F12-01, F12-02, F12-03 | Milestone K e Fase 13 |

Nenhum card autoriza habilitar uma fonte só porque um ATS foi identificado. Cada fonte
segue o gate de termos, teste local e homologação explícita antes de poder executar.

## Conclusão operacional

Em 22 de setembro de 2026, o ambiente Docker local concluiu a homologação de 22 fontes.
Todas ficaram habilitadas com termos aprovados pelo operador e teste do collector
registrados; uma rodada correlacionada executou 22 `SourceRun` com sucesso, limitada a um
item por fonte.
