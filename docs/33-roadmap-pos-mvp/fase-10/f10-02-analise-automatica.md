# CARD F10-02 — Análise automática, retry e claim

- **Status:** Done
- **Fase:** 10 — Ciclo autônomo
- **Depende de:** F10-01
- **Bloqueia:** F10-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§8 e 12–13; ordem prática 43–44

## Resultado

O worker analisa assessments atuais elegíveis sem duplicar chamadas concorrentes
nem repetir falhas de IA sem controle.

## Contexto

O modelo local disputa CPU com o sistema. O histórico de `AI_FAILED` e
`AI_SKIPPED` deve permanecer, mas só retorna à fila após cooldown. A ação
manual e o job precisam disputar a mesma unidade de trabalho.

## Escopo

- Criar `analyze_pending` para assessments atuais sem análise concluída.
- Configurar verdicts elegíveis: `HIGH_PRIORITY`, `RECOMMENDED`, `WATCHLIST` e
  `REVIEW_REQUIRED`; excluir `LOW_MATCH` e `INELIGIBLE`.
- Reusar cache antes de chamar Ollama e limitar chamadas por passada.
- Implementar cooldown padrão de uma hora e máximo padrão de três tentativas em
  24 horas por assessment.
- Usar claim persistente e exclusão mútua entre job e ação manual.
- Limpar estado de retry no sucesso; repetir `AI_COMPLETED` apenas com `refresh`.

## Fora de escopo

- Alterar verdicts do matching determinístico.
- Disponibilizar novo modelo ou infraestrutura de filas.
- Implementar o botão manual, que pertence ao F10-06.

## Notas de implementação

Manter `AI_FAILED` e `AI_SKIPPED` como eventos históricos. Se Ollama estiver
indisponível, degradar este job sem bloquear F10-01. A claim deve sobreviver a
concorrência e reinício, e proteger a cache key da análise.

## Critérios de aceite

- [x] Analisa somente assessment atual com verdict configurado como elegível.
- [x] Consulta o cache antes de chamar Ollama.
- [x] Aplica limite de chamadas por passada.
- [x] Falhas respeitam cooldown e teto de tentativas.
- [x] Sucesso limpa estado de retry.
- [x] `AI_COMPLETED` só é refeito com `refresh` explícito.
- [x] Ação manual concorrente e job não gravam duas análises concluídas.
- [x] Falha de Ollama não interrompe avaliação determinística.

## Verificação

Criar testes de seleção por verdict, cache, cooldown, limite de 24 horas,
claim concorrente, refresh e degradação quando Ollama falha.

Entregue em `tests/backend/matching/test_analysis_queue.py`, que roda no job
`backend-tests` do pipeline com `RUN_DATABASE_INTEGRATION=1`.

## Decisões de implementação

O estado de retry é derivado do histórico de `match_analysis`, não persistido à
parte: as linhas `AI_FAILED` e `AI_SKIPPED` dentro da janela são as tentativas, e
uma `AI_COMPLETED` tira o assessment da fila. Por isso o sucesso limpa o retry
sem apagar evidência.

A claim é a tabela `matching.match_analysis_claim`, uma linha por assessment, com
lease que expira. A exclusão mútua precisa atravessar processos — job e API são
processos distintos — e o vencimento impede que um holder morto aposente o
assessment para sempre.

"Assessment atual" aqui é o mais recente por oportunidade. A identidade formal de
atualidade é escopo do F11-01 e não foi antecipada.

## Arquivos alterados

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/matching/adapters.py`
- `src/opportunity_radar/matching/service.py`
- `src/opportunity_radar/matching/repository.py`
- `src/opportunity_radar/matching/models.py`
- `migrations/versions/20260921_0011_match_analysis_claim.py`
- `src/opportunity_radar/platform/config.py`
- `src/opportunity_radar/presentation/http/matching.py`
- `src/opportunity_radar/presentation/http/dependencies.py`
- `apps/web/src/features/matching/api.ts`
- `.env.example`
- `tests/backend/matching/test_analysis_queue.py`
- `tests/backend/test_worker.py`
