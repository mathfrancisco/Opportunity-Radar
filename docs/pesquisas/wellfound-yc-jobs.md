# Pesquisa — Wellfound e Y Combinator (Work at a Startup) como fonte de vagas

**Data:** 2026-09-28
**Cards relacionados:** [F20-51 — Wellfound](../44-roadmap-fase-20/fase-20/f20-51-wellfound.md),
[F20-52 — Work at a Startup / YC Jobs](../44-roadmap-fase-20/fase-20/f20-52-work-at-a-startup.md)
**Pergunta:** dá para automatizar a coleta de vagas de `wellfound.com/jobs` e de
`ycombinator.com/jobs` (Work at a Startup, `workatastartup.com`) para o radar?
**Padrão aplicado:** o mesmo do F20-32 (Gupy) — revisão de termos e robots.txt antes de
qualquer código; termo com proibição nomeada de agregação/coleta automatizada encerra o
card como "não viável", sem escrever coletor.

## Resumo do veredito

| Site | robots.txt | Termos de Uso | API pública | Anti-bot | Veredito |
| --- | --- | --- | --- | --- | --- |
| Wellfound (`wellfound.com/jobs`) | permite `/` e páginas de vaga (não bloqueia por si) | proíbe nomeadamente scraping/agregação automatizada e uso competitivo do conteúdo (Seção III) | nenhuma API pública; GraphQL interno exige sessão autenticada + token CSRF + cookie DataDome | DataDome + Cloudflare ativos em todo o fluxo de busca de vagas | **Não viável** — nem coleta direta, nem descoberta automatizada de empresas |
| Y Combinator Jobs / Work at a Startup (`ycombinator.com/jobs`, `workatastartup.com`) | `ycombinator.com`: `Allow: /`, sem regra específica para `/jobs`; `workatastartup.com`: `Disallow:` vazio (permite tudo) | Termos gerais da YC ("Legal", que cobre expressamente o programa Work at a Startup) proíbem "data mining, robots, scraping ou métodos similares de coleta ou extração de dados" em conexão com o uso do Site | Algolia é usado internamente pelo front-end (`companies`/`search_jobs`), mas não há chave pública documentada nem contrato de API estável — só endpoints observados por terceiros via engenharia reversa | Não identificado bloqueio tipo DataDome/Cloudflare explícito, mas a barreira é contratual, não técnica | **Não viável** — mesma cláusula nomeada, mesmo padrão de fechamento do F20-32 |

Nos dois casos, a proibição contratual (Termos de Uso) é o fator decisivo, exatamente como
em F20-32 (Gupy): a robots.txt isolada não bloqueia a leitura da página de vagas em nenhum
dos dois sites, mas isso "por si só não decide a viabilidade" (mesma frase usada em
`docs/pesquisas/termos-gupy.md`) — os Termos de Uso proíbem por outro caminho.

## Wellfound (`wellfound.com/jobs`)

### robots.txt (verificado — `https://wellfound.com/robots.txt`)

```
Disallow: /_jobs/
Disallow: /*?after_sign_in=*
Disallow: /*?inFrame=*
Disallow: /*?jobId=*
Disallow: /*?jobSlug=*
Disallow: /*?preview=*
Disallow: /*?role=*
Disallow: /*&inFrame=*
Disallow: /*&jobId=*
Disallow: /*&jobSlug=*
Disallow: /*&preview=*
Disallow: /auth/
Disallow: /cdn-cgi/
Disallow: /documents/
Disallow: /embed/
Disallow: /job_listings/report_company
Disallow: /job_pairings/howitworks
Disallow: /job_profiles/embed
Disallow: /jobs/applications
Disallow: /jobs/signup
Disallow: /onboarding
Disallow: /profile/edit
Disallow: /profile/notifications
Disallow: /profile/review
Disallow: /profile/resume
Disallow: /projects/
Disallow: /re/
Disallow: /recruit/dashboard
Disallow: /search
Disallow: /social/share_modal
Disallow: /u/

Sitemap: https://wellfound.com/sitemap.xml.gz
Sitemap: https://wellfound.com/blog-index.xml.gz
```

A rota geral de vagas (`/jobs`, páginas de vaga sem os parâmetros bloqueados) não está em
`Disallow`. Só a busca (`/search`) e URLs de vaga com parâmetros específicos
(`jobId`, `jobSlug`, `preview`, `role`) estão bloqueadas — o que já cobre a maior parte dos
links de vaga que a UI gera na prática, mas não decide a viabilidade por si.

### Termos de Uso (decisivo) — `https://wellfound.com/terms`

Na seção III ("Covenants"), cláusula de restrições de acesso automatizado:

> "use any automated system (including a spider, robot, or offline reader) to access the
> Site or Services in a manner that takes more bandwidth or produces greater load on
> Wellfound's network or servers than a human can reasonably produce in the same period of
> time by using a conventional on-line web browser"

com uma exceção nomeada só para buscadores públicos:

> "(except Wellfound grants public search engines revocable permission to copy materials
> from the publicly available searchable indices of the materials, excluding any caches or
> archives of such materials)"

E, na mesma seção, proibição nomeada de cópia/distribuição de conteúdo por scraping:

> "copy, disclose or distribute Content except as expressly permitted by the Terms
> (including through the use of automated or non-automated harvesting, collection or
> 'scraping') or otherwise use the Site or Services for competitive purposes"

Essa segunda cláusula é o equivalente direto da cláusula da Gupy ("agregar, copiar ou
duplicar partes do Gupy Recrutamento e Seleção"): nomeia "scraping" e "harvesting" de forma
explícita, exclui qualquer permissão implícita da exceção de buscadores (que é revogável e
só para buscadores públicos, não para agregadores de vagas) e ainda proíbe "uso para fins
competitivos" — que é exatamente o que um radar de oportunidades faz ao reagregar vagas de
Wellfound em outro produto.

### API pública, autenticação, anti-bot

Não há API JSON pública documentada. O front-end usa um endpoint GraphQL interno
(`/graphql`), mas ele só é alcançável pela aplicação web autenticada: exige token CSRF,
cookie de sessão (`_wellfound`) e cookie do DataDome. O próprio material de case da
DataDome confirma que a Wellfound implantou DataDome (com Cloudflare) especificamente
porque "scrapers gathering content to republish or resell it elsewhere" eram alvo comum, e
que caminhos de busca de vaga sem esses cookies retornam 403 com página de captcha
(`datadome.co/customers-stories/33-less-bot-traffic-lower-costs-how-wellfound-gains-time-tranquility-with-datadome/`).
Ou seja: mesmo ignorando os Termos de Uso, o acesso automatizado de baixa frequência e sem
login que os outros coletores da Fase 20 usam (Workday, Teamtailor, Workable, Factorial,
JobPosting) não teria como funcionar de forma estável contra Wellfound sem contornar
DataDome — o que a própria cláusula de Termos de Uso também proíbe nomeadamente
("you agree not to implement any measures to circumvent such blocking").

### Wellfound como fonte de descoberta (só nomes de empresa)

Mesmo restringindo o uso a "ler a lista de empresas que anunciam vaga" (sem coletar o
conteúdo da vaga), a operação ainda seria "usar sistema automatizado para acessar o Site"
e "harvesting/collection" de Content — a cláusula não distingue entre coletar a vaga inteira
ou só metadados de empresa via automação. A barreira técnica do DataDome também se aplica
à navegação da lista, não só ao detalhe da vaga. Não há caminho de descoberta automatizada
viável aqui, diferente do que F20-36 faz com `robots.txt`/`sitemap.xml` de sites de empresa
que não têm essa cláusula.

## Y Combinator Jobs / Work at a Startup (`ycombinator.com/jobs`, `workatastartup.com`)

### robots.txt (verificado)

`https://www.ycombinator.com/robots.txt`:

```
Disallow: /verify/*
Disallow: /library?categories=*&*
Disallow: /library?*
Disallow: /companies?*

Allow: /library?categories=*
Allow: /
```

(mais exceções nomeadas para `facebookexternalhit`, `Twitterbot`, `LinkedInBot` em
`/verify/*`). Nenhuma regra cobre `/jobs` especificamente — a rota de vagas do domínio
principal está, isoladamente, liberada por robots.txt.

`https://www.workatastartup.com/robots.txt`:

```
Disallow:
```

(`Disallow` vazio, sem `Allow`, sem `Sitemap`) — libera o crawling do domínio inteiro por
robots.txt. Como no caso Gupy, isso não decide a viabilidade: os Termos de Uso, abaixo,
proíbem por outro caminho.

### Termos de Uso (decisivo) — `https://www.ycombinator.com/legal` (seção "Terms of Use")

Cláusula geral de acesso automatizado, no corpo dos Termos de Uso da YC:

> "In connection with your use of the Site you will not engage in or use any data mining,
> robots, scraping or similar data gathering or extraction methods."

Cláusula de anti-evasão de bloqueio, na mesma seção:

> "If you are blocked by Y Combinator from accessing the Site (including by blocking your
> IP address), you agree not to implement any measures to circumvent such blocking (e.g.,
> by masking your IP address or using a proxy IP address)."

E cláusula de uso comercial:

> "you agree not to display, distribute, license, perform, publish, reproduce, duplicate,
> copy, create derivative works from, modify, sell, resell, exploit, transfer or upload for
> any commercial purposes, any portion of the Site"

Esses mesmos Termos de Uso descrevem, na mesma página, o programa "Work at a Startup"
("WaaS") e a coleta de dados de candidato (nome, e-mail, LinkedIn, elegibilidade de
trabalho, experiência, formação, habilidades) para repassar a empresas financiadas pela
YC — ou seja, o documento que contém a cláusula de proibição de scraping é também o
documento que rege o próprio Work at a Startup, não um texto genérico de um produto
não relacionado. `workatastartup.com/terms` existe como página própria ("Terms of Use |
Y Combinator's Work at a Startup"), renderizada em React (SPA) — não foi possível extrair o
corpo do texto por fetch simples (sem JS), mas o título e a estrutura confirmam que é o
mesmo guarda-chuva legal da YC, e nada nas páginas de legal/imprensa da YC sugere um regime
de termos mais permissivo para `workatastartup.com` do que para `ycombinator.com`.

A cláusula "will not engage in or use any data mining, robots, scraping or similar data
gathering or extraction methods" é, se possível, mais direta que a cláusula da Gupy: não
depende de interpretar "agregar" ou "Usuários em geral" — nomeia scraping e robots
explicitamente, sem exceção para buscadores (ao contrário de Wellfound) e sem qualificar
por volume ou frequência. Cobre tanto ler vagas quanto ler só a lista de empresas.

### API pública, autenticação, anti-bot

Não existe API pública documentada. O front-end de `workatastartup.com` usa Algolia
internamente (índices observados por terceiros como `companies` e `search_jobs`, citados
em scrapers de terceiros no GitHub e Apify), mas sem chave pública nem contrato estável —
o acesso encontrado por projetos de terceiros depende de reverse engineering da chamada
interna do front-end, o que é precisamente a "extraction method" que os Termos de Uso
proíbem. Não foi identificada barreira tipo DataDome/Cloudflare (diferente de Wellfound):
a barreira aqui é só contratual, não técnica — o que não muda o veredito, pelo mesmo
padrão do F20-32 (a decisão já é negativa pelos Termos de Uso, independente de existir ou
não bloqueio técnico).

### YC/WaaS como fonte de descoberta (só nomes de empresa)

Mesmo problema do Wellfound: a cláusula da YC proíbe "data mining, robots, scraping ou
métodos similares de **coleta ou extração de dados**" em conexão com o uso do Site — sem
distinguir se o dado extraído é a vaga completa ou só a lista de empresas batch-a-batch do
YC. Usar `ycombinator.com/jobs` ou `workatastartup.com` apenas como lista de empresas para
alimentar `probe_direct_ats`/`limited_discovery.py` (que já provam ATS como Ashby,
Greenhouse, Lever, Workable, Teamtailor, Workday, Factorial nos sites das próprias
empresas) seria, ainda assim, uma extração automatizada de dados do Site da YC — a mesma
operação proibida, só que como etapa intermediária. Não há caminho de descoberta
automatizada viável.

Vale registrar, para contexto (não para decisão): muitas empresas do batch YC hoje já usam
ATS que o radar coleta diretamente (Ashby e Greenhouse são comuns em startups YC). A rota
legítima para cobrir essas empresas não é ler o índice do YC/WaaS, e sim continuar
alimentando `limited_discovery.py`/F20-27 com fontes primárias que a própria empresa
publica (site institucional, sitemap, página de carreiras) — o que já é o mecanismo
existente e não depende de Wellfound nem de YC.

## Precedente aplicado (F20-32)

Este card segue a mesma régua do F20-32 (Gupy):

- robots.txt isolado não decide nada — nos dois sites daqui, ele é, se qualquer coisa,
  mais permissivo do que o da Gupy (que também não bloqueava `/`).
- O que decide é a existência de cláusula **nomeada** proibindo scraping/agregação/mineração
  de dados, distinta da cláusula genérica de "não sobrecarregar o serviço" que Workday,
  Teamtailor, Workable e Factorial tinham (e que foi lida como não bloqueando coleta de
  baixa frequência sem login).
- Wellfound e YC/WaaS têm essa cláusula nomeada — Wellfound cita "scraping"/"harvesting"
  explicitamente com exceção só para buscadores; YC cita "data mining, robots, scraping"
  sem exceção alguma. Os dois casos são, portanto, mais claros que a Gupy, não menos.
- Nenhuma chamada de coleta foi feita contra board real de nenhum dos dois sites. As únicas
  requisições desta pesquisa foram: `robots.txt` dos dois domínios (mais
  `workatastartup.com`), a página de Termos de Uso pública de cada site, e buscas na web
  sobre anti-bot/API documentadas por terceiros — nenhuma delas é coleta de vaga.

## Decisão

**Não viável — nem coleta direta, nem uso como fonte de descoberta de empresa —, para os
dois sites.** Wellfound (`wellfound.com/jobs`) e Y Combinator Jobs / Work at a Startup
(`ycombinator.com/jobs`, `workatastartup.com`) proíbem, nos próprios Termos de Uso,
exatamente a operação de um coletor ou de uma sonda de descoberta: extrair/agregar dados do
site por meio automatizado. Os cards F20-51 e F20-52 fecham aqui, sem nenhum código de
coletor, sonda, registro em `registry.py`/`probing.py`/`proposals.py`/`registration.py`,
nem alteração em `apps/web`. Nenhum ATS novo é adicionado a `SUPPORTED_ATS` nem a
`PROBE_TYPES` por este card.

## Referências

- https://wellfound.com/robots.txt (verificado)
- https://wellfound.com/terms (verificado, Seção III — Covenants)
- https://datadome.co/customers-stories/33-less-bot-traffic-lower-costs-how-wellfound-gains-time-tranquility-with-datadome/
  (case público da DataDome confirmando bloqueio de scraping em Wellfound)
- https://www.ycombinator.com/robots.txt (verificado)
- https://www.workatastartup.com/robots.txt (verificado)
- https://www.ycombinator.com/legal (verificado, seção "Terms of Use", inclui a descrição
  do programa Work at a Startup na mesma página)
- https://www.workatastartup.com/terms (título confirmado: "Terms of Use | Y Combinator's
  Work at a Startup"; corpo renderizado em React, não extraído por fetch simples — usado só
  para confirmar que existe página própria sob o mesmo guarda-chuva legal da YC)
- Referências de terceiros (não usadas para decisão, só para confirmar ausência de API
  pública documentada e presença de anti-bot): `apify.com/*/wellfound-*-scraper`,
  `apify.com/*/workatastartup-scraper`, `github.com/subbuwu/wellfound_graphqlscout`,
  `github.com/jwc20/waasuapi`, `pypi.org/project/ycombinator-scraper`
