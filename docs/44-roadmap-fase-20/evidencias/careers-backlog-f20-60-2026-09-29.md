# F20-60 — Careers reais das 20 empresas `backlog` (2026-09-29)

Pesquisa apenas (sem tocar em pilha Docker, sem gravar no acervo). Objetivo: achar a URL de carreiras real e o ATS de cada empresa que ficou `radar_status=backlog` no F20-60 (`mapa-carreira-vs-catalogo-2026-09-28.md`, "Incerteza"; `validacao-pendente.md` §4 item 7).

## Método e gasto

- Lista das 20: o card não nomeia as 20 explicitamente; foram derivadas das 42 empresas classe (d) importadas menos as 22 elegíveis (9 com ATS achado + 13 sem ATS achado) citadas no relatório. Resultado: DoorDash, Mercado Livre, Nuvemshop, TECLA, Howdy, FullStack, AgileEngine, Cognizant, TCS, Infosys, Strider, Remotebase, Gun.io, Arc, Lemon.io, Terminal, AI/R (Avenue Code), Stefanini, act digital, Grupo OLX. **NAVA** não está nesta lista: ficou entre as 13 elegíveis sem ATS (não `backlog`); o relatório a cita só como caso ambíguo. Coberta em nota abaixo por completude.
- Ferramentas: busca web, GET simples nas páginas públicas e nos endpoints públicos dos ATS que o projeto já coleta (Greenhouse `boards-api`, Lever, Ashby `posting-api`, Workable widget), leitura de `robots.txt`.
- Tavily: **0 créditos gastos** (de 100 permitidos).
- Proibidos respeitados: Gupy, Wellfound, YC/Work at a Startup, Careerflow, Crossover, Braintrust, Landing.jobs — nunca acessados além de aparecerem como link em resultado de busca.
- Cuidado com falso positivo: o widget Workable devolve HTTP 200 para qualquer slug (com `jobs` vazio); Ashby/Greenhouse devolvem 200 para slugs de empresas homônimas. Cada slug abaixo foi conferido pelo conteúdo (nome/descrição das vagas), não só pelo status.
- Coletores do projeto (`src/opportunity_radar/acquisition/`): ashby, factorial, greenhouse, jobposting (JSON-LD), lever, teamtailor, workable, workday. Sem SmartRecruiters, sem BambooHR, sem inhire, sem Breezy.

## Tabela

| # | Empresa | URL de carreiras | ATS + board id/slug | Coletor suportado | Recomendação | Evidência |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | DoorDash | `https://careersatdoordash.com/job-search/` (403 a bot) → board `https://job-boards.greenhouse.io/doordashusa` | Greenhouse `doordashusa` (463 vagas, ex.: "Account Executive") | sim | **activate** | `https://boards-api.greenhouse.io/v1/boards/doordashusa/jobs` (200, 463); resultados de busca de vagas reais em `job-boards.greenhouse.io/doordashusa/jobs/7659437` |
| 2 | Mercado Livre | `https://careers-meli.mercadolibre.com/en` (`mercadolibre.com/jobs` redireciona para lá; `mercadolivre.com.br` do palpite antigo não resolve) | Site próprio (SPA + Prismic para conteúdo), sem ATS público identificado; JSON-LD não confirmado | não | **probe** (ver se páginas de vaga têm JSON-LD `JobPosting`) | `https://mercadolibre.com/jobs` (meta refresh); `careers-meli.mercadolibre.com/en` 200; robots: `Disallow: /api /_next` (não usar API interna) |
| 3 | Nuvemshop | `https://www.nuvemshop.com.br/trabalhe-na-nuvemshop` (o `/carreiras` do palpite dá 404) | inhire (`nuvemshop-tiendanube.inhire.app`); sem JSON-LD nas páginas de vaga | não | **probe** (sem coletor inhire; só vale se JSON-LD aparecer em página de vaga individual) | HTML de `trabalhe-na-nuvemshop` lista links `nuvemshop-tiendanube.inhire.app/vagas/...`; `.../vagas` 200 sem `JobPosting` |
| 4 | TECLA | `https://www.tecla.io/about/careers` (`/join` = mercado de vagas de clientes) | Fluxo próprio (`/careers-application`, `app.tecla.io`); sem ATS externo | não | **no-site** (sem quadro de vagas próprio estruturado) | `https://www.tecla.io/about/careers` (200, só links LinkedIn/aplicação); `robots.txt` sem bloqueio de vagas |
| 5 | Howdy | `https://www.howdylatam.com/careers` (vagas de clientes para devs LatAm; `howdy.com/careers` responde 429) | Sem ATS externo na página; vagas próprias só aparecem no YC Work at a Startup (proibido) | não | **blocked: YC / Work at a Startup** (única fonte de vagas próprias achada) | Busca: `workatastartup.com/companies/22658` (não acessado); `howdylatam.com/careers` 200 sem ATS |
| 6 | FullStack (FullStack Labs, fullstack.com) | `https://www.fullstack.com/talent/for-talent` (`/careers` dá 404) | Sem ATS identificado. **Atenção:** o board Ashby `fullstack` existe (5 vagas) mas é de outra empresa (plataforma de trading em NYC), não a FullStack Labs | não | **probe** (achar o quadro real; não ativar o Ashby `fullstack`) | Ashby `posting-api/job-board/fullstack` = "Fullstack ... retail trading platform"; `fullstack.com/talent/for-talent` 200 |
| 7 | AgileEngine | `https://join.agileengine.com/open-positions/` | Portal próprio (`join.agileengine.com`), detalhe de vaga com JSON-LD `JobPosting`; todas as vagas exibem "New applications are currently paused" | jobposting: sim (coletor `jobposting`) | **probe** (JSON-LD presente; vagas pausadas, rendimento pode ser baixo) | `.../open-positions/senior-full-stack-engineer-arkestro-id91466/` contém `JobPosting`; robots sem disallow relevante |
| 8 | Cognizant | `https://careers.cognizant.com/global-en/` (403 a bot; `robots.txt` 200 sem disallow) | Portal próprio/Phenom-like (`/us-en/jobs/<id>/<slug>`), ATS não confirmado. Workable `cognizant` existe mas com 0 vagas (inativo) | não | **probe** (bloqueio de bot 403 impede confirmar JSON-LD; provável parada) | Resultado de busca `careers.cognizant.com/us-en/jobs/46834/...`; widget Workable `cognizant` `jobs: []` |
| 9 | TCS (Tata Consultancy Services) | `https://www.tcs.com/careers` (403 a bot) → `https://ibegin.tcs.com/iBegin/jobs/search` | Portal próprio iBegin. **Atenção:** o Greenhouse `tcs` (98 vagas de enfermagem no Reino Unido) é de outra empresa; Workable `tcs` vazio | não | **probe** (iBegin é app dinâmico; não ativar `tcs` do Greenhouse) | Busca: `ibegin.tcs.com/iBegin/jobs/search`; Greenhouse `tcs` primeira vaga "Community Adult Nurse - Bath" |
| 10 | Infosys | `https://career.infosys.com/` (200; `www.infosys.com/careers` 403 a bot) | Portal próprio, sem ATS externo identificado | não | **probe** (JSON-LD não verificado; `robots.txt` sem disallow) | `career.infosys.com` 200; busca `career.infosys.com/register` |
| 11 | Strider | `https://www.onstrider.com/jobs` (a empresa é `onstrider.com`; `strider.com` do palpite é domínio parqueado/outra empresa) | Sem ATS externo; página de vagas próprias de clientes (marketplace) | não | **no-site** (sem quadro de vagas de emprego próprio; marketplace de matching) | `strider.com/careers` → `/lander`; busca `onstrider.com/jobs`, `onstrider.com/about/` |
| 12 | Remotebase | `https://apply.workable.com/remotebase/` (site `remotebase.com` sem link direto) | Workable `remotebase` (nome "Remotebase", 5 vagas, ex.: "AI Engineer") | sim | **activate** | `https://apply.workable.com/api/v1/widget/accounts/remotebase` (200, `name: Remotebase`, 5 vagas); robots do site sem bloqueio de vagas |
| 13 | Gun.io | `https://gun.io/jobs/` | Marketplace de freelancers; sem quadro de vagas próprio/ATS | não | **no-site** (não publica vagas de emprego próprias) | `https://gun.io/` "Post a Role / Apply as a Freelancer"; `gun.io/careers` 404 |
| 14 | Arc | `https://arc.dev/careers` → página Notion (`app.notion.com/p/codementor/Hi-we-re-Arc-and-Codementor-...`) | Nenhum ATS; página Notion. `arc.dev/remote-jobs` é marketplace de terceiros | não | **no-site** (sem ATS; Notion) | Redirect de `arc.dev/careers` para Notion; `arc.dev/remote-jobs` = marketplace |
| 15 | Lemon.io | `https://lemon.io/careers` → `https://lemonio.bamboohr.com/careers/` | BambooHR (`lemonio`, sem coletor) **e** Ashby `lemon-io` (4 vagas, descrições "About Lemon.io") | sim (Ashby) | **activate** (Ashby `lemon-io`) | `https://api.ashbyhq.com/posting-api/job-board/lemon-io` (200, 4 vagas: Head of Engineering, Growth Manager...); redirect BambooHR confirma domínio |
| 16 | Terminal (terminal.io) | `https://www.terminal.io/engineers/job-openings` (403 a bot; vagas de clientes, EOR) | Sem ATS próprio achado. **Atenção:** o Ashby `terminal` (9 vagas em Toronto) é de outra empresa (telemática para frotas) | não | **probe** (site bloqueia bot; não ativar o Ashby `terminal`) | Ashby `terminal`: "Terminal builds telematics data infrastructure for the commercial fleet industry"; `terminal.io` 403 |
| 17 | AI/R — Avenue Code | `https://aircompany.ai/en/open-opportunities/` (`avenuecode.com/en/careers` redireciona para lá) | Sem ATS público; vagas via LinkedIn (`linkedin.com/company/airevolutioncompany/jobs/`). **Atenção:** o Greenhouse `aircompany` (6 vagas) é AIRCO (química), não a AI/R | não | **probe** (ATS não divulgado; LinkedIn não é fonte a raspar; não ativar `aircompany`) | `WebFetch aircompany.ai/en/open-opportunities/`: "brands Avenue Code, Compass UOL, Edgy, Everymind, Invillia, Synsig, WEBJUMP", jobs via LinkedIn; Greenhouse `aircompany` board name "AIRCO" |
| 18 | Stefanini | `https://vagas.grupostefanini.com.br/` (ATS não identificado) e `https://stefanini.gupy.io/` (principal) | Gupy `stefanini` (principal) | não (Gupy vedado) | **blocked: Gupy** | Busca: `stefanini.gupy.io/` e `vagas.grupostefanini.com.br/` |
| 19 | act digital | `https://lp.actdigital.com/tech-impactor-recruiter` (LP de recrutamento; sem ATS) | Nenhum ATS público achado (vagas via LinkedIn/Indeed/Glassdoor); Workable `act-digital` vazio | não | **no-site** (sem quadro próprio) | `lp.actdigital.com/tech-impactor-recruiter` 200 só com link LinkedIn; `actdigital.com/careers` 404 |
| 20 | Grupo OLX | `https://grupoolx.com.br/carreira` | Gupy `vemsergrupoolx` (link direto na página); SmartRecruiters `OLXBrasil` sem vagas | não (Gupy vedado; sem coletor SmartRecruiters) | **blocked: Gupy** | HTML de `grupoolx.com.br/carreira` contém `vemsergrupoolx.gupy.io`; API SmartRecruiters `OLXBrasil` `totalFound=0` |

Nota NAVA (fora da lista das 20, entre as 13 elegíveis): sem evidência nova nesta rodada; segue ambígua entre a NAVA brasileira e a americana de saúde. Nenhuma sondagem feita.

## Resumo por recomendação

| Recomendação | Empresas |
| --- | --- |
| activate (3) | DoorDash (Greenhouse `doordashusa`), Remotebase (Workable `remotebase`), Lemon.io (Ashby `lemon-io`) |
| probe (9) | Mercado Livre, Nuvemshop, FullStack, AgileEngine, Cognizant, TCS, Infosys, Terminal, AI/R (Avenue Code) |
| blocked (3) | Howdy (YC / Work at a Startup), Stefanini (Gupy), Grupo OLX (Gupy) |
| no-site (5) | TECLA, Strider, Gun.io, Arc, act digital |

## Robots/termos (sinais rápidos)

- `robots.txt` lido em 16 hosts. Sem `Disallow` que cubra listagem de vagas para `*` em: career.infosys.com, careers.cognizant.com, join.agileengine.com, nuvemshop.com.br, tecla.io, onstrider.com, fullstack.com, remotebase.com, grupoolx.com.br. Em `careers-meli.mercadolibre.com`: `Disallow: /api /_next` (portanto não consumir a API interna, só HTML). `lemonio.bamboohr.com`: só bloqueia `/jobs/embed*`.
- Endpoints públicos Greenhouse/Lever/Ashby/Workable usados só para conferir a existência do board (uma requisição por slug), sem coleta.
- Termos de uso de sites individuais não foram lidos; risco residual a confirmar antes de ativar fontes que não sejam API pública de ATS.
- Bot 403 (Cognizant, TCS, Infosys `www`, DoorDash `careersatdoordash.com`, terminal.io) é proteção de site, não sinal de proibição; não foi contornado.

## Incertezas

- A lista das 20 foi derivada por subtração (o card não a nomeia); se a lista real da `f20manual` diferir (por exemplo NAVA no lugar de outra), pedir a consulta `SELECT name FROM company_radar.company WHERE radar_status='backlog'` na `f20manual` (não executada aqui, sem tocar em stack).
- Slugs `doordashusa`, `remotebase`, `lemon-io` confirmados por conteúdo das vagas, mas pertencimento é inferência por nome/descrição; recomenda-se `discover_ats.py` na `f20manual` antes de ativar em produção.
- "Probe" em Cognizant, TCS, Infosys, Terminal e Mercado Livre significa não confirmado: páginas dinâmicas ou bloqueio a bot impediram verificar JSON-LD.
- Strider: interpretado como `onstrider.com` (matching LatAm); o `strider.com` do palpite é parqueado.
- Howdy: `howdy.com` respondeu 429; a conclusão vem de busca + `howdylatam.com`.
