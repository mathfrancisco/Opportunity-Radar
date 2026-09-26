# Curadoria manual de `skills-v2` (F20-02)

- **Status:** Medido e curado na máquina de referência.
- **Card:** [F20-02](../44-roadmap-fase-20/fase-20/f20-02-curadoria-skills-v2.md)
- **Fecha:** [F17-06](../38-roadmap-ia-e-busca/fase-17/f17-06-normalizacao-mais-precisa.md)
  (parcialmente — ver limitação sobre a versão da taxonomia)
- **Medido em:** 2026-09-26, `docker compose exec api python scripts/unmatched_skill_terms.py`
  contra o acervo real (648 oportunidades, 630 descrições não vazias).

## Saída do script (termos sem entrada na taxonomia, top 60, min-count 2)

```
630 descriptions scanned; 60 candidate terms shown.
481  data       477  build      473  every      467  across     462  ai
453  how        450  business   447  more       421  into       403  be
396  real       396  platform   395  tools      390  all        388  help
388  support    382  technical  376  than       374  what       369  not
369  teams      367  re         367  make       366  ll         364  if
361  engineering 361 product    361  scale      359  working    357  growth
356  us         355  time       354  looking    352  new        352  design
351  building   350  company    350  through    346  impact     340  use
340  learning   339  benefits   329  can        328  solutions  327  it
324  built      321  tech       320  systems    316  customer   311  equity
308  strategy   307  love       303  other      301  high       299  fast
299  provide    298  customers  298  process    297  insurance  296  development
```

(saída completa, 400 termos, disponível reproduzindo o comando acima com `--top 400`).

## Por que a lista é majoritariamente ruído

O script (`scripts/unmatched_skill_terms.py`) conta tokens de uma palavra só (regex
`[a-zA-Z][a-zA-Z0-9+#.]{1,}`) que passam por uma lista de stopwords deliberadamente não
exaustiva — o comentário do próprio script diz isso. Sobre o acervo real, a maior parte do
texto das vagas é boilerplate de RH em inglês (benefícios, EEOC, "who we are"), não
vocabulário técnico. Isso não é um bug do script; é o motivo de cada termo continuar
exigindo revisão humana, como o docstring do script já avisa.

## Decisão por termo (candidatos com sinal técnico real)

| Termo | Contagem | Decisão | Motivo |
| --- | --- | --- | --- |
| `ai` | 462 | **nova skill** (`ai`) | Altíssima frequência, termo técnico inequívoco (IA/machine learning), zero cobertura na `skills-v1`. Aliases: `ai`, `artificial intelligence`, `machine learning`, `ml`, `agentic ai` (termo emergente também observado no corpus, ex. "agentic AI systems"). |
| `ci` | 218 | **alias de `ai`?** não — **nova skill** (`cicd`) | "CI" isolado é ambíguo em prosa geral, mas no corpus real aparece consistentemente ao lado de "CD"/"CI/CD" em contexto de plataforma/infra (ex.: "observability, CI/CD, developer environments"). Aliases: `ci/cd`, `ci`, `continuous integration`, `continuous deployment`. Risco documentado: `ci` sozinho (2 letras) pode ter falso positivo maior que os termos `go`/`react` já tratados como ambíguos no código; não implementei a mesma desambiguação por contexto (fora do escopo de arquivos do card — só a tupla `SKILL_TAXONOMY` e testes). |
| `observability` | 124 | **nova skill** (`observability`) | Termo técnico inequívoco de plataforma/SRE, sem ambiguidade, alta frequência. |
| `apis` | 146 (não top 60, presente na lista de 400) | **descartado** | Genérico demais — qualquer vaga backend menciona "APIs"; não identifica uma skill discreta sem uma taxonomia própria de protocolos (REST/GraphQL — GraphQL já existe). |
| `cloud` | 193 (lista de 400) | **descartado** | Ambíguo por natureureza; a taxonomia já cobre provedores específicos (`aws`, `azure`, `gcp`). Adicionar `cloud` genérico arrisca casar em contexto não técnico ("cloud of possibilities" etc.) e duplica sinal que os provedores específicos já capturam. |
| `sdlc` | 183 (lista de 400) | **descartado** | Sigla de processo (Software Development Life Cycle), não uma skill técnica discreta — mais próximo de metodologia do que de tecnologia, fora do padrão das 27 entradas atuais (linguagens, frameworks, bancos, cloud, IaC). |
| `martech` | 178 (lista de 400) | **descartado** | Categoria de produto/marketing, fora da área do perfil (Backend Engineer) e fora do tipo de entrada que a taxonomia modela. |
| `architecture` / `systems` / `platform` / `frameworks` / `tools` / `stack` | alto (lista de 400) | **descartado** | Palavras-guarda-chuva; sem uma tecnologia nomeada, marcar como skill geraria ruído maciço (qualquer vaga de engenharia usa essas palavras). |
| `agentic` | 140 (lista de 400) | **incorporado como alias de `ai`** | Ver linha `ai` acima — não é uma skill isolada, é uma variação de IA (sistemas de agentes). |

## Entradas adicionadas em `SKILL_TAXONOMY`

Arquivo: `src/opportunity_radar/opportunities/domain.py`, dentro da tupla
`SKILL_TAXONOMY` (27 → 30 entradas):

```python
SkillTaxonomyEntry(
    "ai",
    ("ai", "artificial intelligence", "machine learning", "ml", "agentic ai"),
),
SkillTaxonomyEntry(
    "cicd",
    ("ci/cd", "ci", "continuous integration", "continuous deployment"),
),
SkillTaxonomyEntry("observability", ("observability",)),
```

Casos de teste de regressão (com texto real do acervo, não fabricado):
`tests/backend/opportunities/test_domain.py::test_extracts_skills_added_by_f20_02_curation`
— cobre `ai` (via "machine learning" e via "artificial intelligence (AI)"), `cicd` e
`observability` (via o mesmo trecho real "observability, CI/CD, developer environments"),
e o alias `agentic ai`.

## Cobertura antes/depois (medição real, sem alterar `NORMALIZER_VERSION`)

Ver limitação abaixo sobre por que a medição não passou pelo pipeline de reprocessamento
oficial. Script ad-hoc: reexecuta `extract_skills(title, description, {})` sobre as 648
oportunidades reais do acervo, uma vez com as primeiras 27 entradas (`skills-v1` antes
deste card) e uma vez com as 30 entradas atuais.

```
total opportunities measured: 648
before (skills-v1, 27 entries): 314 with >=1 skill (48.46%)
after  (skills-v1 + F20-02, 30 entries): 588 with >=1 skill (90.74%)
delta: +274 opportunities gained at least one skill
new-term hits: {'ai': 544, 'cicd': 221, 'observability': 124}
```

Cobertura de "pelo menos uma skill extraída" salta de 48,46% para 90,74% das
oportunidades reais — um ganho grande e mensurável, majoritariamente puxado por `ai`
(presente em 544 das 648 descrições).

Meta do card F17-06 ("recall ≥ 90% num conjunto marcado de 30 vagas") não foi medida no
sentido estrito do card — não existe um conjunto de 30 vagas marcadas manualmente com a
lista completa de skills esperadas por vaga (isso exigiria leitura humana vaga a vaga, que
não coube nesta sessão). O número acima é uma proxy honesta (cobertura sobre o acervo
inteiro, não recall sobre um gabarito), documentada como tal.

## Reprocessamento oficial (2026-09-26, sessão de fechamento do gap)

A limitação acima ("`NORMALIZER_VERSION` não foi incrementado") foi resolvida: o gap foi
fechado numa sessão seguinte que teve autorização para tocar `service.py`/`domain.py` além
da lista original de arquivos do card (registrado aqui, não escondido).

- `SKILL_TAXONOMY_VERSION` subiu de `"skills-v1"` para `"skills-v2"`
  (`src/opportunity_radar/opportunities/domain.py:122`).
- `NORMALIZER_VERSION` subiu de `"v3"` para `"v4"`
  (`src/opportunity_radar/opportunities/service.py:49`), o gatilho que faz
  `pending_raw_item_ids` reenfileirar todo `RawItem` para `normalize_pending`.
- Todos os 13 literais de teste que comparavam contra `"skills-v1"` foram auditados; dois
  eram o próprio valor padrão do normalizador e foram corrigidos para `"skills-v2"`
  (`tests/backend/opportunities/test_domain.py`,
  `tests/backend/test_opportunities_integration.py`); dois helpers de fixture que
  representavam "a versão atual" passaram a importar `SKILL_TAXONOMY_VERSION` em vez de
  hardcodar (`tests/backend/matching/test_currency.py`,
  `tests/backend/dashboard/test_queries.py`) — o restante usa `"skills-v1"` como um valor
  arbitrário de teste para lógica de mistura de versões (`opportunity_taxonomy_version`,
  bump de taxonomia em `test_reevaluation.py`) e não precisava mudar.
- Novo teste de regressão:
  `tests/backend/opportunities/test_domain.py::test_skills_v2_never_removes_or_narrows_a_skills_v1_entry`
  — prova, por construção, que `skills-v2` é estritamente aditiva sobre as 27 entradas
  `skills-v1` (nenhum `canonical_id`/alias removido ou trocado), então o reprocessamento
  oficial só pode ganhar evidência, nunca perder.
- Reprocessamento rodado na máquina de referência (projeto compose `opportunity-radar`,
  containers `api`+`worker` reconstruídos com o código novo, sem `down -v`, banco e
  volumes intactos), disparado via
  `POST /opportunities/normalizations/pending?limit=500` até `processed=0`:

  ```
  antes  (normalizer_version=v3, taxonomy_version=skills-v1):
    opportunities: 648
    opportunities com >=1 skill: 314 (48.46%)
    opportunity_skill rows: 955, todas skills-v1

  depois (normalizer_version=v4, taxonomy_version=skills-v2):
    opportunities: 648  (nenhuma perdida/duplicada)
    opportunities com >=1 skill: 588 (90.74%)
    opportunity_skill rows: 1844, todas skills-v2 (nenhuma linha skills-v1 órfã sobrou —
      _reconcile_enrichment substitui a evidência por ocorrência corretamente)
    normalization_result: 670 v3 + 670 v4 (todo o acervo de RawItem reprocessado)
    falhas (status=FAILED, INVALID_COLLECTED_ITEM_V1): 22 sob v3 e 22 sob v4 — o mesmo
      conjunto de raw_item_id, zero falha nova introduzida pelo bump
  ```

  90,74% bate exatamente com a medição ad-hoc anterior (fora do pipeline), agora
  confirmada pelo pipeline oficial de reprocessamento sobre o banco real. Nenhuma
  oportunidade regrediu: a tabela `opportunity_skill` não guarda mais nenhuma linha
  `skills-v1`, e a contagem de oportunidades com skill subiu (314 → 588), nunca desceu,
  como a taxonomia aditiva garante.

- Rescore de matching: o bump de `NORMALIZER_VERSION`/`SKILL_TAXONOMY_VERSION` muda o
  `input_hash` das avaliações afetadas, então a fila de reavaliação (`F16-04`) absorve a
  onda como comportamento esperado (nota de implementação do F17-06) — não é uma
  regressão, é a reanálise que o próprio card documenta como certa.

## Limitações remanescentes

- **Termo `ci` é um alias curto (2 caracteres) sem desambiguação por contexto**, ao
  contrário de `go`/`react` que já têm uma função de contexto dedicada
  (`_is_unambiguous_skill_use`). Risco residual: `ci` pode gerar falso positivo em vagas
  que citam "CI" como sigla de outra coisa (raro, mas não impossível). Não corrigido nesta
  sessão — mudar a lógica de extração é maior que o escopo do fechamento do gap.
- A meta "recall ≥ 90% num conjunto marcado de 30 vagas" do F17-06 continua medida como
  proxy (cobertura sobre o acervo inteiro, 90,74%), não como recall sobre um gabarito
  humano de 30 vagas — esse gabarito não existe e não foi criado nesta sessão.
