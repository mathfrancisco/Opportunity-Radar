# Cards da Fase 13 — operação contínua

Estes cards decompõem a Fase 13 do roadmap pós-MVP em entregas atômicas. A
ordem preserva o estado operacional e a procedência antes de ativar limpeza,
alertas e gates de operação.

| Ordem | Card | Depende de |
| --- | --- | --- |
| 1 | [F13-01 — estado dos jobs](f13-01-estado-dos-jobs.md) | Fases 10 e 11 |
| 2 | [F13-02 — alertas de fontes](f13-02-alertas-de-fontes.md) | F13-01 |
| 3 | [F13-03 — separação do payload](f13-03-separacao-do-payload.md) | Nenhum |
| 4 | [F13-04 — retenção auditável](f13-04-retencao-auditavel.md) | F13-03 |
| 5 | [F13-05 — métricas operacionais](f13-05-metricas-operacionais.md) | F13-01, Fase 12 |
| 6 | [F13-06 — doctor e soak gate](f13-06-doctor-e-soak-gate.md) | F13-01, F13-02, F13-04, F13-05 |

F13-03 pode seguir em paralelo com F13-01 e F13-02. F13-06 encerra a fase.
