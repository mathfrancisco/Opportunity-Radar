# Pesquisa — Descoberta de startups sem tocar Wellfound/YC/WaaS

**Data:** 2026-09-28
**Cards relacionados:** F20-51 (Wellfound), F20-52 (Work at a Startup) — fechados não
viável em [`docs/pesquisas/wellfound-yc-jobs.md`](wellfound-yc-jobs.md). Este documento
avalia a alternativa ("opção 1") pedida pelo usuário: descobrir startups **sem** acessar
`wellfound.com`, `ycombinator.com` nem `workatastartup.com`.
**Pergunta:** dá para achar mais vagas de startups (idealmente YC, seed/Series A,
remoto/LATAM/Brasil) usando só fontes que o radar já tem contrato para tocar — os
domínios de ATS que o radar já coleta e/ou APIs públicas de terceiros com termos
permissivos — em vez de Wellfound/YC?
**Padrão aplicado:** mesma régua do F20-32/F20-51/F20-52 — revisão de termos por fonte
antes de qualquer código; só endpoint/site que não proíbe automação e tem contrato
estável entra em card de implementação.

## Resumo do veredito

| Fonte | Mecanismo | ToS | Veredito |
| --- | --- | --- | --- |
| Domínios de ATS já coletados (Ashby, Greenhouse, Lever, Workable, Teamtailor), descobertos via busca Tavily e validados por `probe_direct_ats` | Busca de texto livre restrita por `site:`/`include_domains` nos próprios domínios de ATS; nenhuma chamada a Wellfound/YC; validação final é a mesma sonda direta que F20-27/F20-36 já fazem contra a API pública do ATS | Termos da Tavily (uso comercial da API, já aceito pelo F20-42/43); termos de cada ATS já cobertos pelos cards existentes (Ashby, Greenhouse, Lever, Workable, Teamtailor — todos "Done"/"Implementado" com revisão prévia) | **Viável** — não é fonte nova, é um jeito novo de alimentar `limited_discovery`/`probe_direct_ats` com candidatos a empresa |
| Hacker News "Who is hiring?" via API oficial (`hacker-news.firebaseio.com`, mantida pela própria YC) | API JSON pública, sem chave, sem limite de taxa documentado, mantida no repositório oficial `github.com/HackerNews/API` | Sem cláusula de proibição de automação encontrada; é a API oficial que a HN disponibiliza precisamente para acesso programático — categoricamente diferente de raspar `news.ycombinator.com/item` via HTML ou de tocar `wellfound.com`/`workatastartup.com` | **Viável** — API própria, não scraping |
| Algolia HN Search API (`hn.algolia.com/api/v1`) | API JSON pública de terceiro (Algolia), espelha o mesmo conteúdo da Firebase API, usada para localizar o thread mensal "Who is hiring?" sem varrer IDs manualmente | Documentada publicamente pela Algolia como serviço gratuito para a comunidade HN; mesmo conteúdo da API oficial | **Viável** — mesmo dado, caminho de busca mais barato |
| Listas GitHub "awesome" de startups YC/seed (ex.: `github.com/*/awesome-yc-companies`, listas de batch) | Ler README/JSON de um repositório público no GitHub | Cada lista tem sua própria licença (normalmente MIT/CC0 nos READMEs "awesome-*"); GitHub permite acesso de conteúdo público via API oficial (`api.github.com`, rate limit documentado) | **Viável em princípio, mas descartado nesta rodada** — listas "awesome" são compiladas manualmente por terceiros, ficam desatualizadas rápido e não têm garantia de fonte primária; qualidade do dado é pior que buscar direto nos ATS. Não abrir card agora; registrar como opção de baixo custo se a fonte 1 não escalar. |
| Listas de funding público com licença aberta (ex.: Crunchbase Open Data Map, dados de imprensa) | Dataset ou API de terceiro | Crunchbase: API paga, termos restringem redistribuição — não é "licença aberta" de fato, apesar do nome "Open Data Map" ser sobre um mapa de visualização, não um dump livre | **Não viável nesta rodada** — não há dataset de funding realmente aberto e atualizado encontrado sem custo/contrato adicional; fora de escopo do pedido do usuário (fontes de vaga, não base de investimento) |

## Opção 1 — Busca Tavily nos domínios de ATS + `probe_direct_ats`

### Mecanismo

1. Tavily `/search` com `site:<domínio-de-ATS>` (ou `include_domains`) combinando um
   domínio de ATS já suportado (`jobs.ashbyhq.com`, `boards.greenhouse.io` /
   `job-boards.greenhouse.io`, `jobs.lever.co`, `apply.workable.com`, `*.teamtailor.com`)
   com um termo de sinal de startup (`"Y Combinator"`, `"YC W24"`, `"seed stage"`,
   `"Series A"`, `remote LATAM`/`remote Brazil`).
2. A busca já devolve a **URL do board de ATS da empresa** (ex.:
   `jobs.ashbyhq.com/retell-ai/...`) — não a URL de Wellfound/YC. Nenhuma requisição vai
   para `wellfound.com`, `ycombinator.com` ou `workatastartup.com` neste fluxo.
3. Extrair o slug da empresa a partir da própria URL do ATS (já é o padrão de
   `detect_ats_board()` do F20-44) — não precisa de `probe_direct_ats` para achar o board,
   porque a busca já aponta o board diretamente. `probe_direct_ats` (ou o
   `known_ats_boards`/dedupe do F20-44) só entra para confirmar que o board tem vaga
   ativa e para não duplicar `CompanySource` já habilitada.
4. Resultado novo (empresa/board ainda não em `company_radar.company`) se torna proposta
   de fonte pela fila de homologação existente (F20-25/F20-46), com evidência da busca
   Tavily anexada — mesmo padrão que F20-46 já define para achados via Tavily.

Este mecanismo **não é uma fonte nova**: é uma consulta adicional de descoberta que
alimenta o mesmo pipeline proposta → homologação → coleta que Ashby/Greenhouse/
Lever/Workable/Teamtailor já usam. Não há coletor novo, não há ATS novo em
`SUPPORTED_ATS`.

### Piloto (evidência)

4 chamadas `tvly search --max-results 10` (profundidade `basic`, 1 crédito cada —
confirmado pelos preços documentados na SPEC 41 §3.1; CLI não expõe contador de créditos
consumidos, então o total é estimado por número de chamadas), mais 1 chamada de apoio
para verificar a API oficial da HN (não conta para este piloto de ATS). **5 créditos
Tavily gastos no total, dentro do teto de ~15 pedido.**

| # | Query | Domínio filtrado | Resultados | Empresas distintas | Sinal de startup explícito (YC/seed/Series A na amostra) | Já no catálogo (`company_radar.company`, 223 linhas) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `site:jobs.ashbyhq.com "Y Combinator" remote` | Ashby | 10 | 7 (clipboard, aleph, legionhealth, centralize, fieldguide, retell-ai, vetcove) | 4/7 citam YC explicitamente no trecho | 1/7 (Retell AI) |
| 2 | `site:jobs.lever.co "YC" startup remote` | Lever | 10 | 4 (Instrumentl, Weekday, Emi Labs, EasyPost) | 3/4 (Instrumentl, Weekday, Emi Labs); EasyPost é falso positivo (não é YC) | 0/4 |
| 3 | `site:job-boards.greenhouse.io "seed stage" OR "Series A" remote LATAM` | Greenhouse | 10 | 4 (Aktos, Lumimeds, Dropbox, Able) | 1/4 (Aktos, "seed-stage" explícito); Dropbox é falso positivo grosseiro (empresa grande, não startup) | 0/4 |
| 4 | `site:apply.workable.com "Y Combinator" OR "YC" remote` | Workable | 10 | 6 (talentpluto, anavah-talent, weekday-1\*, growthbook, writesonic, intellecthq) | 4/6 citam YC explicitamente (talentpluto, weekday, growthbook, intellecthq); anavah-talent é agência de recrutamento citando clientes YC, não é ela própria YC (falso positivo) | 0/6 (\*Weekday duplica a empresa da query 2, contada uma vez no total) |

\* Weekday aparece em Lever e Workable ao mesmo tempo — startups às vezes têm mais de um
board de ATS ativo (migração ou teste); dedupe por empresa (não por board) é necessário
na implementação, não só dedupe por URL.

**Totais do piloto:** 40 resultados brutos, ~20 empresas distintas depois de dedupe por
nome/slug (7+4+4+6, descontando 1 duplicata cross-ATS). Comparando por `normalized_name`
contra as 223 empresas do catálogo em `f20manual` (consulta somente leitura, sem
alteração): **1 de ~19 nomes testados já estava no catálogo (Retell AI, achada via
Ashby)** — **~95% dos candidatos são novos**. Sinal de startup explícito (menção a
"Y Combinator"/YC/seed/Series A no próprio trecho) apareceu em **12/21** resultados úteis
(57%) quando a query já inclui um termo de startup (queries 1, 2, 4); cai para **1/4**
(25%) quando a query só usa `"seed stage" OR "Series A"` sem termo de marca (query 3), e
essa mesma query trouxe o único falso positivo grosseiro (Dropbox, claramente não é
startup).

### Qualidade e riscos

- **Rendimento bruto é bom** (a maioria dos resultados é empresa nova), mas **precisão
  do sinal "é startup/YC" é imperfeita**: falsos positivos vêm de (a) agências de
  recrutamento citando clientes YC (`anavah-talent`) e (b) empresa grande capturada por
  termo genérico demais (`Dropbox` em "Series A"/"seed" sem contexto — a query pegou uma
  vaga de Dropbox mencionando "early-stage" em outro trecho da página, não a empresa em
  si). **Recomendação:** exigir o sinal de marca (`"Y Combinator"`, `"YC "+ano/letra de
  batch`) para marcar `is_startup`/evidência de batch; usar `"seed stage"`/`"Series A"`
  sem marca só como sinal fraco (rendimento mais alto, precisão mais baixa), nunca como
  prova isolada — mesmo princípio de "marca ausente é desconhecida" do §4 da SPEC 39.
- **Sem viés de amostra maior**: 4 queries e 40 resultados não bastam para uma taxa de
  precisão estatisticamente confiável — é piloto de viabilidade, não medição de produção.
  A implementação real precisa da métrica de rendimento útil (SPEC 39 §4) antes de
  decidir orçamento de créditos recorrente para esta descoberta.
- **Duplicidade cross-board** (Weekday em Lever e Workable) confirma que dedupe de
  proposta precisa ser por empresa/domínio canônico, não só por URL de board — já é a
  regra do F20-36 (mesma URL canônica não ocupa a fila de novo), mas a implementação
  precisa achar a mesma empresa em boards diferentes, o que exige matching por nome
  normalizado além de URL.
- **Custo de créditos por ciclo:** se a descoberta rodar semanalmente com N queries
  (termos de startup × domínio de ATS), o orçamento entra no mesmo `TavilyBudgetGuard`
  do F20-43 — não é budget novo, é mais uma fila de query concorrendo pelo teto mensal
  já existente. Com 5 domínios de ATS × ~3 termos de startup = 15 queries/ciclo a 1
  crédito cada (profundidade `basic`), isso é ~15 créditos por ciclo de descoberta — a
  confirmar contra o teto real configurado antes de fixar a cadência.
- **Nenhuma chamada de coleta foi feita contra board real** além das 4 buscas Tavily
  (que retornam snippet, não fazem GET no board) e da consulta somente leitura ao
  Postgres do ambiente `f20manual` para contar/comparar nomes. Nenhum `probe_direct_ats`
  real foi executado neste piloto — ele já é código existente e testado (F20-27/F20-36),
  não precisa de nova prova de viabilidade.

## Opção 2 — Hacker News "Who is hiring?" via API oficial

### ToS e mecanismo

- API: `https://hacker-news.firebaseio.com/v0/...` — documentada em
  `github.com/HackerNews/API`, mantida pela própria Y Combinator/HN "em parceria com o
  Firebase". Texto do próprio README: "There is currently no rate limit" (na época da
  publicação; ainda assim, o radar deve aplicar seu próprio limite conservador, política
  de boa vizinhança já usada com Remotive/ATS). Sem chave, sem autenticação, sem cláusula
  de proibição de scraping — é, ao contrário de Wellfound/YC/WaaS, **a própria API que a
  HN disponibiliza para acesso programático de terceiros**, não um endpoint interno
  descoberto por engenharia reversa.
- Complementar: `https://hn.algolia.com/api/v1/search` (mantida pela Algolia,
  documentada publicamente como serviço da comunidade HN) permite achar o item do
  thread mensal "Ask HN: Who is hiring? (Mês/Ano)" por texto, sem precisar varrer IDs
  manualmente pela Firebase API.
- Fluxo: localizar o item do mês via Algolia → buscar filhos (comentários de nível 1) via
  Firebase API → cada comentário é um texto livre de vaga (formato não estruturado,
  varia por autor) → extrair empresa, é-remoto, stack como sinal, não como
  `JobPosting` estruturado.
- **Diferença central em relação a Wellfound/YC/WaaS:** aqui não há Termos de Uso
  proibindo mineração de dados sobre este conteúdo — a própria HN publica e mantém a
  API para esse fim. `news.ycombinator.com/legal` (Termos gerais da YC, os mesmos citados
  em `wellfound-yc-jobs.md`) cobre o **site** `news.ycombinator.com`; a Firebase API é
  outro produto, com seu próprio README dizendo explicitamente que existe para uso
  programático. Ainda assim, antes de abrir o card de implementação (F20-55, abaixo), a
  revisão de termos completa (robots.txt de `news.ycombinator.com`, texto integral de
  `ycombinator.com/legal` aplicado à API, não só ao site) deve ser refeita — este
  documento já aponta o caminho, não substitui a revisão formal do card.

### Qualidade esperada (não medida neste piloto — nenhuma chamada HN foi feita além de
1 busca Tavily para confirmar a existência/termos da API; ver tabela de créditos acima)

- Sinal de "é startup" mais forte que busca Tavily em ATS: o próprio formato do thread
  "Who is hiring?" já filtra para empresas contratando abertamente em público, boa
  fração é startup em estágio inicial.
- Extração é mais trabalhosa: comentário de texto livre, não JobPosting estruturado —
  precisa de heurística de parsing (linha 1 = empresa, palavras-chave de local/remoto),
  parecido com o que F18-03/F20-37 já fazem para JobPosting não estruturado, mas sem
  schema.org aqui.
- Frequência baixa (thread mensal), então o custo de rede é irrelevante comparado ao
  budget Tavily.

## Opções descartadas nesta rodada

- **Listas GitHub "awesome-*"**: viáveis por licença, mas qualidade de dado inferior
  (curadoria manual esparsa, desatualiza rápido) comparada à busca direta nos ATS.
  Registrado como opção de reserva, sem card agora.
- **Crunchbase/dados de funding**: sem dataset aberto e atualizado sem custo/contrato
  adicional; fora do pedido original (fonte de vaga, não base de investimento).

## Recomendação

1. Abrir card de descoberta de startups via busca Tavily nos domínios de ATS já
   suportados + integração com a fila de homologação (F20-53 abaixo) — reaproveita
   100% do pipeline existente (Tavily do F20-42/43/44/46, `probe_direct_ats`/
   `limited_discovery` do F20-27/F20-36, fila de homologação do F20-25), sem coletor
   novo, sem ATS novo.
2. Abrir card de marcação "startup" no `company_radar.company` (estágio, evidência de
   batch YC) e filtro correspondente na UI (F20-54) — depende do F20-53 produzir a
   evidência de origem que alimenta a marcação.
3. Abrir card de coletor "Who is hiring?" da HN via API oficial (F20-55), condicionado
   a revisão de termos formal (mesmo padrão do F20-32/F20-51/F20-52) antes de qualquer
   código de coleta — este documento não substitui essa revisão, só aponta que, ao
   contrário de Wellfound/YC/WaaS, aqui existe uma API oficial documentada sem cláusula
   de proibição encontrada.
4. Não abrir card para listas GitHub "awesome-*" nem para dados de funding agora;
   revisitar só se F20-53 não sustentar rendimento útil suficiente.

## Referências

- Piloto Tavily: 4 chamadas `tvly search` (queries acima) + 1 chamada de verificação da
  API oficial da HN, todas em 2026-09-28, ~5 créditos totais.
- `docs/44-roadmap-fase-20/fase-20/f20-42-tavily-cliente-e-configuracao.md`,
  `f20-43-tavily-orcamento-de-creditos.md`, `f20-44-tavily-collector-de-descoberta-web.md`,
  `f20-46-tavily-evidencia-para-propostas.md` — pipeline Tavily reaproveitado.
- `src/opportunity_radar/acquisition/limited_discovery.py` (`probe_direct_ats`,
  `direct_slug_candidates`) — sonda direta reaproveitada, nenhuma alteração testada
  neste piloto.
- `https://github.com/HackerNews/API` — README oficial confirmando ausência de limite de
  taxa documentado e propósito programático da API.
- `https://hn.algolia.com/api/v1/search` — documentação pública da API Algolia da HN.
- Consulta somente leitura ao Postgres do ambiente `f20manual`
  (`SELECT count(*) FROM company_radar.company` → 223; `SELECT normalized_name, domain
  FROM company_radar.company WHERE normalized_name ILIKE ANY(...)` contra os nomes do
  piloto → só "Retell AI" bateu de fato, "Airtable" foi correspondência falsa do padrão
  `%able%`). Nenhuma escrita foi feita neste banco; projeto Docker `opportunity-radar`
  não foi tocado.
