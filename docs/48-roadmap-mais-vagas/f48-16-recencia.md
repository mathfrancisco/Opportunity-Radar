# F48-16 — Recência com base explícita (V13)

## Resultado

- Regra única `data_de_referencia = published_at ?? source_updated_at ?? first_seen_at`:
  `opportunities/domain.py` (`recency_reference`, `recency_basis_of`, `recency_decision`) e o
  espelho SQL em `opportunities/repository.py` (`recency_reference_expression`,
  `recency_condition`, usado pela Inbox em `dashboard/queries.py::_recency_condition` e por
  `/opportunities`). Teste de espelho:
  `tests/backend/dashboard/test_recency_mirror_integration.py` (grade de entradas, Python x SQL).
- `opportunity.recency_basis` (`published`, `updated`, `first_seen`) persistida, com CHECK.
  Migração `20260929_0057_recency_basis` (backfill pelas duas datas anuláveis; upgrade/downgrade
  testado em `tests/backend/test_recency_basis_migration_integration.py`). O normalizador grava
  na criação e no refresh (`_apply_evidence_fields`), então um `source_updated_at` mais novo
  reposiciona a vaga na janela.
- Janela padrão da Inbox: **30 dias** (`DEFAULT_RECENCY_WINDOW_DAYS`, decisão 3 do spec 48).
  Lentes: "Novas (14 dias)" = `recency_window_days=14`; "Abertas na fonte" = `open_at_source=true`
  (alguma ocorrência vista na última run `complete` da própria fonte, sem limite de data; troca
  a janela). Exceção de programa com prazo (`recency_exempt_program`, `valid_through` futuro)
  mantida.
- API: `recency_basis` na Inbox e no detalhe; `date_is_estimated` vale para `updated` e
  `first_seen`. UI: "(estimada)" com dica quando a base não é `published` (linha da Inbox,
  cartão e detalhe); lente como `FilterPill` "Recência".
- O penhasco de 2026-10-13 não atinge vaga com `source_updated_at` recente
  (`test_2026_10_13_cliff_does_not_hit_a_job_with_recent_source_updated_at`).

## Fora do escopo

- Ordenação "Mais recentes" continua por `published_at` (nulos por último).
- Lente "Abertas na fonte" não exclui `CLOSED`; o status segue filtrável à parte.
