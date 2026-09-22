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

## Conclusão operacional

Em 22 de setembro de 2026 os seis cards foram entregues e verificados:

- O estado de cada job do worker é persistido em `platform.worker_job_state` e lido pelo
  `doctor`, que classifica job ausente, atrasado, falho e saudável.
- Três falhas consecutivas de uma fonte abrem um incidente em
  `acquisition.source_alert_incident`, enviam um único webhook e encerram com recovery no
  primeiro sucesso. Sem webhook, o incidente continua registrado e aparece no `doctor`.
- O conteúdo bruto passou para `acquisition.raw_item_payload`; o envelope `RawItem`
  preserva ID, hash, fonte, `SourceRun` e `SourceOccurrence`.
- A retenção padrão de 12 meses expira apenas payload de item com normalização terminal e
  grava histórico append-only em `acquisition.payload_retention_event`. A API e a UI
  informam quando o reprocessamento deixou de estar disponível.
- `GET /source-metrics` entrega cobertura, volume, taxa de erro por código, dedupe, p95 e
  senioridade com `UNKNOWN` e procedência, nas janelas de 24 horas e sete dias; a Overview
  mostra as duas janelas.
- `python scripts/soak_gate.py` (alvo `make soak`) replica 72 horas de operação sem
  intervenção contra relógio controlado, com falha e recuperação de fonte roteirizadas, e
  falha o gate se qualquer job ficar silenciosamente falho.
