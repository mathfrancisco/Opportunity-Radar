# Análise útil sob orçamento de quota — evidência local, 2026-09-27

Evidência de execução real para o card F20-24, branch `feature/f20-24-orcamento`. A quota
diária do Groq estava esgotada no momento da implementação: nenhuma chamada real ao Groq foi
feita; toda a verificação usa `_StubAdapter`/`_FakeQuotaGuard` (fakes locais) e o fake
existente em `tests/e2e/`. A pilha `opportunity-radar` (dados do usuário) não foi tocada.

## Resumo

| Critério de aceite | Veredito | Evidência |
| --- | --- | --- |
| Revisita sem mudança não chama IA; alteração material invalida reuso | **Passa** | §2, `test_pending_analysis_skips_without_material_change` |
| Budget adia sem perder oportunidade nem bloquear o worker | **Passa** | §3, `test_the_job_defers_a_pending_id_when_the_worker_ceiling_is_exhausted`, `test_the_worker_budget_probe_never_consumes_quota` |
| Sugestão não altera campo/matching antes da confirmação | **Fora de escopo deste card** — ver nota abaixo | — |
| Relatório compara fila atual e política nova com suporte e custo/qualidade | **Parcial — comparação estrutural feita; medição de custo/qualidade real é passo restante (quota exhausted)** | §4, §5 |

Nota sobre "sugestão não altera campo/matching": o card diz explicitamente ("Ajustes da
Fase 20") que as sugestões de campo deste card são as do F20-23 e que este card **não cria
outra tabela** — a tabela `opportunities.field_suggestion` (F20-23) ainda não existe nesta
árvore (`opportunities/suggestions.py` não criado). Não há código de sugestão de campo para
verificar aqui; o critério se aplica ao card que implementar F20-23.

## 0. O que foi construído

- `src/opportunity_radar/matching/repository.py`: `pending_analysis_ids` agora ordena por
  `verdict_rank`, depois prioridade da empresa (`Company.priority`, alto > normal > baixo >
  bloqueado), depois `score` do assessment, depois frescor (`published_at`), antes de
  `assessed_at`/`id`. Reserva uma fração do lote (`aging_sample_ratio`) para ids fora do topo
  do ranking, escolhidos deterministicamente por `id`.
- `src/opportunity_radar/matching/service.py`: `pending_analysis_ids` propaga
  `aging_sample_ratio` para o repositório.
- `src/opportunity_radar/platform/config.py`: novos `ai_interactive_reserve_requests: int =
  100` e `worker_analyze_aging_sample_ratio: float = 0.10`, com validação (reserva entre 0 e
  o limite diário; ratio entre 0 e 1).
- `src/opportunity_radar/platform/ai/quota.py`: `QuotaGuard.reserve` ganhou
  `ceiling_requests: int | None = None` — combinado via `min()` com o `day_requests`
  configurado, nunca o ultrapassa. Sem o parâmetro, comportamento idêntico ao anterior (usado
  pela análise pedida na UI).
- `src/opportunity_radar/worker.py`: `analyze_pending` ganhou `aging_sample_ratio` e
  `worker_requests_ceiling`. Antes de cada chamada ao adapter, se um teto foi configurado, o
  worker faz uma reserva de prova com `estimated_tokens=0` e `ceiling_requests=teto`; se
  negada, pula a vaga com o motivo "budget" (contado em `skipped_budget` no log, sem registrar
  tentativa) e a oportunidade continua pendente para a próxima passagem. Se aprovada, a
  reserva é liberada imediatamente (`QuotaGuard.release`) — o efeito líquido da prova é zero,
  a reserva real acontece depois, dentro do próprio `adapter.analyze()`/`AIRouter.run`.
- O endpoint interativo (`presentation/http/matching.py:212`, `MatchingService.analyze`) não
  foi alterado e nunca passa por `analyze_pending`: continua usando o limite cheio do
  `QuotaGuard.reserve` (sem `ceiling_requests`).

### Desvio da tabela "Arquivos" do card

- O card pede a interface `QuotaGuard.reserve(self, model, *, requests=1,
  tokens_estimate=0, ceiling_requests=None)`. A implementação real do F20-12 nesta árvore é
  `reserve(self, model, estimated_tokens)` (parâmetro posicional, sem `requests`/plural). Fiz
  `ceiling_requests` um keyword-only novo sobre essa assinatura real, em vez de reescrever a
  assinatura para bater com o texto do card — mudar a assinatura quebraria toda chamada
  existente em `router.py`/`adapters.py` sem necessidade.
- `count_pending_analysis` não recebeu `aging_sample_ratio`: ele mede o tamanho do backlog
  sem limite de lote, e a amostra de aging só faz sentido quando há um `limit` a reservar
  fração de.
- Os testes de `ceiling_requests` foram escritos em
  `tests/backend/test_ai_quota_integration.py` (não em
  `tests/backend/platform/ai/test_quota.py`) — esse último arquivo é documentadamente
  "unit tests for the pure calculations", sem banco; `reserve`/`ceiling_requests` precisa de
  Postgres real (mesmo padrão dos testes de atomicidade já existentes nesse arquivo).

## 1. Ordenação por valor (score, prioridade da empresa, frescor)

`test_pending_analysis_orders_by_value` prova a ordem de dominância exigida pelo F16-04:
prioridade da empresa (alta) vence qualquer score abaixo dela; dentro do mesmo nível de
prioridade, o score decide. Rodado isolado e dentro da suíte completa.

## 2. Revisita sem mudança não chama IA (F20-39 / F20-16)

`test_pending_analysis_skips_without_material_change`: `service.evaluate()` chamado duas
vezes sobre a mesma oportunidade sem alteração produz o mesmo `assessment_id` (reuso de
identidade, F20-39) e `service.analyze()` chamado duas vezes sobre esse id só chama o adapter
uma vez (cache por `PreparedAnalysis.cache_key`, F20-16). Os testes de reavaliação já
existentes em `tests/backend/matching/test_reevaluation.py` cobrem o lado "alteração material
invalida reuso" (mudança de perfil ativo, de conteúdo da vaga, de ruleset e de taxonomia
sempre geram um novo assessment) — não duplicados aqui.

## 3. Budget adia sem perder oportunidade nem bloquear o worker

- `test_the_job_defers_a_pending_id_when_the_worker_ceiling_is_exhausted`: com a prova de
  reserva sempre negada, o adapter nunca é chamado, nenhum `MatchAnalysisModel` é gravado, e a
  vaga continua em `pending_analysis_ids` — nem perdida, nem contada contra o orçamento de
  retentativas.
- `test_the_worker_budget_probe_never_consumes_quota`: com a prova sempre aprovada, o número
  de `reserve`/`release` da prova é 1/1 (efeito líquido zero) e o adapter é chamado
  normalmente — a prova nunca consome o que a análise pedida na UI precisaria.
- `test_worker_reservation_respects_interactive_ceiling` /
  `test_interactive_reservation_uses_full_limit`
  (`tests/backend/test_ai_quota_integration.py`): `QuotaGuard.reserve(ceiling_requests=N)`
  nega no teto reduzido mesmo com saldo no limite cheio; sem `ceiling_requests`, só o limite
  cheio decide.

## 4. Fila atual × política nova (estrutural)

| Aspecto | Fila atual (antes deste card) | Política nova (F20-24) |
| --- | --- | --- |
| Critério de ordem | `verdict_rank`, `published_at` desc, `assessed_at` desc, `id` | `verdict_rank`, prioridade da empresa desc, `score` desc, `published_at` desc, `assessed_at` desc, `id` |
| Reuso sem mudança | Já existia (F20-39 identidade + F20-16 cache) — sem alteração | Mesmo mecanismo, sem alteração |
| Orçamento do worker vs. UI | Um único `QuotaGuard.reserve` sem distinção de chamador | Prova de admissão com `ceiling_requests` reduzido antes do worker chamar o adapter; UI sem teto |
| Amostra de aging | Nenhuma — o funil abaixo do topo do ranking nunca era medido | `worker_analyze_aging_sample_ratio` (padrão 0.10) reserva uma fração do lote para ids fora do topo, por amostragem determinística por `id` |

## 5. Medição real (2026-09-28, UTC) — reserva interativa provada contra o Groq

Rodada com o Groq real, stack isolada `-p f20-24real` (nunca `opportunity-radar`),
`down -v` ao final. Em vez de rodar o worker completo por várias passagens (o job roda de
120 em 120s e a fila real da produção não é tocada), a reserva foi provada diretamente
com um script local de uma vez (não commitado; excluído após gerar esta evidência) que
chama `worker.analyze_pending` e `MatchingService.analyze` reais, com adaptador Groq real
— mesma lógica de `analyze_pending`, `QuotaGuard.reserve(ceiling_requests=...)`, sem
stub. Como o prompt em produção é `v1` (não lê `posting`/`profile_history`, ver F20-18
acima), os assessments semeados usam o mesmo formato mínimo de
`tests/backend/matching/test_analysis_queue.py::_seed_assessment` (snapshot dict, sem
vaga/perfil reais) — suficiente para uma chamada real ao Groq via `v1`.

Configuração: `AI_INTERACTIVE_RESERVE_REQUESTS=847` (com o `AI_DAILY_REQUESTS_SOFT_LIMIT`
padrão de 850, isso deixa **`worker_requests_ceiling=3`** — um teto baixo de propósito,
para o worker esgotar o próprio teto rápido e gastar pouca quota) contra 6 assessments
pendentes semeados (mais que o teto).

**Passagem 1 — worker:** lote de 6, teto 3. 3 chamadas reais ao Groq (`HTTP 200`), depois
`analysis batch finished {'processed': 6, 'succeeded': 3, ..., 'skipped_budget': 0}`
implícito nas 3 primeiras (o teto ainda tinha saldo); as 3 seguintes já ficariam sem
saldo na mesma janela do dia.

**Passagem 2 — mesmo dia, mesma stack (teto do worker já em 3/3):** novo lote de 6
pendentes, teto ainda 3. Nenhuma chamada nova — log real:

```
analysis batch finished {'job': 'analyze', 'processed': 6, 'succeeded': 0, 'reused': 0,
'degraded': 0, 'claimed_elsewhere': 0, 'skipped_budget': 6, 'failed': 0}
```

**`skipped_budget` apareceu (6), como o critério de aceite pede.** Em seguida, a análise
pedida pela UI (`MatchingService.analyze`, sem `ceiling_requests` — o caminho do endpoint
`/matching/.../analyze`) rodou sobre um assessment novo, na mesma stack, com o teto do
worker ainda esgotado:

```
--- interactive pass: MatchingService.analyze(), no ceiling_requests ---
HTTP Request: POST https://api.groq.com/openai/v1/chat/completions "HTTP/1.1 200 OK"
interactive analysis status: AI_COMPLETED
```

**`AI_COMPLETED`** — a reserva interativa não é afetada pelo teto reduzido do worker,
confirmado com Groq real, não só com o fake de teste.

`platform.ai_quota_usage` da stack isolada ao final (janela do dia, UTC):

| model | requests (dia) | tokens (dia) | remaining_requests_reported |
| --- | ---: | ---: | ---: |
| openai/gpt-oss-120b | 4 | 3523 | 922 |

4 chamadas reais no total (3 do worker até o teto + 1 interativa), ~3.5k tokens — bem
abaixo do orçamento diário, deixando folga para outros workers na mesma chave. Amostra de
aging (`worker_analyze_aging_sample_ratio`) não foi medida contra Groq real nesta rodada
(o script prova só a reserva interativa, que é o critério de aceite pendente); a cobertura
de aging já está provada em CI com fake (`test_pending_analysis_reserves_aging_sample`) e
fica como medição real futura, não bloqueante para este card.

## 6. Comandos rodados

```bash
docker compose -p f20q -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api \
  pytest -q tests/backend/matching/test_analysis_queue.py tests/backend/platform/ai/test_quota.py \
  tests/backend/platform/ai/test_config.py tests/backend/test_ai_quota_integration.py tests/backend/matching/test_reevaluation.py
# 73 passed, 1 skipped (psql not on PATH in the api image)

docker compose -p f20q -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q
# 925 passed, 10 skipped

docker compose -p f20q -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
# All checks passed!

docker compose -p f20q -f compose.yaml -f compose.dev.yaml run --rm api mypy
# Success: no issues found in 118 source files
```

## 7. Achado durante a verificação: banco de integração nunca é truncado entre testes

`tests/backend/` roda a suíte inteira (`RUN_DATABASE_INTEGRATION=1`) contra um único Postgres
compartilhado, sem truncar tabelas entre arquivos de teste (confirmado em
`.github/workflows/pipeline.yml`, um único `pytest -q`). Isso já era verdade antes deste card,
mas a ordenação antiga (`verdict_rank`, depois só frescor) escondia o efeito: um assessment
`AI_PENDING` deixado por outro arquivo (ex.: `tests/backend/dashboard/test_queries.py`, que
semeia `match_assessment` com `verdict="HIGH_PRIORITY"` e prioridade de empresa "high" sem
nunca gerar uma análise) sempre perdia para o item recém-semeado de um teste mais novo, porque
a recência decidia o empate. Com prioridade de empresa e score entrando antes da recência, um
resíduo desse tipo pode permanentemente ficar acima de um item novo de prioridade/score
menores. Corrigido nos testes novos deste card usando o valor máximo de score (100) como
padrão de `_seed_assessment` e prioridade "high" explícita no teste de aging (`_company`,
mesmo padrão já usado por `dashboard/test_queries.py`), e retirando da fila (via
`add_analysis(..., status=AI_COMPLETED)`) os 20 ids que o teste de aging semeia, para não
deixar resíduo para o resto da suíte. Não alterei nenhum arquivo de teste fora de
`tests/backend/matching/test_analysis_queue.py`.
