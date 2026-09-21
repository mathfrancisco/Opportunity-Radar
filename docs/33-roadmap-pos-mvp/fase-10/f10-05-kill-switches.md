# CARD F10-05 — Kill switches

- **Status:** In progress
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

- [ ] Cada variável controla somente seu job funcional correspondente.
- [ ] Job desligado não aparece no scheduler.
- [ ] Log de inicialização lista estado de todos os jobs funcionais.
- [ ] `heartbeat` continua ativo com todas as variáveis desligadas.
- [ ] Configuração padrão mantém os jobs previstos para a fase habilitados.

## Verificação

Criar testes de configuração e de scheduler que cubram cada flag isoladamente,
todas desligadas e preservação do heartbeat.

## Arquivos prováveis

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/config.py`
- `.env.example`
- `tests/` de worker e configuração
