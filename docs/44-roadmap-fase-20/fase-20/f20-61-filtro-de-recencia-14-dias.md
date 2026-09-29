# CARD F20-61 — Filtro de recência (14 dias) com exceção para estágio/programas com prazo

- **Status:** Feito — mesclado em `feature/f20-groq-e-consolidacao` (`5a1e062`), CI verde em `13d6605`; volume real de junior/estágio/programa-com-prazo (nota do item 5, não critério de aceite) segue no backlog da próxima fase (`validacao-pendente.md` §7)
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-01, F20-03
- **Origem:** pedido do usuário em 2026-09-28 — regra de produto: por padrão, a busca mostra
  só vaga postada nos últimos 14 dias (vaga mais antiga é provavelmente já preenchida);
  exceção para estágio/trainee/programas de início de carreira/residência e para vaga com
  janela/prazo explícito de candidatura, que ficam visíveis mesmo além dos 14 dias.

## Contexto (investigação de código feita antes deste card)

Levantamento em `src/opportunity_radar/opportunities/` e `src/opportunity_radar/acquisition/`
para saber quais coletores têm data real de publicação e qual é o fallback:

- `Opportunity.published_at` (`opportunities/models.py:112`, índice
  `ix_opportunity_published`) e `SourceOccurrenceModel.source_published_at`
  (`opportunities/models.py:324`) guardam a data de publicação **real**, quando a fonte
  fornece — vem de `CollectedItem.published_at` (`acquisition/domain.py:329`), setado no
  candidato e propagado em `opportunities/service.py:206,254,951,1029`.
  - Coletores que setam `published_at` a partir de um campo real da fonte: `ashby.py:285`
    (`publishedAt` do JSON do board), `teamtailor.py:316` (`date_published`),
    `remotive.py:304` (campo próprio da API pública do Remotive), `jobposting.py:485`
    (`datePosted` do `schema.org` `JobPosting`).
  - Coletores que **não** setam `published_at` (fica `None` sempre): `greenhouse.py`,
    `lever.py`, `workday.py`, `workable.py`, `factorial.py` — nenhum campo real de data de
    publicação foi encontrado nas respostas desses ATS que os coletores atuais consomem
    (confirmado por grep: zero ocorrência de `published_at`/`posted_at`/`date_posted` nesses
    cinco arquivos).
- **Fallback**: `SourceOccurrenceModel.first_seen_at` é setado de `raw_item.fetched_at`
  (`opportunities/service.py:251`) — a data em que o radar *viu* a vaga pela primeira vez,
  não a data real de publicação. Quando `published_at` é `None`, este card usa
  `first_seen_at` como data estimada e precisa marcar isso explicitamente (campo
  `date_is_estimated` ou equivalente na resposta da API) — nunca apresentar `first_seen_at`
  como se fosse a data real de publicação sem essa marca.
- **Prazo de candidatura**: `schema.org` `JobPosting` tem `validThrough`, já parseado em
  `jobposting.py:58,217,275` como `valid_through` — mas esse campo **não está propagado**
  para `CollectedItem`/`Opportunity` (grep confirma zero ocorrência de `valid_through` fora
  de `jobposting.py`). Este card precisa adicionar esse campo ao domínio (`CollectedItem`,
  `Opportunity`) para os coletores que o expõem (hoje só o `jobposting.py`); para os demais
  ATS, "janela de candidatura explícita" fica sempre ausente — o card não deve inventar
  data para quem não a expõe.
- **Estágio/trainee/early-careers**: `ContractType.INTERNSHIP`
  (`opportunities/domain.py:963`) já classifica por regex de título
  (`\binternship\b`, `\best[aá]gio\b`) — usável como sinal de exceção sem trabalho novo de
  classificação. "Residência"/"programa de início de carreira" (`residency`, `trainee`,
  `early-careers`) **não têm regex própria hoje** — este card precisa estender o padrão de
  `ContractType` ou criar um sinal de exceção separado (`is_time_boxed_program` ou
  equivalente) cobrindo esses termos, sem forçar um `ContractType` que não existia antes
  (ex.: "trainee" não é o mesmo que "internship" para o resto do sistema).

## Escopo

1. Campo de exceção "programa com prazo/início de carreira" (estágio, trainee,
   early-careers, residência) — reusa `ContractType.INTERNSHIP` já existente e adiciona
   reconhecimento equivalente para `trainee`/`residency`/`early career` (regex em pt-BR e
   en, mesmo padrão de `_CONTRACT_TYPE_PATTERNS`), sem virar um `ContractType` novo — é um
   sinal de "aplica exceção de recência", independente do tipo de contrato.
2. Campo de "janela de candidatura explícita" — thread `valid_through` (schema.org
   `JobPosting`, já parseado em `jobposting.py`) até `CollectedItem` e `Opportunity`; vaga
   com essa data no futuro fica visível mesmo além de 14 dias, com ou sem ser estágio.
3. Cálculo de recência no backend (não só no frontend): dado
   `published_at ?? first_seen_at` (nessa ordem, com marca de estimativa quando cai no
   fallback) e a janela configurada (padrão 14 dias), decidir se a oportunidade aparece na
   listagem por padrão. Endpoint HTTP (`presentation/http/opportunities.py`) expõe um
   parâmetro para o cliente pedir "sem filtro de recência" (todas as vagas) — o padrão do
   servidor, sem esse parâmetro, já aplica o filtro.
4. UI (`apps/web`, Inbox/Overview): filtro **ligado por padrão**; controle visível para o
   usuário desligar e ver tudo (mesmo padrão de toggle dos outros filtros já existentes —
   ver `apps/web/src/features/opportunities/`).
5. Métrica/nota de volume: registrar, na mesma tela ou em log, quantas vagas de
   estágio/trainee/junior existem no total, para medir depois (fora deste card) se o volume
   é baixo demais para a exceção valer a pena — não é um critério de aceite, é observação
   para acompanhar.

## Fora de escopo

- Mudar `published_at`/`first_seen_at`/`valid_through` em `score`, elegibilidade ou veredito
  do matching (mesma invariante da Fase 20: saída de recência não altera esses três campos).
- Inventar `valid_through` para coletores que não expõem essa data (Greenhouse, Lever,
  Workday, Workable, Factorial, Ashby, Teamtailor, Remotive continuam sem essa data até
  algum deles passar a expor no futuro).
- Medir o volume real de vaga junior/estágio no acervo (fica só como nota, "a medir depois"
  no critério 5) — não é um teste de aceite deste card, é um lembrete explícito de que o
  volume pode ser baixo e a exceção pode não mover muito o resultado.

## Critérios de aceite

- [x] Vaga com `published_at` (ou `first_seen_at` de fallback) há 13 dias aparece na
      listagem padrão (filtro ligado); vaga com 15 dias não aparece — teste cobrindo os dois
      lados do limite de 14 dias, com o mesmo instante de referência controlado no teste
      (não `datetime.now()` sem congelar).
- [x] Vaga classificada como estágio/trainee/early-careers/residência com 60 dias desde
      `published_at`/`first_seen_at` continua aparecendo na listagem padrão (exceção não
      expira aos 14 dias) — teste com título/sinal de estágio e data de 60 dias atrás.
- [x] Vaga sem `published_at` (coletor que não expõe essa data) usa `first_seen_at` como
      fallback e vem marcada como data estimada na resposta da API (campo booleano ou
      enum explícito) — teste garantindo que o fallback participa do cálculo de recência e
      que a marca de estimativa está presente e correta (`True` no fallback, `False` quando
      `published_at` é real).
- [x] Vaga com `valid_through` (prazo de candidatura) no futuro aparece na listagem padrão
      mesmo com `published_at` mais antigo que 14 dias, sem precisar ser estágio — teste
      cobrindo `jobposting.py` (única fonte hoje com essa data).
- [x] Com o filtro desligado pelo usuário (parâmetro/toggle), toda vaga aparece,
      independente de idade, tipo de contrato ou `valid_through` — teste de componente (UI)
      e de contrato de API (parâmetro presente vs. ausente) confirmando que o padrão do
      servidor é filtrar e que o toggle desligado remove o filtro por completo.

## Verificação

- **CI:** testes de unidade para o cálculo de recência (backend, `opportunities/domain.py`
  ou módulo próprio) cobrindo os cinco critérios acima com tempo congelado; teste de
  contrato do endpoint HTTP (parâmetro presente/ausente); teste de componente React para o
  toggle (ligado por padrão, desliga ao clicar, mostra tudo).
- **Máquina de referência:** nenhuma — filtro é determinístico sobre dado já coletado, sem
  dependência de Groq/Tavily/acervo real. Se a nota de volume (item 5 do escopo) exigir
  consulta ao acervo real, isso é medição separada, registrada como pendência em
  `docs/44-roadmap-fase-20/validacao-pendente.md`, não um critério de aceite deste card.

## Arquivos prováveis

- `src/opportunity_radar/opportunities/domain.py` (sinal de exceção estágio/trainee/
  early-careers/residência; cálculo de recência)
- `src/opportunity_radar/acquisition/domain.py`, `jobposting.py` (propagar `valid_through`
  até `CollectedItem`)
- `src/opportunity_radar/opportunities/models.py`, `service.py` (persistir `valid_through`
  em `Opportunity`/`SourceOccurrenceModel`; marca de data estimada)
- `src/opportunity_radar/presentation/http/opportunities.py` (parâmetro de filtro/toggle,
  campo de data estimada na resposta)
- `apps/web/src/features/opportunities/` (toggle de recência na Inbox/Overview)
- `tests/backend/opportunities/test_recency_filter.py` (novo)
- `apps/web/src/features/opportunities/*.test.tsx` (novo ou existente, teste do toggle)

## Não fazer

- Não alterar `score`, elegibilidade ou veredito do matching por causa da idade da vaga.
- Não inventar `published_at`/`valid_through` para coletor que não expõe essa data — usar o
  fallback marcado como estimado, nunca fingir que é data real.
- Não medir o volume real de vaga junior/estágio como parte deste card — só registrar a nota
  de que precisa ser medido depois.

## Comando de verificação

```bash
docker compose -p f20-61 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/opportunities/test_recency_filter.py
docker compose -p f20-61 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-61 -f compose.yaml -f compose.dev.yaml run --rm api mypy
npm run check --prefix apps/web
```

## Pronto quando

Todos os critérios de aceite estão marcados com evidência (incluindo os quatro testes de
limite/exceção/fallback/toggle), o comando de verificação passa e o CI está verde.

## Evidência de implementação

- Testes: `tests/backend/opportunities/test_recency_filter.py` (limites 13/14/15 dias com `now` congelado, exceção de programa aos 60 dias, fallback `first_seen_at` marcado estimado, `valid_through` futuro), `tests/backend/test_recency_filter_http_integration.py` (`/inbox` e `/opportunities`: padrão filtra, `only_recent=false` mostra tudo), `apps/web/src/routes/InboxPage.test.tsx` (toggle ligado por padrão, desliga enviando `only_recent=false`).
- Filtro SQL em `dashboard/queries.py` (`_recency_condition`) e `opportunities/repository.py`; regra pura em `opportunities/domain.py` (`recency_decision`). Migração `20260928_0053`.
- `published_at` real agora em: Lever (`createdAt`), Workable (`published_on`), Workday (`postedOn` relativo, limite inferior). Greenhouse (só `updated_at`, não é publicação) e Factorial (sem data) seguem com fallback estimado.
- F20-73 absorvido: exceção de programa (estágio/trainee/residência/early careers) implementada (`recency_exempt_program`).
