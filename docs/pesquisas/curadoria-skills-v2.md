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

## Limitações

- **`NORMALIZER_VERSION` não foi incrementado.** O card F20-02 pede "rodar o
  reprocessamento retomável do F17-06" pelo pipeline oficial (`normalize_pending` por
  versão, em `src/opportunity_radar/opportunities/service.py`). Isso exigiria editar
  `service.py`, fora da lista de arquivos deste card, e dispara uma onda de reanálise de
  matching (rescore de todas as 648 oportunidades) — o card F20-02 explicitamente proíbe
  alterar elegibilidade, score ou veredito. Por isso a medição de cobertura acima foi feita
  chamando `extract_skills` diretamente sobre o texto já armazenado, sem passar pelo
  pipeline de normalização/reprocessamento nem tocar no banco. O ganho de cobertura é real
  e reproduzível, mas os registros de `opportunity_skill` no banco **não foram
  atualizados** — isso só acontece quando alguém rodar o reprocessamento oficial
  (bump de `NORMALIZER_VERSION`, fora de escopo aqui).
- **Termo `ci` é um alias curto (2 caracteres) sem desambiguação por contexto**, ao
  contrário de `go`/`react` que já têm uma função de contexto dedicada
  (`_is_unambiguous_skill_use`). Adicionar essa mesma desambiguação ficou fora do escopo
  de arquivos permitido (`domain.py` só na tupla `SKILL_TAXONOMY`, não na lógica de
  extração). Risco residual: `ci` pode gerar falso positivo em vagas que citam "CI" como
  sigla de outra coisa (raro, mas não impossível).
- **Versão da taxonomia não subiu para `skills-v2`.** `SKILL_TAXONOMY_VERSION = "skills-v1"`
  está hardcoded como literal (`"skills-v1"`) em 13 arquivos de teste fora da lista de
  arquivos deste card (`tests/backend/dashboard/`, `tests/backend/matching/`, etc.) —
  bump do nome de versão exigiria tocar todos eles. Optei por manter o nome de versão e só
  adicionar entradas à mesma tupla, que é aditivo e não quebra nada existente. Registrado
  aqui como decisão deliberada, não omissão.
