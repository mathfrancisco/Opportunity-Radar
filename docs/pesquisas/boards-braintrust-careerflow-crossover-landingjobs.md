# Pesquisa — Braintrust, Careerflow, Crossover e Landing.jobs como fonte de vagas

**Data:** 2026-09-28
**Cards relacionados:** [F20-56 — Braintrust](../44-roadmap-fase-20/fase-20/f20-56-braintrust.md),
[F20-57 — Careerflow](../44-roadmap-fase-20/fase-20/f20-57-careerflow.md),
[F20-58 — Crossover](../44-roadmap-fase-20/fase-20/f20-58-crossover.md),
[F20-59 — Landing.jobs](../44-roadmap-fase-20/fase-20/f20-59-landing-jobs.md)
**Pergunta:** dá para automatizar a coleta de vagas de `app.usebraintrust.com/jobs/`,
`careerflow.ai/jobs`, `crossover.com/jobs` e `landing.jobs/jobs`?
**Padrão aplicado:** o mesmo do F20-32 (Gupy) e do F20-51/F20-52 (Wellfound/YC) — `robots.txt`
não decide nada por si; Termos de Uso com proibição **nomeada** de scraping/agregação/mineração
de dados encerra o card; verificar também API pública/feed oficial, autenticação, anti-bot, e se
a vaga já vive num ATS que o radar coleta (`ashby`, `greenhouse`, `lever`, `workable`,
`teamtailor`, `workday`, `factorial`, além do coletor genérico `jobposting` para schema.org
`JobPosting`). Nenhuma raspagem de lista de vaga foi feita; só `robots.txt`, páginas de Termos
públicas, a página `/jobs`/`/terms` de cada site (para checar schema.org e o endpoint da API
documentada) e busca na web para contexto de terceiros.

## Resumo do veredito

| Site | robots.txt | Termos de Uso | API pública | Vaga já em ATS coletado? | Veredito |
| --- | --- | --- | --- | --- | --- |
| Braintrust (`app.usebraintrust.com/jobs/`) | permissivo (só bloqueia parâmetro de tracking) | Seção "Prohibited Uses" (Talent Node) só proíbe ferramenta "não autorizada" e engenharia reversa — **sem** cláusula nomeada de scraping/mineração/agregação | Nenhuma documentada; página é SPA React sem `JobPosting` no HTML inicial | Não — marketplace próprio (bidding/aplicação na própria Braintrust), não usa Ashby/Greenhouse/Lever/etc. | **Não viável** — sem endpoint estruturado; exigiria raspar DOM renderizado por JS, fora do padrão dos coletores atuais |
| Careerflow (`careerflow.ai/jobs`) | permissivo (só bloqueia parâmetros de tracking/paginação) | Termos (`careerflow.ai/terms`) proíbem nomeadamente "systematically retrieve data... to compile... a collection, compilation, database", "data mining, robots, ou ferramentas similares de coleta e extração", "spider, robot, scraper, ou leitor offline" e uso "para competir" | Nenhuma; o próprio "Job Board" da Careerflow é um agregador de +50 boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice) que redireciona para a fonte original ao aplicar | N/A — a página é ela mesma um agregador, não uma fonte primária | **Não viável** — cláusula nomeada decide, e a página é um agregador de agregadores (preferir sempre a fonte original que ela já lincka) |
| Crossover (`crossover.com/jobs`) | permissivo (só bloqueia `apply$`/`/next-step`) | Não verificável por fetch simples — `/jobs`, `/terms-and-conditions` e `/website-terms` retornam o mesmo shell React vazio (19.434 bytes, sem HTML server-renderizado) mesmo sem JS; nenhum texto de termos foi obtido sem executar JavaScript | Nenhuma documentada; sem `JobPosting` no HTML inicial (só `Organization`/`WebSite`) | Não — Crossover roda seu próprio pipeline de contratação (testes, entrevista, "Crossover for Work"), não delega a Ashby/Greenhouse/Lever/etc. | **Não viável** — sem endpoint estruturado nem texto de termos acessível sem JS; mesma regra "não raspar DOM sem endpoint" decide, independente do texto de Termos (não confirmado) |
| Landing.jobs (`landing.jobs/jobs`) | bloqueia `/api/`, `/jobs/search`, `/employers/*`; não bloqueia `/jobs` isoladamente | Termos (`landing.jobs/tos`, atualizados 2026-04-17), Seção 8 "Prohibited Uses", proíbem nomeadamente "usar scrapers ou bots", "monitorar ou copiar materiais", "copiar, usar, exibir ou distribuir qualquer informação obtida da Plataforma" e "monetizar a Plataforma sem permissão" — a Plataforma é definida como "nosso site (landing.jobs)", sem exceção para a API | **Existe e está ativa hoje** — `GET https://landing.jobs/api/v1/jobs` e `/api/v1/companies` responderam `200` com dados reais de vaga sem autenticação (verificado nesta pesquisa); documentada em `github.com/LandingJobs/LandingJobs-api` (sem licença, sem termo de uso próprio no README) | Não — Landing.jobs é board próprio; integra com Greenhouse/Workable só para *exportar* candidatura do lado da empresa, não para hospedar a vaga lá | **Não viável apesar da API tecnicamente aberta** — os Termos vigentes cobrem "a Plataforma" (o site, onde a API também vive) e proíbem nomeadamente scraping e redistribuição de conteúdo, sem cláusula própria de API/parceria que abra excepção; mesmo padrão do F20-51 (GraphQL da Wellfound é tecnicamente alcançável, mas o Termo decide) |

Nenhuma chamada de coleta de vaga foi feita nos quatro sites. As únicas requisições desta
pesquisa foram: `robots.txt` dos quatro domínios, a página `/jobs` de cada site (para checar
`schema.org`/`JobPosting` no HTML inicial), a página de Termos pública de cada site, e duas
chamadas de verificação ao endpoint documentado `landing.jobs/api/v1/{jobs,companies}` (GET
simples, sem autenticação, sem paginação exaustiva) — para confirmar se a API pública que o
usuário lembrava ainda está ativa, exatamente o que este card pedia para verificar.

## Braintrust (`app.usebraintrust.com/jobs/`)

### robots.txt (verificado — `https://app.usebraintrust.com/robots.txt`)

Só bloqueia parâmetros de tracking (`utm_*`, `page`, `back`, `key`, `vgo_ee`) e referencia
`sitemap.xml`. Não bloqueia `/jobs/` nem páginas de vaga.

### Termos de Uso (`https://www.usebraintrust.com/terms`, entidade "Talent Node")

Seção "Prohibited Uses of the Site" lista proibições — nenhuma nomeia scraping, data mining,
harvesting ou agregação:

> "Attempt to access or search the Site Services using any unauthorized engine, software,
> tool, or mechanism."

> "Attempt to decipher, decompile, disassemble or reverse engineer any software used to
> provide the Site Services."

Busca no documento inteiro por "scrape", "scraping", "harvest", "aggregat", "data mining" e
"compet(e/itive)" não encontrou nenhuma ocorrência. Isso é o mesmo padrão de cláusula
**genérica** de Workday/Teamtailor/Workable/Factorial (que a Fase 20 já leu como não bloqueando
coleta de baixa frequência sem login) — diferente da cláusula **nomeada** que fechou Gupy,
Wellfound e YC. Por Termos de Uso isolados, Braintrust não estaria bloqueado.

### API pública, autenticação, anti-bot

- Não existe API JSON pública documentada para vagas (só um dashboard de estatísticas de rede
  citado por terceiros, sem relação com listagem de vaga).
- `GET /jobs/` devolve `200`, cookie de sessão Django (`sessionid`, `HttpOnly`), sem CAPTCHA nem
  bloqueio tipo DataDome nesta requisição simples.
- O HTML inicial (72.042 bytes) não contém nenhum `<script type="application/ld+json">` com
  `JobPosting` — é uma SPA React (`app.js`/`vendors.js` servidos via CloudFront) que busca a
  lista de vaga via chamada JS não descoberta nos assets estáticos.

### Decisão

**Não viável.** Não há cláusula nomeada de Termos que bloqueie — mas também não há nenhum
endpoint estruturado (API documentada, feed, ou `JobPosting` embutido) para coletar sem
executar JavaScript e raspar o DOM renderizado. Os coletores da Fase 20 (`httpx`-based, sem
navegador headless) não têm essa capacidade, e a regra "não fazer: raspagem de HTML/DOM quando
não existe endpoint estruturado" (repetida em todos os cards de F20-28 a F20-37) já decide sem
precisar de bloqueio contratual. Braintrust é uma marketplace própria (aplicação/bidding na
própria plataforma) — não há vaga já hospedada num ATS que o radar coleta.

## Careerflow (`careerflow.ai/jobs`)

### robots.txt (verificado — `https://www.careerflow.ai/robots.txt`)

`Allow: /`, bloqueia só parâmetros de paginação/tracking (`_page=`, `ref=`, `via=`, `utm_`,
`trk=`). Não bloqueia `/jobs`.

### Termos de Uso (decisivo) — `https://www.careerflow.ai/terms`

> "Systematically retrieve data or other content from the Site to create or compile, directly
> or indirectly, a collection, compilation, database, or directory"

> "Engage in any automated use of the system, such as using scripts to send comments or
> messages, or using any data mining, robots, or similar data gathering and extraction tools."

> "Except as may be the result of standard search engine or Internet browser usage, use,
> launch, develop, or distribute any automated system, including without limitation, any
> spider, robot, cheat utility, scraper, or offline reader"

> "Use the Site as part of any effort to compete with us or otherwise use the Site and/or the
> Content for any revenue-generating endeavor or commercial enterprise."

Quatro cláusulas nomeadas — "data mining", "robots", "scraper", "systematically retrieve data...
to compile a collection/database" — cobrem exatamente a operação de um coletor. Mesmo padrão
decisivo do F20-32/F20-51/F20-52.

### Careerflow como agregador (achado extra, além do decisivo)

O título da própria página é *"Job Board – AI-Matched Jobs for Career Builders"*, e o texto
menciona "Browse jobs"/"Job Board"/"LinkedIn". Confirmado por fonte pública (help
center/review de terceiros): a Careerflow **agrega +50 job boards** (LinkedIn, Indeed,
Glassdoor, ZipRecruiter, Dice, entre outros) e, ao candidatar-se, redireciona para a página
original. Isso confirma a hipótese do pedido: mesmo que os Termos não decidissem, coletar
`careerflow.ai/jobs` seria coletar um agregador de agregadores — a regra prática já usada na
Fase 20 (preferir a fonte original de cada empresa/ATS) se aplicaria de qualquer forma. O HTML
inicial (57.999 bytes, Webflow) não contém `JobPosting`, só `Organization` — a listagem real
também é montada por JS, reforçando que não há endpoint estruturado nem aqui.

### Decisão

**Não viável.** Termos nomeiam scraping/data mining/agregação e proíbem uso competitivo — o
mesmo padrão decisivo dos cards já fechados. Ainda que os Termos permitissem, a página é ela
mesma um agregador de terceiros (LinkedIn, Indeed etc.), o que contraria a prática já adotada
na Fase 20 de priorizar a fonte original da vaga.

## Crossover (`crossover.com/jobs`)

### robots.txt (verificado — `https://www.crossover.com/robots.txt`)

```
User-agent: facebookexternalhit
Disallow: *gad_source=*

User-agent: *
Disallow: */apply$
Disallow: */next-step
Noindex: */apply$
Noindex: */next-step

Sitemap: https://www.crossover.com/sitemap.xml
```

Não bloqueia `/jobs`.

### Termos de Uso — não verificável por fetch simples

`https://www.crossover.com/terms-and-conditions`, `https://www.crossover.com/website-terms` e
a própria `https://www.crossover.com/jobs` devolvem exatamente o mesmo corpo de 19.434 bytes
(`Server: AmazonS3` via CloudFront) — um shell React vazio, com só `Organization`/`WebSite` em
`schema.org` (sem `JobPosting`) e nenhum texto de Termos ou vaga no HTML. É uma SPA que renderiza
tudo por JavaScript no navegador; sem executar JS não há como ler nem os Termos nem a lista de
vaga. Diferente dos outros três sites desta pesquisa (e de `wellfound.com/terms`,
`ycombinator.com/legal`, `careerflow.ai/terms`, `landing.jobs/tos`, todos lidos por fetch
simples), aqui **não foi possível obter texto citável de Termos** sem contornar essa barreira —
o que esta pesquisa não faz (mesma régua de "poucas requisições educadas, sem navegador
headless" aplicada às outras).

### API pública, autenticação, anti-bot

Nenhuma API pública documentada encontrada. Nenhum bloqueio tipo CAPTCHA/DataDome identificado
na requisição simples (retorna `200` normalmente) — mas isso é irrelevante porque a resposta não
contém conteúdo, só o shell da SPA.

### Decisão

**Não viável.** Independente do texto de Termos (não confirmado, para nenhum lado), não existe
endpoint estruturado: o HTML inicial não tem `JobPosting`, não há API documentada, e a única
forma de ler a lista de vaga (ou os próprios Termos) é executar JavaScript e raspar o DOM
renderizado — exatamente o que a regra "não fazer" de todos os coletores da Fase 20 exclui.
Crossover roda seu próprio pipeline de contratação (testes/entrevistas via "Crossover for
Work"), não delega a nenhum ATS que o radar já coleta.

## Landing.jobs (`landing.jobs/jobs`)

### robots.txt (verificado — `https://landing.jobs/robots.txt`)

```
User-agent: *
Disallow: /job_closed.html
Disallow: /backoffice/
Disallow: /employers/request_info
Disallow: /employers/request_source_access
Disallow: /employers/search
Disallow: /api/
Disallow: /jobs/search

Sitemap: https://landing.jobs/sitemap.xml
```

Bloqueia `/api/` e `/jobs/search` nomeadamente — sinal técnico relevante, mas, pela mesma regra
do F20-32, não decide a viabilidade por si (o robots.txt de Gupy também não bloqueava `/` e o
card fechou pelos Termos, não pelo robots.txt).

### Termos de Uso (decisivo) — `https://landing.jobs/tos` (atualizado 2026-04-17)

A "Plataforma" é definida como "our website (the 'Platform' or 'website':
[https://landing.jobs](https://landing.jobs))" — sem seção separada para a API. Seção 8
("Prohibited Uses") proíbe, entre outras coisas:

> "Use, support or develop software, devices, scripts, robots or any other means or processes
> to access, monitor, scrape or copy the Platform"

> "Use any manual process to monitor or copy any of the material of the Platform, unless
> expressly permitted"

> "Copy, use, display or distribute any information obtained from the Platform"

> "[Monetizing] the platform without permission"

Busca dirigida por "API" no documento inteiro não encontrou nenhuma menção — os Termos não
descrevem, autorizam nem isentam o uso do endpoint HTTP documentado no GitHub. A cláusula
"access, monitor, scrape or copy the Platform" e "distribute any information obtained from the
Platform" cobrem, pelo texto, qualquer acesso automatizado ao site — inclusive a um endpoint
`landing.jobs/api/v1/...` que vive no mesmo domínio, mesmo sendo alcançável sem login.

### API pública — verificação do status atual (pedido explícito do card)

O usuário lembrava que Landing.jobs "teve" API pública; esta pesquisa verificou que **ainda
está no ar hoje**:

- `GET https://landing.jobs/api/v1/jobs` → `200`, JSON real com vagas (`id`, `title`,
  `company_id`, tipo de contrato, localização, faixa salarial, `expires_at`, tags, remoto/
  relocation, timestamps).
- `GET https://landing.jobs/api/v1/companies` → `200`.
- Documentada em `github.com/LandingJobs/LandingJobs-api`: endpoints `Companies` e `Jobs` **não
  exigem autenticação**; só `/user` exige token. Sem menção a limite de taxa, licença, aviso de
  descontinuação ou termos próprios da API no README.
- Nenhuma referência encontrada (busca na web) a um "programa de parceiros"/termos de
  redistribuição de dado via API distintos dos Termos gerais do site — as integrações
  documentadas com Greenhouse e Workable são para a Landing.jobs **exportar candidatura** da
  empresa (ATS da empresa recebe o candidato), não para a vaga ser publicada num board
  Greenhouse/Workable que o radar já coleta.

### Decisão

**Não viável, apesar da API tecnicamente aberta e ainda ativa.** Os Termos vigentes (2026-04-17)
nomeiam "scrape or copy the Platform" e "distribute any information obtained from the
Platform", sem qualquer cláusula específica de API/parceria que abra excepção — e o próprio
`robots.txt` já sinaliza (não decide, mas reforça) que `/api/` não é destinado a acesso de
terceiros ao bloqueá-lo nomeadamente. O mesmo padrão de "acesso tecnicamente aberto não é
permissão contratual" já decidiu Wellfound (GraphQL interno alcançável só por engenharia
reversa) e YC/WaaS (Algolia observado por terceiros) em F20-51/F20-52 — aqui o endpoint é ainda
mais aberto (sem CSRF, sem cookie, documentado no GitHub oficial da empresa), mas o texto do
Termo não distingue. Landing.jobs também não delega a vaga a nenhum ATS que o radar já coleta
(é board próprio; a integração com Greenhouse/Workable é para exportar candidatura, não para
hospedar a vaga).

**Incerteza registrada:** esta é a decisão mais próxima de "viável" das quatro — se o usuário
quiser seguir por essa via, o caminho legítimo (fora do mandato desta pesquisa, que é só leitura
pública e sem contato comercial) é abrir contato com a Landing.jobs para um acordo de
parceria/API explícito, não usar o endpoint hoje documentado sem esse acordo.

## Precedente aplicado (F20-32, F20-51, F20-52)

- `robots.txt` isolado não decide nada nos quatro sites — em Braintrust e Careerflow é
  permissivo; em Landing.jobs bloqueia `/api/` (sinal, não decisão); em Crossover é permissivo.
- Termos com cláusula **nomeada** de scraping/mineração/agregação/redistribuição decidem
  sozinhos, mesmo quando existe um endpoint técnico aberto (Landing.jobs) — mesma lógica de
  Wellfound/YC.
- Termos **genéricos** (só "ferramenta não autorizada", sem nomear scraping/mineração) não
  decidem por si — mesma leitura já usada para Workday/Teamtailor/Workable/Factorial — mas
  Braintrust não tem, ainda assim, nenhum endpoint estruturado para coletar.
- Ausência de qualquer HTML citável (Crossover) é tratada como "não viável por falta de
  evidência de endpoint estruturado e de Termos legíveis", não como aprovação por omissão.
- Nenhuma chamada de coleta de vaga foi feita contra nenhum dos quatro sites. As únicas
  requisições foram `robots.txt`, a página `/jobs` (para checar `JobPosting`), a página de
  Termos pública, e duas chamadas de leitura ao endpoint documentado da API da Landing.jobs
  (`/api/v1/jobs`, `/api/v1/companies`) para confirmar seu status atual.

## Decisão consolidada

**Não viável nos quatro casos.** Nenhum coletor, sonda de descoberta, alteração em
`registry.py`/`probing.py`/`proposals.py`/`registration.py`, nem alteração em `apps/web` é feita
por esta pesquisa. Nenhum ATS novo é adicionado a `SUPPORTED_ATS` nem a `PROBE_TYPES`.

## Referências

- https://app.usebraintrust.com/robots.txt (verificado)
- https://www.usebraintrust.com/terms (verificado, seção "Prohibited Uses of the Site")
- https://www.careerflow.ai/robots.txt (verificado)
- https://www.careerflow.ai/terms (verificado)
- https://help.careerflow.ai (referência de terceiro sobre agregação de +50 boards, contexto)
- https://www.crossover.com/robots.txt (verificado)
- https://www.crossover.com/terms-and-conditions, https://www.crossover.com/website-terms
  (tentativa de leitura; ambas devolvem o shell SPA vazio, sem texto — não usadas para decisão)
- https://landing.jobs/robots.txt (verificado)
- https://landing.jobs/tos (verificado, Seção 8 "Prohibited Uses")
- https://github.com/LandingJobs/LandingJobs-api (verificado, documentação da API)
- `https://landing.jobs/api/v1/jobs`, `https://landing.jobs/api/v1/companies` (verificado — `200`
  com dados reais, sem autenticação, nesta pesquisa)
