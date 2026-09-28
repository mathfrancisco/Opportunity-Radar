# Mapa de carreira internacional (Notion) vs. catálogo do projeto — 2026-09-28

## Origem e método

- **Entrada:** export do Notion "15 · Mapa de Carreira Internacional — Empresas &
  Estratégia" (1358 linhas) e os dois CSVs anexos (`Application Pipeline`,
  `Untitled`) — ambos apenas com o cabeçalho de propriedades e uma linha vazia,
  sem candidaturas registradas; nada de dado pessoal foi copiado para este
  documento ou para o repositório.
- **Catálogo comparado:** `company_radar.company` + `company_radar.company_source`
  (223 empresas) e `acquisition.source_definition` (fontes habilitadas, incluindo
  definições sem `company_source_id` vinculado mas cujo nome identifica a empresa —
  ex.: `MongoDB (Greenhouse)`, `Zapier (Ashby)`) no banco do projeto Docker
  `f20manual` (somente leitura; `opportunity-radar` não foi tocado).
- **Catálogo de pesquisa:** `docs/pesquisas/auditoria-186-empresas.md` (importado por
  `scripts/import_research_catalog.py`) — mesmas 223 empresas do banco, já refletidas
  no dump usado aqui.
- **Extração das 100 empresas do mapa:** seções 02–04 do documento Notion (o próprio
  documento soma 37 + 44 + 17 + 2 = 100 alvos únicos; diretórios/quadros de vaga
  como Wellfound, YC, LinkedIn, We Work Remotely etc. — seção 05 — não são "empresa"
  e já têm decisão registrada nos cards F20-51/F20-52, fechados por termos de uso).
- **Correspondência:** nome canônico + normalização (case, acentos, sufixos como
  Inc/Ltda/S.A., "antiga X") comparados com `canonical_name`/`normalized_name` e
  `company_alias` do catálogo. Nenhuma linha nova foi inserida no banco; nenhuma
  fonte foi habilitada.
- **Identificação de ATS para as classes (c)/(d):** reaproveitando o padrão de URL dos
  coletores já homologados (`greenhouse.py`, `lever.py`, `workable.py`) fiz uma única
  requisição HTTP por candidato plausível (nunca Gupy — fechado no F20-32 por Termos
  de Uso), com `User-Agent` identificável, ao endpoint público do próprio ATS
  (nunca o site institucional da empresa), com pausa entre chamadas. Nenhuma
  ativação de fonte foi feita.

## Contagem por classe

| Classe | Definição | Empresas |
| --- | --- | --- |
| (a) | No catálogo, com fonte de coleta **habilitada** (`enabled=true`) | 15 |
| (b) | No catálogo, só página de carreiras / sem ATS coletável | 29 |
| (c) | No catálogo, ATS **identificado** mas fonte **desabilitada** | 5 |
| (d) | **Ausente** do catálogo | 51 |
| **Total** | | **100** |

Dentro da classe (d), 5 empresas tiveram o ATS identificado por sondagem real nesta
sessão (Loadsmart/Lever, Devsu/Workable, Azumo/Workable, Zup/Greenhouse,
EBANX/Greenhouse) — todos os quadros responderam HTTP 200 com vagas reais no board.
Red Hat tem ATS conhecido pelo próprio Notion (Workday), mas o tenant/site do Workday
não é adivinhável por uma sondagem barata (exige descoberta de site, fora do escopo
desta auditoria). As demais 45 empresas da classe (d) não têm ATS identificável a
partir do texto do Notion sem pesquisa adicional; três delas (DB, FCamara, Minsait —
Minsait já está na classe (b) por já constar no catálogo) usam Gupy, que está fechado
por Termos de Uso desde o F20-32 e nunca deve ser sondado ou coletado.

## Tabela completa — as 100 empresas do mapa

| Empresa (Notion) | Bloco Notion | Classe | Detalhe |
| --- | --- | --- | --- |
| Deel | 02 | b | Catálogo: `Deel` — só `careers`, sem ATS. |
| Remote | 02 | b | Catálogo: `Remote` — só `careers`. |
| GitLab | 02 | a | Catálogo: `GitLab` — Greenhouse habilitado. |
| Automattic | 02 | a | Fonte habilitada `Automattic (Greenhouse)`. |
| Canonical | 02 | b | Catálogo: `Canonical` — só `careers`. |
| Cloudflare | 02 | a | Fonte habilitada `Cloudflare (Greenhouse)`. |
| Docker | 02 | b | Catálogo: `Docker` — só `careers`. |
| Brex | 02 | a | Fonte habilitada `Brex (Greenhouse)`. |
| DoorDash | 02 | d | Não está no catálogo; ATS não identificado no Notion. |
| Wikimedia Foundation | 02 | b | Catálogo: `Wikimedia Foundation` — só `careers`. |
| Grafana Labs | 02 | c | Catálogo: Greenhouse `ats_identified`, fonte desabilitada. |
| Elastic | 02 | b | Catálogo: `Elastic` — só `careers`. |
| Vercel | 02 | a | Fonte habilitada `Vercel (Greenhouse)`. |
| Supabase | 02 | a | Catálogo: Ashby `api_json_confirmed`, habilitado. |
| Mercado Livre | 02 | d | Não está no catálogo; site institucional próprio, ATS não identificado. |
| Rollstack | 02 | d | Não está no catálogo; vaga só no board da YC, sem ATS estruturado próprio. |
| Roboflow | 02 | d | Não está no catálogo; vaga só no board da YC. |
| LiteLLM | 02 | d | Não está no catálogo; vaga só no board da YC. |
| Loadsmart | 02 | d | Não está no catálogo. **ATS confirmado por sondagem real 2026-09-28:** Lever (`api.lever.co/v0/postings/loadsmart`), HTTP 200 com vagas. |
| Nuvemshop | 02 | d | Não está no catálogo; ATS não identificado no Notion. |
| RevenueCat | 02 | a | Catálogo: Ashby `api_json_confirmed`, habilitado. |
| Zapier | 02 | a | Fonte habilitada `Zapier (Ashby)`. |
| Doist / Todoist | 02 | b | Catálogo: `Doist` (alias `Todoist`) — só `careers`. |
| Buffer | 02 | b | Catálogo: `Buffer` — só `careers`. |
| Toggl | 02 | b | Catálogo: `Toggl` — só `careers`. |
| TestGorilla | 02 | c | Catálogo: Ashby `ats_identified`, fonte desabilitada. |
| Storyblok | 02 | a | Fonte habilitada `Storyblok (Greenhouse)`. |
| Customer.io | 02 | c | Catálogo: Greenhouse `ats_identified`, fonte desabilitada. |
| PostHog | 02 | b | Catálogo: `PostHog` — só `careers`. |
| MongoDB | 02 | a | Fonte habilitada `MongoDB (Greenhouse)`. |
| Datadog | 02 | a | Fonte habilitada `Datadog (Greenhouse)`. |
| HubSpot | 02 | a | Fonte habilitada `HubSpot (Greenhouse)`. |
| Twilio | 02 | b | Catálogo: `Twilio` — só `careers` (radar_status backlog). |
| Red Hat | 02 | d | Não está no catálogo. ATS citado no Notion (Workday), mas tenant/site não é adivinhável por sondagem barata — precisa de pesquisa de descoberta, não sondagem direta. |
| Akamai | 02 | b | Catálogo: `Akamai` — só `careers`. |
| Oyster | 02 | a | Fonte habilitada `Oyster (Ashby)`. |
| Percona | 02 | d | Não está no catálogo; ATS não identificado no Notion. |
| TECLA | 03 | d | Não está no catálogo; ATS não identificado no Notion. |
| Howdy | 03 | d | Não está no catálogo. |
| FullStack | 03 | d | Não está no catálogo; quadro requer JavaScript, ATS não identificado. |
| Devsu | 03 | d | Não está no catálogo. **ATS confirmado por sondagem real 2026-09-28:** Workable (`apply.workable.com/api/v1/widget/accounts/devsu`), HTTP 200. |
| Jobsity | 03 | b | Catálogo: `Jobsity` — só `careers` (backlog). |
| Bluelight Consulting | 03 | d | Não está no catálogo. |
| Lumenalta | 03 | b | Catálogo: `Lumenalta` — só `careers` (backlog). |
| X-Team | 03 | b | Catálogo: `X-Team` — só `careers`. |
| BairesDev | 03 | b | Catálogo: `BairesDev` — só `careers` (backlog). |
| Thoughtworks | 03 | b | Catálogo: `Thoughtworks` — só `careers`. |
| Globant | 03 | b | Catálogo: `Globant` — só `careers`. |
| EPAM | 03 | b | Catálogo: `EPAM Systems` — só `careers`. |
| Encora | 03 | d | Não está no catálogo. |
| Nearsure | 03 | b | Catálogo: `Nearsure` — só `careers`. |
| AgileEngine | 03 | d | Não está no catálogo. |
| NTT DATA | 03 | c | Catálogo: Workday `ats_identified`, fonte desabilitada. |
| Accenture | 03 | c | Catálogo: Workday `ats_identified`, fonte desabilitada. |
| Capgemini | 03 | b | Catálogo: `Capgemini` — só `careers`. |
| Cognizant | 03 | d | Não está no catálogo. |
| Tata Consultancy Services (TCS) | 03 | d | Não está no catálogo. |
| Infosys | 03 | d | Não está no catálogo. |
| Wipro | 03 | d | Não está no catálogo. |
| IBM | 03 | d | Não está no catálogo. |
| Softtek | 03 | d | Não está no catálogo. |
| GFT | 03 | b | Catálogo: `GFT` — só `careers`. |
| Minsait | 03 | b | Catálogo: `Minsait` — só `careers`. ATS real é Gupy (`minsait.gupy.io`), fechado desde F20-32; não sondar. |
| Strider | 03 | d | Não está no catálogo (rede/matching, não ATS próprio). |
| Remotebase | 03 | d | Não está no catálogo. |
| Braintrust | 03 | d | Não está no catálogo. |
| G2i | 03 | b | Catálogo: `G2i` — só `careers` (backlog). |
| Turing | 03 | d | Não está no catálogo. |
| Proxify | 03 | b | Catálogo: `Proxify` — só `careers`. |
| BEON.tech | 03 | d | Não está no catálogo. |
| VanHack | 03 | d | Não está no catálogo. |
| Gun.io | 03 | d | Não está no catálogo. |
| CloudDevs | 03 | d | Não está no catálogo. |
| Arc | 03 | d | Não está no catálogo. |
| Andela | 03 | d | Não está no catálogo. |
| Lemon.io | 03 | d | Não está no catálogo. |
| Toptal | 03 | b | Catálogo: `Toptal` — só `careers`. |
| Terminal | 03 | d | Não está no catálogo. |
| Scopic | 03 | d | Não está no catálogo; ATS não identificado no Notion. |
| Azumo | 03 | d | Não está no catálogo. **ATS confirmado por sondagem real 2026-09-28:** Workable (`apply.workable.com/api/v1/widget/accounts/azumo`), HTTP 200. |
| Crossover | 03 | d | Não está no catálogo. |
| Nubank | 04 | a | Fonte habilitada `Nubank (Ashby)`, vinculada em `company_source`. |
| VTEX | 04 | d | Não está no catálogo. |
| Wellhub | 04 | b | Catálogo: `Wellhub` — só `careers` (backlog). |
| Hotmart | 04 | b | Catálogo: `Hotmart` — só `careers` (backlog). |
| EBANX | 04 | d | Não está no catálogo. **ATS confirmado por sondagem real 2026-09-28:** Greenhouse (`boards-api.greenhouse.io/v1/boards/ebanx`), HTTP 200 com vagas. |
| Pipefy | 04 | d | Não está no catálogo. |
| CI&T | 04 | a | Fonte habilitada `CI&T (Lever)`, vinculada em `company_source`. |
| BossaBox | 04 | d | Não está no catálogo. |
| DB (antiga DBServer) | 04 | d | Não está no catálogo. ATS é Gupy (`db.gupy.io`); fechado desde F20-32, não sondar. |
| CESAR | 04 | d | Não está no catálogo. ATS é Breezy HR (`cesar.breezy.hr`); não há coletor Breezy no projeto — não sondado. |
| Zup | 04 | d | Não está no catálogo. **ATS confirmado por sondagem real 2026-09-28:** Greenhouse (`boards-api.greenhouse.io/v1/boards/zupinnovation`), HTTP 200 com vagas. |
| AI/R — Avenue Code | 04 | d | Não está no catálogo. |
| Stefanini | 04 | d | Não está no catálogo. |
| FCamara | 04 | d | Não está no catálogo. ATS é Gupy (`fcamara.gupy.io`); fechado desde F20-32, não sondar. |
| NAVA | 04 | d | Não está no catálogo. |
| act digital | 04 | d | Não está no catálogo. |
| Revelo | 04 | b | Catálogo: `Revelo` — só `careers` (backlog). |
| Serasa Experian | 04 | d | Não está no catálogo. |
| Grupo OLX | 04 | d | Não está no catálogo. |

## Sondagens reais feitas nesta sessão

Uma requisição por candidato, com `User-Agent` identificável, direto no endpoint
público do próprio ATS (nunca no site institucional da empresa), com pausa entre
chamadas. Nenhuma delas ativou fonte nem inseriu empresa.

| Empresa | ATS | Endpoint sondado | Resultado |
| --- | --- | --- | --- |
| Loadsmart | Lever | `https://api.lever.co/v0/postings/loadsmart?mode=json` | HTTP 200, JSON com vagas reais. |
| Zup | Greenhouse | `https://boards-api.greenhouse.io/v1/boards/zupinnovation/jobs` | HTTP 200, JSON com vagas reais. |
| EBANX | Greenhouse | `https://boards-api.greenhouse.io/v1/boards/ebanx/jobs` | HTTP 200, JSON com vagas reais. |
| Devsu | Workable | `https://apply.workable.com/api/v1/widget/accounts/devsu?details=true` | HTTP 200, conta ativa. |
| Azumo | Workable | `https://apply.workable.com/api/v1/widget/accounts/azumo?details=true` | HTTP 200, conta ativa. |

Gupy nunca foi sondado (DB, FCamara e o ATS real da Minsait o usam) — fechado por
Termos de Uso desde o F20-32. Red Hat (Workday) e CESAR (Breezy HR) não foram
sondados: Workday exige descoberta de tenant/site (não é uma sondagem barata de um
slug único) e não há coletor Breezy no projeto.

## Maiores lacunas

1. **Consultorias/redes internacionais grandes ausentes do catálogo** (classe d,
   28 de 44 no bloco 03): TECLA, FullStack, Encora, AgileEngine, Cognizant, TCS,
   Infosys, Wipro, IBM, Softtek, Strider, Remotebase, Braintrust, Turing, Andela,
   Toptal (este já está — ver tabela), Arc, Gun.io, VanHack, CloudDevs, Lemon.io,
   Terminal, Crossover, entre outras. A maioria não tem ATS identificável sem
   pesquisa adicional; não são o alvo mais barato de importar.
2. **5 fontes com ATS já identificado no catálogo mas desabilitadas** (classe c):
   Grafana Labs, TestGorilla, Customer.io, NTT DATA, Accenture — ativação é
   praticamente gratuita (só ligar `enabled=true` após revisão de termos), sem
   pesquisa nova.
3. **5 empresas brasileiras/estrangeiras com ATS confirmado por sondagem real nesta
   sessão e prontas para importar**: Loadsmart (Lever), Zup (Greenhouse), EBANX
   (Greenhouse), Devsu (Workable), Azumo (Workable).
4. **Bloqueio de política, não de esforço:** Minsait, DB e FCamara têm ATS
   conhecido (Gupy), mas o F20-32 fechou Gupy por Termos de Uso — continuam fora
   de alcance por decisão já tomada, não por lacuna de descoberta.

## Resultados da execução (F20-60, 2026-09-28)

Card materializado na `f20manual` (`docker exec f20manual-*`, API em `127.0.0.1:8001`).
Nenhuma mudança em `probe_direct_ats`, coletores ou schema — só `CompanyService.reconcile`,
o mesmo padrão de `import_research_catalog.register_researched_collectors` para criar
`SourceDefinitionModel` desabilitadas, e os scripts existentes (`enable_sources.py`,
`collect.py`, `discover_ats.py`, `discover_sites.py`) para probar/habilitar/coletar.

### 1. As 5 fontes classe (c) — resolvidas e habilitadas

Nenhuma delas tinha de fato uma `SourceDefinitionModel`: `ats_identified` só registrava o
ATS, sem `external_key`/endpoint resolvido (`register_researched_collectors` também nunca
cobriu `workday`). Uma sondagem real por candidato resolveu a chave; termos já revisados
em nível de coletor (`docs/pesquisas/termos-workday.md`, mesma régua do F20-28/F20-30) —
nenhuma é Gupy, nenhuma nova revisão de termos era necessária.

| Empresa | ATS | Chave resolvida | Sondagem | Habilitada | Coleta real |
| --- | --- | --- | --- | --- | --- |
| Grafana Labs | Greenhouse | `grafanalabs` | `boards-api.greenhouse.io/v1/boards/grafanalabs/jobs` → 200, 134 vagas | sim | `SUCCEEDED`, 134 itens |
| TestGorilla | Ashby | `testgorilla` | `api.ashbyhq.com/posting-api/job-board/testgorilla` → 200 | sim | `SUCCEEDED`, 3 itens |
| Customer.io | Greenhouse | `customerio` | `boards-api.greenhouse.io/v1/boards/customerio/jobs` → 200, 27 vagas | sim | `SUCCEEDED`, 27 itens |
| NTT DATA | Workday | `nttglobaldatacenters/External`, pod `wd501` | tenant achado na própria careers page (`careers.nttdata.com` → `myworkdayjobs.com`), `POST /wday/cxs/.../jobs` → 200 | sim | `SUCCEEDED`, 224 itens |
| Accenture | Workday | `accenture/AccentureCareers`, pod `wd103` | idem (`accenture.com/us-en/careers` → `myworkdayjobs.com`), `POST /wday/cxs/.../jobs` → 200 | sim | `PARTIAL` — 1997 itens persistidos, `PARSER_SCHEMA_CHANGED` (paginação Workday repetiu página sem avançar; board grande, achado pré-existente do coletor, fora do escopo deste card) |

### 2. As 5 empresas confirmadas por sondagem — importadas e habilitadas

Importadas via `CompanyService.reconcile` (`company_id` novo cada uma), fonte real
adicionada com `verification_status=api_json_confirmed`, `SourceDefinitionModel` criada
desabilitada e depois habilitada por `enable_sources.py --accept-terms` (probe `PASSED`
para as 5). `collect.py` uma vez cada: todas `SUCCEEDED`.

| Empresa | ATS | Chave | Coleta real |
| --- | --- | --- | --- |
| Loadsmart | Lever | `loadsmart` | 17 itens |
| Zup | Greenhouse | `zupinnovation` | 3 itens |
| EBANX | Greenhouse | `ebanx` | 36 itens |
| Devsu | Workable | `devsu` | 29 itens |
| Azumo | Workable | `azumo` | 62 itens |

### 3. As ~45 empresas classe (d) sem ATS — importadas e sondadas com a descoberta nova

Excluídas deste lote (por decisão, não por esforço): DB e FCamara (ATS real Gupy, fechado
pelo F20-32 — nunca sondadas); CESAR (Breezy HR, sem coletor no projeto — não sondada);
Red Hat (tratada em separado abaixo, já tinha ATS citado no Notion). Restaram 42
empresas, importadas via `CompanyService.reconcile` com nome + site oficial (conhecimento
público; alguns palpites de URL de carreiras marcados como incerteza abaixo).

**Confirmação da página de carreiras** (uma requisição real por candidato, antes de
qualquer descoberta — `eligible_companies` exige `careers_confirmed`): 22 de 42
responderam HTTP < 400 e foram marcadas `careers_confirmed`; as outras 20 ficaram
`radar_status=backlog` (site indisponível, bloqueio de bot, ou URL de carreiras chutada
incorretamente — ver Incerteza).

**`scripts/discover_ats.py --concurrency 8`** (sondagem direta por slug antes de bater na
própria careers page) sobre as 22 elegíveis: 9 boards populados achados, ATS com coletor
no projeto — nenhum Gupy.

| Empresa | ATS achado | Chave | Habilitada | Coleta real |
| --- | --- | --- | --- | --- |
| Andela | Ashby | `andela` | sim | `SUCCEEDED`, 15 itens |
| Bluelight Consulting | Lever | `bluelightconsulting` | sim | `SUCCEEDED`, 1523 itens |
| Braintrust | Ashby | `braintrust` | sim | `SUCCEEDED`, 26 itens |
| LiteLLM | Ashby | `litellm` | sim | `SUCCEEDED`, 10 itens |
| Percona | Ashby | `percona` | sim | `SUCCEEDED`, 16 itens |
| Roboflow | Ashby | `roboflow` | sim | `SUCCEEDED`, 35 itens |
| Rollstack | Ashby | `rollstack` | sim | `SUCCEEDED`, 3 itens |
| Turing | Greenhouse | `turing` | sim | `SUCCEEDED`, 32 itens |
| VTEX | Greenhouse | `vtex` | sim | `SUCCEEDED`, 28 itens |

As outras 13 elegíveis (CloudDevs, BossaBox, IBM, Crossover, Encora, BEON.tech, Pipefy,
Serasa Experian, VanHack, Softtek, Scopic, NAVA, Wipro) não tiveram ATS achado por
`discover_ats.py`. **`scripts/discover_sites.py` não pôde rodar sobre elas no mesmo dia**:
as duas ferramentas compartilham o mesmo portão de novidade (`companies.discovery.
eligible_companies`, F20-27) — uma empresa já sondada por qualquer uma das duas fica fora
de `eligible_companies` por 30 dias. Isso é a proteção de gentileza do projeto (SPEC 43)
funcionando como desenhado, não um bug do script; para dar a `discover_sites.py` sua
chance de descoberta em várias páginas, ele precisaria rodar primeiro (antes de
`discover_ats.py`) num lote futuro que ainda não tenha sido sondado neste ciclo de 30
dias.

**Red Hat**: ATS já citado no Notion (Workday), tenant não pesquisado na auditoria
original. Achado nesta sessão por uma sondagem barata (uma requisição na própria careers
page): `redhat.com/en/jobs` → link para `redhat.wd5.myworkdayjobs.com`; `POST
/wday/cxs/redhat/jobs/jobs` → 200, vagas reais. Importado, fonte habilitada, coleta real:
`SUCCEEDED`, 151 itens.

### 4. Contagens finais na `f20manual`

| Métrica | Antes do F20-60 | Depois |
| --- | --- | --- |
| `company_radar.company` | 223 | 271 (+48: 5 confirmadas + Red Hat + 42 classe (d)) |
| `acquisition.source_definition` — total | 74 | 94 (+20) |
| `acquisition.source_definition` — habilitadas | 67 | 87 (+20) |
| `acquisition.source_definition` — desabilitadas | 7 (fixtures de teste antigas, não deste card) | 7 (mesmas, intocadas) |

Nenhuma fonte Gupy foi sondada, coletada ou habilitada. Nenhuma alteração em
`probe_direct_ats`, coletores existentes ou schema do catálogo. Testes:
`pytest tests/backend/companies tests/backend/acquisition` — 296 passed, 62 skipped
(projeto Compose isolado `f20-60-verify`, código do worktree, sem rebuild de imagem
salvo o necessário; stack derrubada ao final).

### Pendente para a pilha real

As 20 fontes novas (10 classe c/confirmadas + 10 descoberta nova) só existem na
`f20manual`. Ativação em `opportunity-radar` fica para depois da janela de sete dias —
ver `docs/44-roadmap-fase-20/validacao-pendente.md` §4.6.

## Incerteza

- A extração de nomes do Notion foi manual (leitura completa das 1358 linhas);
  pode haver variação de grafia não capturada pela normalização simples usada
  aqui (ex.: "TCS" vs. "Tata Consultancy Services").
- **Resolvido pelo F20-60** (seção "Resultados da execução" acima): as ~45 empresas
  classe (d) foram importadas e sondadas com `discover_ats.py`/`discover_sites.py`; Red
  Hat teve o tenant Workday achado por uma sondagem barata na própria careers page.
- URLs de careers page para as 42 empresas classe (d) foram um palpite de conhecimento
  público (nome da empresa + `/careers` ou variação comum), não pesquisado individualmente
  — daí 20 delas terem ficado `radar_status=backlog` (site não respondeu 200, bloqueio de
  bot corporativo, ou o palpite de URL estava errado). Casos a destacar: "Mercado Livre"
  usou o domínio corporativo `mercadolibre.com`, que falhou por DNS — o domínio brasileiro
  correto pode ser outro; "AI/R — Avenue Code" redirecionou para um domínio (`aircompany.ai`)
  que não parece ser da mesma empresa — o palpite de domínio (`avenuecode.com`) está
  provavelmente errado; "NAVA" é ambíguo (pode ser a NAVA brasileira ou a "Nava" americana
  de saúde, `nava.pbc`) — usei `nava.com.br` sem confirmar qual é a empresa do mapa de
  carreira. Nenhuma dessas 20 teve fonte criada além do registro `careers` não confirmado;
  nenhuma foi sondada além da própria página (nunca o endpoint de nenhum ATS).
- `discover_sites.py` não rodou sobre as 13 empresas que ficaram sem ATS em
  `discover_ats.py` (mesmo dia, mesmo portão de novidade de 30 dias — ver seção 3 acima).
  Falta real, não fechada por este card: rodar `discover_sites.py` primeiro, em outro
  dia, para essas 13 (CloudDevs, BossaBox, IBM, Crossover, Encora, BEON.tech, Pipefy,
  Serasa Experian, VanHack, Softtek, Scopic, NAVA, Wipro) e para as 20 sem careers page
  confirmada, depois de pesquisar a URL de carreiras real de cada uma.
- Accenture: coleta `PARTIAL` (1997 itens reais, mas o coletor Workday parou por
  `PARSER_SCHEMA_CHANGED` — paginação repetiu página sem avançar num board muito grande).
  Evidência real já satisfaz o critério de aceite ("pelo menos um item real coletado"),
  mas o board não foi coletado por completo; investigar o coletor Workday para boards
  grandes é trabalho de outro card (não tocado aqui — "Não fazer" veda mudar coletores).
