# CARD F17-01 — Marcação de relevância e relatórios de cobertura e precisão

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** Nenhum
- **Bloqueia:** F17-02, F17-03, F17-06, F17-08, F17-13, F18-01, Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §3, §13

## Resultado

O operador marca cada vaga como relevante ou não, e o radar passa a medir o que esta fase
promete melhorar: quantas vagas relevantes entram, quantas das mostradas servem, quantas
se repetem e o que a busca acha. O baseline disponível fica registrado antes de alterar o ranking. Métricas de
funções futuras ficam nulas, com motivo e card responsável; cada entrega registra
sua comparação antes/depois.

## Contexto

Nenhuma métrica da SPEC §3 existe hoje. Sem elas, os cards de volume (F17-04, F17-10,
F17-11) poderiam dobrar a quantidade de vagas e piorar a Inbox sem ninguém perceber, e os
cards de precisão não teriam como provar que ajudaram.

## Escopo

- **Marcação de relevância:**
  - tabela `opportunities.relevance_mark` — `id`, `opportunity_id`, `relevant` (bool),
    `reason` (`AREA`, `SENIORITY`, `LOCATION`, `COMPANY`, `COMPENSATION`, `OTHER`, opcional
    quando relevante), `note`, `profile_version_id`, `opportunity_version`, `marked_at`; histórico append-only, a
    marca atual é a mais recente;
  - `POST /opportunities/{id}/relevance` e a marca atual na resposta da Inbox e do detalhe;
  - na Inbox e no detalhe, dois botões ("Relevante", "Não é para mim") com motivo opcional
    num menu curto. A marca não entra no score: é dado de avaliação.
- **Relatório de cobertura** (`GET /search-metrics?window=7d`, bloco `coverage`), por fonte
  e total: execuções, itens vistos, persistidos, repetidos e inválidos, vagas novas,
  empresas cobertas ÷ empresas com ATS identificado, taxa de senioridade `UNKNOWN`.
- **Relatório de precisão** (bloco `precision`): precisão das 50 primeiras da Inbox na
  ordem padrão em snapshot congelado. P@50 só é publicada com as 50 julgadas;
  menos vagas disponíveis usa P@k identificado. Julgamento parcial mostra taxa
  observada e suporte, mantendo P@50 nula.
- **Amostra de duplicatas:** `scripts/sample_duplicates.py` sorteia 50 pares de vagas da
  mesma empresa com títulos parecidos (similaridade de trigramas) para o operador julgar;
  o resultado mede duplicação entre candidatos. Uma amostra aleatória de
  oportunidades, revisada contra suas ocorrências, mede a taxa global separadamente.
- **Conjunto de referência da busca:** `scripts/search_reference.py` mantém
  `data/search-reference/queries.json` (fora do git: é do acervo local) com 40 consultas e,
  para cada uma, as vagas relevantes marcadas. O mesmo arquivo é usado pelo F17-03 e pelo
  F16-10.
- **Visão geral:** linha de apoio no bloco "Acervo" — "7 dias: N vagas novas · precisão X%
  (M marcadas) · Y empresas cobertas de Z".
- **Baseline:** relatório em `docs/pesquisas/` com o valor inicial das métricas
  disponíveis da SPEC §3, com denominadores e limitações.

## Fora de escopo

- Usar a marca no score ou no veredito.
- Aprendizado a partir das marcas.

## Notas de implementação

- Contar empresas canônicas. Denominador ATS inclui tipos sem coletor; registrar
  também total do catálogo. Não confundir 222 registros pesquisados com empresas.
- Separar fonte proposta, homologada, habilitada e cobertura operacional: coleta
  completa dentro da janela configurada. Uma fonte falhando não prova cobertura.
- Congelar ranking, corpus, perfil, filtros, regras e julgamentos de cada medição.
  Amostra fora do top 50 inclui fontes, áreas, idiomas e UNKNOWN.
- Referência de busca exporta URL canônica e snapshot/hash do conteúdo, julgamentos
  e configuração; ids locais não bastam para reconstruir uma comparação.
  Separar consultas de ajuste e reservadas; reportar o número de relevantes.
- A marca guarda perfil e versão da vaga julgada. Mudança material torna a marca
  antiga histórica, sem tratá-la como avaliação do texto novo.
- F18-01 complementa este endpoint com produtividade da aquisição, sem duplicar
  métricas. Métricas indisponíveis têm null e motivo, não zero.

## Critérios de aceite

- [ ] O operador marca relevância pela Inbox e pelo detalhe, com motivo opcional.
- [ ] `GET /search-metrics` devolve cobertura e precisão, com `null` onde não há dado.
- [ ] O conjunto de referência pode ser criado, exportado e importado pelo script.
- [ ] A Visão geral mostra a linha de apoio.
- [ ] Baseline disponível e responsáveis pelas métricas ainda indisponíveis registrados.
- [ ] Denominadores incluem ATS sem coletor; habilitada e operacional são distintos.
- [ ] Julgamentos incompletos não produzem P@50; fixtures cobrem ambos os casos.
- [ ] Snapshot exportado permite repetir a comparação após alterações no acervo.

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
