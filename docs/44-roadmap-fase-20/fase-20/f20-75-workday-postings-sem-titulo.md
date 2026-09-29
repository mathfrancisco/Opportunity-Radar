# CARD F20-75 — Coletor Workday: postagem sem título é `skipped`, não inválida

- **Status:** Feito (2026-09-29) — correção e testes; re-execução real da Accenture
  pendente.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-74
- **Origem:** re-execução da Accenture após F20-74 terminou `PARTIAL` com `INVALID_ITEM`
  (11 postagens sem `title`; ver
  [`f20-74-workday-paginacao-cap-2000.md`](f20-74-workday-paginacao-cap-2000.md)).

## Causa

O coletor tratava `Workday posting is missing a title` como item malformado
(`record_invalid_item`), o que o serviço converte em `items_invalid` e `PARTIAL`. Postagem
sem título não é oportunidade nem sinal de mudança de esquema: não deve degradar o run.

## Correção

Nenhum coletor tinha caminho de "ignorado" (só `invalid`), então o mínimo foi espelhar o
contador de inválidos:

- `acquisition/domain.py`: `CollectionTelemetry.skipped_items` + `record_skipped_item()`.
- `acquisition/service.py`: `skipped_items` entra em `items_seen` e `items_skipped` do run;
  não gera erro nem `PARTIAL`.
- `acquisition/workday.py`: postagem sem `title` (ausente ou em branco) é contada como
  `skipped` antes de `_item`. Demais defeitos (sem `externalPath`, `bulletFields`
  inválido) continuam `invalid`.

## Critérios de aceite

- [x] Página com postagens sem título: `telemetry.skipped_items == 2`, `invalid_items == 0`,
      só o item válido é emitido — `test_untitled_posting_is_skipped_not_invalid`.
- [x] Via `service.execute`: run `SUCCEEDED`, sem `error_code`, `items_seen 2`,
      `items_persisted 1`, `items_skipped 1`, `items_invalid 0` —
      `test_workday_untitled_postings_count_as_skipped_and_do_not_degrade_the_run`.
- [x] Item malformado por outro motivo continua inválido —
      `test_skips_malformed_listed_job_and_reports_it` (inalterado).
- [ ] Re-execução real da Accenture (coordenador): esperado `SUCCEEDED`, `items_skipped` 11.
