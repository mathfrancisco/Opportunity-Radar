# F48-14 — Prioridade de empresa separada da maturidade da pesquisa (V05)

## Resultado

- Campo novo `company.research_confidence` (`low`/`normal`/`high`, operacional). Migração
  `20260929_0060_company_research_confidence` (backfill = prioridade atual, que era o que o
  importador gravou; não reescreve `priority`).
- `scripts/import_research_catalog.py`: empresa nova entra com `priority = normal`; a maturidade
  (`ResearchRow.research_confidence`: `api json` = high, `ats identificado` = normal, resto =
  low) vai só para `research_confidence` e só sobe. Empresa existente nunca tem `priority`
  alterada pelo importador. Curadoria manual só para `high`/`blocked`.
- Ordem padrão da Inbox (`InboxOrder.PRIORITY`, valor mantido por compatibilidade da API):
  `score desc, published_at desc, id`. A prioridade entra só como fator do score
  (`COMPANY_PRIORITY`). Agrupamento F48-10 intacto. A fila de homologação de fontes
  (`list_source_health`) continua ordenada por prioridade da empresa.
- Agenda de coleta (`scheduling.py`): a cadência segue só `Company.priority`;
  `research_confidence` nunca a rebaixa para semanal. Como novas empresas entram `normal`
  (diária), a agenda muda sozinha para as novas; as antigas `low` mudam ao reclassificar.
- `scripts/reclassify_company_priority.py [--dry-run]`: `low` -> `normal` só quando
  `priority = low`, `research_confidence = low` e `version = 1`. O sinal de "usuário editou" é
  `version`: `CompanyRegistration.update` incrementa a cada edição e o importador nunca; `updated_at`
  não serve porque o importador também o move. Empresas editadas são contadas
  (`kept_low_user_edited`) e mantidas.

## Testes

- `tests/backend/test_research_catalog_import.py` (mapeamento, empresa importada = normal/normal).
- `tests/backend/dashboard/test_queries.py::test_inbox_default_order_is_score_then_recency_not_company_priority`.
- `tests/backend/test_reclassify_company_priority.py` (dry-run e execução real).

## Fora do escopo

- Não rodar o script contra o banco real neste card; `high` importadas antes ficam como estão.
