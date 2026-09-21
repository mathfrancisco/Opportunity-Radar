# CARD F13-06 — Doctor e soak gate de 72 horas

- **Status:** Backlog
- **Fase:** 13 — Operação contínua
- **Depende de:** F13-01, F13-02, F13-04, F13-05
- **Bloqueia:** Encerramento da Fase 13 e milestone L
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§25–26, 31 e 33

## Resultado

O `doctor` avalia o estado persistido dos jobs e um gate prova que o sistema opera por
72 horas sem intervenção, com alerta e recovery cobertos.

## Contexto

O scheduler pode parecer saudável sem executar. O gate final precisa confirmar tanto
o caminho contínuo normal quanto o comportamento observável diante de falha de fonte.

## Escopo

- Reportar job ausente, atrasado, falho ou saudável a partir do estado persistido.
- Incluir fontes degradadas, incidentes abertos e ausência de webhook no diagnóstico.
- Criar soak test de 72 horas, ou simulação acelerada com relógio controlado.
- Cobrir coleta, normalização, matching, análise, alerta, recovery, métricas e
  retenção durante o gate.

## Fora de escopo

- Monitoramento externo 24/7, SLA formal, implantação distribuída ou substituição do
  `doctor` por serviço de observabilidade.

## Notas de implementação

O `doctor` deve retornar diagnóstico acionável e código de saída apropriado para o
gate. A simulação acelerada deve preservar a semântica do tempo, especialmente limiar
de atraso, 12 meses de retenção e sequência de três falhas.

## Critérios de aceite

- [ ] `doctor` identifica job ausente, atrasado, falho e saudável.
- [ ] Diagnóstico inclui incidentes de fonte e configuração de webhook.
- [ ] Gate de 72 horas não exige terminal ou intervenção manual após bootstrap.
- [ ] Gate cobre alerta único após três falhas e recovery no primeiro sucesso.
- [ ] Gate confirma métricas e retenção sem perda de envelope ou procedência.
- [ ] Simulação acelerada usa relógio controlado e preserva os limites temporais.

## Verificação

Execute o soak real por 72 horas ou a simulação equivalente; arquive resultados do
`doctor`, métricas, incidentes e recovery. Falhe o gate se qualquer job ficar atrasado,
silenciosamente falho ou exigir ação manual.

## Arquivos prováveis

- `src/opportunity_radar/doctor.py`
- `src/opportunity_radar/worker.py`
- `tests/`
- `.github/workflows/pipeline.yml`
- `docs/30-runbook.md`
