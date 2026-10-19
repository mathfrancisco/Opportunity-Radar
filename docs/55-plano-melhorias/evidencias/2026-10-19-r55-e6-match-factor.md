# R55-E6: `matching.match_factor` e `match_assessment`

## Achados

- `match_factor` guarda, por avaliação, os 8 fatores de `DEFAULT_FACTORS` (código, peso,
  `raw_score`, contribuição, status KNOWN/UNKNOWN/NOT_APPLICABLE, confiança, política de
  ausência, `explanation` em texto livre e `evidence_refs` JSONB). Tem 8 linhas por avaliação
  porque a avaliação sempre produz todos.
- Leitores: `GET` de avaliação em `presentation/http/matching.py` (`_factor_response`, todos os
  fatores ordenados por código) e a tabela `Factors` de `apps/web/src/routes/OpportunityDetailPage.tsx`
  (peso, contribuição, status e, para UNKNOWN, a política de ausência). Nenhum dashboard nem prompt
  de IA lê a tabela. O prompt usa os snapshots da avaliação.
- Os fatores **não são deriváveis**: `explanation` e `evidence_refs` são produzidos pela regra no
  momento da avaliação, e a nota depende de `raw_score`/peso (renormalização de
  `EXCLUDE_AND_RENORMALIZE`). Um fator UNKNOWN ou NOT_APPLICABLE é justamente o que explica o que a
  nota não enxergou.
- Imutabilidade: triggers `prevent_match_assessment_mutation` / `prevent_match_factor_mutation`
  recusam UPDATE e DELETE; só `matching.allow_prune` (por transação) deixa o DELETE passar
  (migração 0064).
- Índices de `match_factor`: PK, `uq_match_factor_assessment_code (assessment_id, factor_code)` e
  `ix_match_factor_assessment (assessment_id)`. O último é prefixo estrito do unique: nenhuma
  consulta ou cascata por `assessment_id` o exige.
- Poda (R55-E6 anterior, `operations/assessment_retention.py`): apaga avaliações superadas há mais
  que a janela, deleta os fatores explicitamente antes, e nunca apaga a corrente
  (`current_assessment`), nem as com análise, claim ou candidatura. Regra "corrente + anterior
  dentro da janela" confirmada por testes existentes e por um novo.

## Opções avaliadas

| Opção | Decisão |
|---|---|
| (a) gravar só fatores decisivos e derivar o resto | Rejeitada: a UI e a API exibem todos; explicação/evidência não são deriváveis; mudaria a semântica da auditoria. Ganho estimado de ~30% das linhas, ao custo de perder o "o que não se sabe". |
| (b) remover índice redundante | **Escolhida.** Sem mudança de dados, reversível. |
| (c) poda de superadas leva os fatores | Já correta; coberta por teste novo (todos os fatores da avaliação podada somem, os da corrente ficam). |
| (d) compactar JSON/texto de `match_assessment` | Rejeitada neste cartão: os snapshots são insumo da análise de IA e da reprodutibilidade (`input_hash`); JSONB acima de 2 KB já é comprimido em TOAST. Reduzir exigiria mudar o formato do snapshot (e tende a pedir nova versão de regras). |

Nenhuma reavaliação em massa e nenhum bump de `rules_version`: nenhum dado ou resultado muda.

## Mudança

- Migração `20261018_0076` (down_revision `20261017_0075`): `DROP INDEX IF EXISTS
  matching.ix_match_factor_assessment`. Downgrade recria o índice.
- `MatchFactorModel` sem o `Index` correspondente (modelo e banco coerentes).

## Testes

`tests/backend/matching/test_match_factor_storage.py` (Postgres em Docker):
- positivo: índice redundante ausente, unique presente e usado pelo plano (`EXPLAIN` com
  `enable_seqscan=off`) para `WHERE assessment_id = ...`;
- positivo: avaliação podada leva todos os seus fatores; a corrente mantém os seus;
- negativo: a resposta da API contém os 8 fatores, inclusive UNKNOWN e NOT_APPLICABLE, ordenados
  e com política de ausência, `raw_score` nulo e explicação, como a UI precisa.
O frontend não foi alterado, então seus testes não foram reexecutados.

## Economia esperada

Medida em tabela sintética de mesma forma (53,6 mil linhas): o índice redundante ocupa ~650 KB
(unique 2,4 MB, PK 2,2 MB). Em produção (57 mil linhas, 7 MB de índices) a economia é de ~0,7 MB
(~10% dos índices de `match_factor`, ~1,8% do par de tabelas) e menos custo de escrita por
avaliação. É pequena de propósito: o grosso (snapshots e texto de explicação) é informação de
auditoria que a UI e a IA usam. O maior ganho continua sendo a poda de superadas
(`OPPORTUNITY_RETENTION_APPLY`).

## Reversão

`alembic downgrade 20261017_0075` recria o índice. Sem perda de dados.

## Riscos

- Nenhum plano de consulta existente depende do índice removido (todas as consultas por
  `assessment_id` usam o prefixo do unique). Em produção, `DROP INDEX` toma lock exclusivo breve na
  tabela.
- `tests/backend/fixtures/pre_f20_dump.sql` ainda cria o índice; a migração usa `IF EXISTS`.
