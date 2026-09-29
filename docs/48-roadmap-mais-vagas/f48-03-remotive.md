# CARD F48-03 — Remotive volta a produzir vagas (V02)

- **Status:** Implementado (2026-09-29); falta a verificação real (rodar o script na stack real
  e conferir oportunidades Remotive > 0), que este card não executa.
- **Spec:** [`../48-spec-mais-vagas.md`](../48-spec-mais-vagas.md) §4.2, §5, §9 decisão 9.

## Resultado

- `RemotiveCollector._published_at` grava `published_at = None` para `publication_date` sem
  fuso. Data com fuso explícito (`Z`, `+00:00`) continua como está.
- `_optional_datetime` (normalizador) devolve `None` com aviso (`logger.warning`) para data
  sem fuso em `published_at`, `updated_at` e `valid_through`, em vez de reprovar o item.
  Isso cobre os 35 `raw_item` já gravados com o snapshot ingênuo.
- Novo `scripts/backfill_failed_normalizations.py` com `--dry-run`.
- Coletor Hacker News: comentário cujo cabeçalho não nomeia um cargo (`title is None`) vira
  `skipped` (`telemetry.record_skipped_item()`), como o F20-75 fez no Workday.

## Contexto

A API da Remotive entrega `publication_date` sem fuso e o normalizador rejeitava datas sem
fuso ("collected_item_v1 published_at must include a timezone"). Resultado: 35 `raw_item`
Remotive com `normalization_result` `FAILED` e nenhuma oportunidade. Como
`pending_raw_item_ids` só devolve item sem resultado da versão atual, corrigir o código não
bastava. Decisão 9 (§9): não inventar fuso; a recência cai na data de coleta (F48-16).
Nenhuma documentação oficial da Remotive citando UTC foi consultada, então UTC não foi
assumido.

## Escopo

- `src/opportunity_radar/acquisition/remotive.py`
- `src/opportunity_radar/opportunities/service.py` (`_optional_datetime`, logger)
- `src/opportunity_radar/acquisition/hacker_news.py`
- `scripts/backfill_failed_normalizations.py`
- Testes: `tests/backend/acquisition/test_remotive_collector.py`,
  `tests/backend/acquisition/test_hacker_news_collector.py`,
  `tests/backend/test_backfill_failed_normalizations_integration.py`

Decisões e limites:

- O script considera afetado o `FAILED` com `reasons @> [{"code":"INVALID_COLLECTED_ITEM_V1"}]`
  **e** `error_summary LIKE '%must include a timezone%'`; outros `INVALID_COLLECTED_ITEM_V1`
  (causa não corrigida) ficam intactos. Apaga só linhas de `normalization_result` (um
  `FAILED` não tem oportunidade nem ocorrência) e nunca toca `raw_item`. É idempotente.
- HN: comentário sem cargo **mas com link de ATS suportado** continua persistido, porque
  alimenta a fila de propostas de fonte (F20-55, `_hn_proposal_item`). Só os sem cargo e
  sem ATS viram `skipped`. Os `FAILED` de HN já gravados não são alterados por este card.
- Não há status `SKIPPED` em `normalization_result` (CHECK só `SUCCEEDED`,
  `REVIEW_REQUIRED`, `FAILED`); por isso o "ignorado" acontece no coletor, sem criar
  `raw_item`.

## Critérios de aceite

- [x] `publication_date` sem fuso não reprova o item; o coletor grava `published_at = None`
  — `test_queries_maps_and_preserves_public_payload`,
  `test_publication_date_keeps_an_explicit_timezone_and_drops_a_naive_one`.
- [x] O normalizador aceita snapshot com `published_at = "2026-09-29T08:00:00"` e cria a
  oportunidade — `test_naive_published_at_no_longer_fails_the_item`.
- [x] `--dry-run` lista os itens afetados e não escreve; a execução real apaga só `FAILED`
  `INVALID_COLLECTED_ITEM_V1` por fuso e o `normalize_pending` cria a oportunidade —
  `test_backfill_dry_run_writes_nothing_and_real_run_reprocesses_only_affected`.
- [x] HN sem título vira `skipped` —
  `test_comment_without_a_role_is_skipped_not_emitted_or_invalid`.
- [ ] Verificação real: oportunidades Remotive > 0 na stack real (rodar
  `python scripts/backfill_failed_normalizations.py --dry-run`, depois sem a flag, depois
  `normalize_pending`; exige backup verificado antes, §6). Não executado neste card.

## Verificação

Ambiente isolado (`docker compose -p f48w2 ...`, sem tocar o projeto `opportunity-radar`):

```
pytest -q tests/backend/acquisition/test_remotive_collector.py tests/backend/acquisition/test_hacker_news_collector.py
42 passed, 1 skipped
RUN_DATABASE_INTEGRATION=1 pytest -q tests/backend/test_backfill_failed_normalizations_integration.py tests/backend/test_opportunities_integration.py
3 passed
RUN_DATABASE_INTEGRATION=1 pytest -q -x tests/backend
1181 passed, 11 skipped
ruff check src scripts tests/backend
All checks passed!
```
