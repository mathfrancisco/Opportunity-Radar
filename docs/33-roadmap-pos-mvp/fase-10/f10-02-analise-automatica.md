# CARD F10-02 — Análise automática, retry e claim

- **Status:** Backlog
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

- [ ] Analisa somente assessment atual com verdict configurado como elegível.
- [ ] Consulta o cache antes de chamar Ollama.
- [ ] Aplica limite de chamadas por passada.
- [ ] Falhas respeitam cooldown e teto de tentativas.
- [ ] Sucesso limpa estado de retry.
- [ ] `AI_COMPLETED` só é refeito com `refresh` explícito.
- [ ] Ação manual concorrente e job não gravam duas análises concluídas.
- [ ] Falha de Ollama não interrompe avaliação determinística.

## Verificação

Criar testes de seleção por verdict, cache, cooldown, limite de 24 horas,
claim concorrente, refresh e degradação quando Ollama falha.

## Arquivos prováveis

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/matching/analysis.py`
- `src/opportunity_radar/matching/ollama.py`
- `src/opportunity_radar/matching/repository.py`
- `src/opportunity_radar/matching/models.py`
- `tests/` de matching e worker
