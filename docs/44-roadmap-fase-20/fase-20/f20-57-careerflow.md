# CARD F20-57 — Careerflow como fonte de vagas

- **Status:** Fechado — não viável. Revisão em
  [`docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md`](../../pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md)
  (2026-09-28): os Termos de Uso da Careerflow (`careerflow.ai/terms`) proíbem nomeadamente
  "systematically retrieve data... to compile... a collection, compilation, database",
  "data mining, robots" e "spider, robot, scraper, ou offline reader", além de uso "para
  competir". A própria página `/jobs` é, adicionalmente, um agregador de +50 boards
  (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice) que redireciona para a fonte original ao
  candidatar-se — não é fonte primária mesmo se os Termos permitissem. Nenhum código foi
  escrito.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); pedido do usuário em
  2026-09-28 ("automatizar coleta de careerflow.ai/jobs"), tratado com a mesma régua do
  F20-32/F20-51/F20-52.

## Contexto

`careerflow.ai/jobs` ("Job Board – AI-Matched Jobs for Career Builders") foi avaliada como
fonte direta de vaga. O pedido do usuário já apontava a hipótese de a Careerflow ser ela
mesma um agregador — confirmada nesta pesquisa.

## Escopo

1. **Revisão de termos** registrada em `docs/pesquisas/` antes de qualquer código, cobrindo
   `robots.txt`, Termos de Uso, se a página é fonte primária ou agregador de terceiros, API
   pública, autenticação e anti-bot. Termo com proibição nomeada de scraping/agregação, ou
   confirmação de que a página é ela mesma um agregador de fontes que o radar já prioriza
   diretamente, encerram o card.
2. Se viável: coletor com a interface dos atuais.
3. Se viável: board falso em `tests/e2e/`, integração com `PROBE_TYPES`/`IDENTIFIER_KEYS`/
   `SUPPORTED_ATS`/formulário de criação de fonte.

## Fora de escopo

- Qualquer fonte que exija login ou proíba automação.
- Coletar um agregador de terceiros em vez da fonte original da vaga.
- Raspagem de HTML/DOM quando não existe endpoint estruturado.

## Resultado da revisão

**Não viável.** Ver a pesquisa citada para o texto completo. Resumo:

- `robots.txt` permissivo (só bloqueia parâmetros de tracking/paginação) — não decide por si.
- Termos de Uso, quatro cláusulas nomeadas: "systematically retrieve data... to compile...
  collection/database", "data mining, robots... data gathering and extraction tools",
  "spider, robot, cheat utility, scraper, or offline reader" e "compete... revenue-generating
  endeavor". Mesmo padrão decisivo do F20-32/F20-51/F20-52.
- Achado extra: a Careerflow agrega +50 job boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter,
  Dice) e redireciona para a página original ao candidatar-se — mesmo sem os Termos, coletar
  aqui seria coletar um agregador de terceiros, contra a prática já adotada na Fase 20 de
  priorizar a fonte original de cada empresa/ATS.
- HTML inicial (57.999 bytes, Webflow) sem `JobPosting` em `schema.org` — a listagem real
  também é montada por JavaScript.

## Critérios de aceite

- [x] Termos revisados e registrados antes do código —
      `docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md`, decisão: não
      viável. Os critérios seguintes não se aplicam.
- [ ] Coletor com teste. — N/A (não viável)
- [ ] Sonda, proposta, cadastro e formulário reconhecem a fonte nova. — N/A (não viável)
- [ ] Pelo menos uma vaga real coletada via Careerflow. — N/A (não viável)

## Verificação

- **CI:** nenhuma — nenhum código foi escrito.
- **Máquina de referência:** nenhuma chamada de coleta foi feita; as únicas requisições desta
  revisão foram `robots.txt`, `GET /jobs` (para checar `JobPosting`) e a página pública de
  Termos, listadas na pesquisa citada.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar (compartilhado com F20-56/58/59) | `docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md` | Revisão de termos, robots.txt, API e anti-bot dos quatro sites, feita em conjunto. Entregável final deste card: decisão "não viável" para Careerflow. |

## Não fazer

- Não implementar coletor, sonda ou integração de descoberta para Careerflow.
- Não coletar um agregador de terceiros como se fosse fonte original.
- Não raspar o DOM renderizado por JavaScript de `careerflow.ai`.

## Pronto quando

A revisão está registrada com decisão e evidência, e o card está marcado como fechado — não
viável, sem código pendente.
