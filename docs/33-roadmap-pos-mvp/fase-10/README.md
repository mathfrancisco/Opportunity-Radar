# Fase 10 — Ciclo autônomo

Estes cards decompõem a Fase 10 do roadmap pós-MVP. O objetivo é operar o
ciclo `coletar → normalizar → avaliar → analisar` sem terminal, depois do
bootstrap explícito do ambiente.

## Ordem de execução

1. [F10-01 — Avaliação automática e identidade atual](f10-01-avaliacao-automatica.md)
   não tem dependência e bloqueia F10-02 e F10-06.
2. [F10-02 — Análise automática, retry e claim](f10-02-analise-automatica.md)
   depende de F10-01 e bloqueia F10-06.
3. [F10-04 — Origem da execução em SourceRun](f10-04-origem-source-run.md)
   não tem dependência e bloqueia F10-03 e F10-06.
4. [F10-03 — Coleta agendada e request por capability](f10-03-coleta-agendada.md)
   depende de F10-04 e bloqueia F10-06.
5. [F10-05 — Kill switches](f10-05-kill-switches.md) não tem dependência e
   bloqueia F10-06.
6. [F10-06 — Ação manual e gate E2E](f10-06-acao-manual-e-gate.md) depende de
   todos os cards anteriores.

## Limites da fase

Não criar uma fila distribuída, Redis, Celery ou efeitos colaterais de
bootstrap no Compose. `heartbeat` continua obrigatório e não recebe kill
switch.
