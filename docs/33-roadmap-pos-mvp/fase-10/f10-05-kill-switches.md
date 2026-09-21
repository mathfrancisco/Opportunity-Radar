# CARD F10-05 — Kill switches

- **Status:** Done
- **Fase:** 10 — Ciclo autônomo
- **Depende de:** Nenhum
- **Bloqueia:** F10-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§10 e 12; ordem prática 48

## Resultado

Operadores podem desabilitar qualquer job funcional no startup do worker sem
editar código, preservando o heartbeat.

## Contexto

Um job desabilitado não pode ser registrado para retornar cedo depois. Essa
diferença evita aparentar que uma automação está ativa quando ela foi desligada.

## Escopo

- Adicionar `WORKER_COLLECT_ENABLED`, `WORKER_NORMALIZE_ENABLED`,
  `WORKER_MATCH_ENABLED` e `WORKER_ANALYZE_ENABLED`.
- Condicionar o registro dos jobs `collect_enabled_sources`,
  `normalize_opportunities`, `evaluate_pending` e `analyze_pending`.
- Registrar em log estruturado, no startup, quais jobs foram agendados e quais
  foram desabilitados.
- Manter `heartbeat` sempre registrado enquanto o worker estiver ativo.

## Fora de escopo

- Kill switch por fonte.
- Pausar job em memória depois do startup.
- Desabilitar `heartbeat`.

## Notas de implementação

Usar uma configuração única e valores explícitos. A semântica é de startup:
alterar uma variável exige reiniciar o worker para reconstruir o scheduler.

## Critérios de aceite

- [x] Cada variável controla somente seu job funcional correspondente.
- [x] Job desligado não aparece no scheduler.
- [x] Log de inicialização lista estado de todos os jobs funcionais.
- [x] `heartbeat` continua ativo com todas as variáveis desligadas.
- [x] Configuração padrão mantém os jobs previstos para a fase habilitados.

## Verificação

Criar testes de configuração e de scheduler que cubram cada flag isoladamente,
todas desligadas e preservação do heartbeat.

Entregue em `tests/backend/test_worker.py`. O gate E2E do F10-06 recria o worker
com as quatro variáveis desligadas e confere o log de inicialização.

## Correção durante a fase

O log de inicialização era montado a partir das settings, e por isso anunciava
`analyze_pending` ativo enquanto esse job sequer existia. Agora é derivado do
scheduler construído: um job não registrado não pode ser reportado como ativo.

O `compose.yaml` não repassava nenhuma `WORKER_*_ENABLED` ao container. O worker
herda apenas aquele bloco de environment, então o kill switch existia no código
mas não era operável — que é exatamente o que este card prometia.

## Arquivos prováveis

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/config.py`
- `.env.example`
- `tests/` de worker e configuração
