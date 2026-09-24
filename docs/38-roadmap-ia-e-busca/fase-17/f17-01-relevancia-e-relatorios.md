# CARD F17-01 — Marcação de relevância e relatórios de cobertura e precisão

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** Nenhum
- **Bloqueia:** F17-02, F17-03, F17-06, F17-08, F16-11, Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §3, §13

## Resultado

O operador marca cada vaga como relevante ou não, e o radar passa a medir o que esta fase
promete melhorar: quantas vagas relevantes entram, quantas das mostradas servem, quantas
se repetem e o que a busca acha. O valor inicial de cada métrica fica registrado antes de
qualquer outro card mexer nelas.

## Contexto

Nenhuma métrica da SPEC §3 existe hoje. Sem elas, os cards de volume (F17-04, F17-10,
F17-11) poderiam dobrar a quantidade de vagas e piorar a Inbox sem ninguém perceber, e os
cards de precisão não teriam como provar que ajudaram.

## Escopo

- **Marcação de relevância:**
  - tabela `opportunities.relevance_mark` — `id`, `opportunity_id`, `relevant` (bool),
    `reason` (`AREA`, `SENIORITY`, `LOCATION`, `COMPANY`, `COMPENSATION`, `OTHER`, opcional
    quando relevante), `note`, `profile_version_id`, `marked_at`; histórico append-only, a
    marca atual é a mais recente;
  - `POST /opportunities/{id}/relevance` e a marca atual na resposta da Inbox e do detalhe;
  - na Inbox e no detalhe, dois botões ("Relevante", "Não é para mim") com motivo opcional
    num menu curto. A marca não entra no score: é dado de avaliação.
- **Relatório de cobertura** (`GET /search-metrics?window=7d`, bloco `coverage`), por fonte
  e total: execuções, itens vistos, persistidos, repetidos e inválidos, vagas novas,
  empresas cobertas ÷ empresas com ATS identificado, taxa de senioridade `UNKNOWN`.
- **Relatório de precisão** (bloco `precision`): precisão das 50 primeiras da Inbox na
  ordem padrão, calculada só sobre as marcadas, com a contagem de marcadas ao lado — sem
  marcação suficiente, a precisão é `null`, não um número frágil.
- **Amostra de duplicatas:** `scripts/sample_duplicates.py` sorteia 50 pares de vagas da
  mesma empresa com títulos parecidos (similaridade de trigramas) para o operador julgar;
  o resultado alimenta a taxa de duplicatas.
- **Conjunto de referência da busca:** `scripts/search_reference.py` mantém
  `data/search-reference/queries.json` (fora do git: é do acervo local) com 40 consultas e,
  para cada uma, as vagas relevantes marcadas. O mesmo arquivo é usado pelo F17-03 e pelo
  F16-10.
- **Visão geral:** linha de apoio no bloco "Acervo" — "7 dias: N vagas novas · precisão X%
  (M marcadas) · Y empresas cobertas de Z".
- **Baseline:** relatório em `docs/pesquisas/` com o valor inicial de cada métrica da SPEC
  §3.

## Fora de escopo

- Usar a marca no score ou no veredito.
- Aprendizado a partir das marcas.

## Notas de implementação

- "Empresas cobertas" = empresas com pelo menos uma `SourceDefinition` habilitada;
  "empresas com ATS identificado" = empresas com `CompanySource` de tipo com coletor.
- O conjunto de referência fica fora do git porque os ids são do banco local; o script
  exporta e importa por URL canônica da vaga, para sobreviver a restauração de backup.
- A marca guarda a versão do perfil: uma vaga irrelevante para o perfil de hoje pode ser
  relevante para o de amanhã, e a precisão é calculada contra o perfil ativo.

## Critérios de aceite

- [ ] O operador marca relevância pela Inbox e pelo detalhe, com motivo opcional.
- [ ] `GET /search-metrics` devolve cobertura e precisão, com `null` onde não há dado.
- [ ] O conjunto de referência pode ser criado, exportado e importado pelo script.
- [ ] A Visão geral mostra a linha de apoio.
- [ ] O baseline de todas as métricas da SPEC §3 está registrado.

## Verificação

- **CI:** testes de integração da marcação (histórico e marca atual), do endpoint com dados
  fixos (precisão calculável e `null`), do script de referência (ida e volta por URL); E2E
  marcando uma vaga e conferindo a métrica.
- **Máquina de referência:** o relatório de baseline é o entregável manual.

## Arquivos prováveis

- `migrations/versions/*_relevance_mark.py`
- `src/opportunity_radar/opportunities/models.py`, `dashboard/queries.py`
- `src/opportunity_radar/presentation/http/opportunities.py`, `dashboard.py`
- `scripts/sample_duplicates.py`, `scripts/search_reference.py` (novos)
- `apps/web/src/routes/InboxPage.tsx`, `OpportunityDetailPage.tsx`, `OverviewPage.tsx`
