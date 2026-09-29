# F48-09 — Identidade: refresh na mesma `external_id` e finder de duplicatas em `REVIEW` (V12, V11)

## Resultado

- A mesma `external_id` da fonte com impressão nova atualiza a oportunidade
  (`_refresh_opportunity`: campos derivados refeitos, `version` incrementada só se algum valor
  mudou), grava a impressão nova e devolve `REFRESHED` /
  `IDENTITY_REFRESHED_SAME_EXTERNAL_ID`. A mudança fica em
  `closure_evidence["identity_refresh"]` (impressão anterior e nova, raw item, instante); o
  histórico completo continua nos `normalization_result`.
- `REVIEW_REQUIRED` (`EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`) só quando **outra** oportunidade
  já é dona da impressão nova: as duas disputam a identidade e nada é atualizado.
- Oportunidade criada como `REVIEW` (`SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY`) também roda
  `find_title_location_window_candidates`; os pares viram `duplicate_candidate` `PENDING`. Nada é
  fundido automaticamente.
- `scripts/backfill_identity_refresh.py` (`--dry-run`) apaga os `normalization_result` da versão
  corrente com esse motivo cujo raw item ainda é o conteúdo vigente da ocorrência; o próximo
  `normalize_pending` os refaz pela regra nova. Oportunidades, ocorrências e raw items não são
  tocados; idempotente.

## Decisão: `fingerprint_version`

Mantida em `v1`. Com o refresh na mesma `external_id`, uma mudança de regra (ex.: `work_mode`
do `13d6605`) deixa de ser "mudança de identidade": a impressão é recalculada e gravada em
lugar. Subir para `v2` exigiria migrar todas as linhas ou deixaria `v1` e `v2` sem se
encontrarem em `opportunity_by_fingerprint`, sem ganho para o problema que o card resolve.

## Limites

- Conteúdo antigo (`fetched_at` anterior ao vigente) não atualiza nada e não é disputa.
- Um refresh que muda título ou local não roda o finder de janela (só criação); fica para um
  card próprio se medir necessidade.

## Verificação

Testes em `tests/backend/opportunities/test_identity_refresh.py` (refresh com `work_mode`
diferente, disputa entre duas oportunidades, par AIG "Collections Supervisor" a 3 dias gera
`PENDING`, backfill `--dry-run` não escreve).

Backfill (não executado contra o banco real): `python scripts/backfill_identity_refresh.py
--dry-run`, depois sem a flag e `normalize_pending`.
