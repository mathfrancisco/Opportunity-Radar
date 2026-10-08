# Fila `REVIEW_REQUIRED`: proposta de regra por motivo (2026-10-07)

Proposta para decisão do dono. **Nada foi resolvido nem fundido**: as consultas abaixo só
leem a base de dev. Continua o registro da [SPEC 52 §5](../52-spec-aderencia-ao-nivel.md) e
da amostra [fila-review-required-amostra-2026-10-07.json](fila-review-required-amostra-2026-10-07.json).

## Estado medido

Medido em 2026-10-07, 13:52 UTC: **1222 linhas** em `opportunities.normalization_result`
com `status = 'REVIEW_REQUIRED'`. Eram 1.152 no fim do lote de 4.455; a fila cresce com a
coleta (152 linhas com data de 2026-10-07, 164 de 2026-10-06). Uma regra aplicada só em lote
não esvazia a fila: ela precisa entrar no normalizador, o que é mudança de código.

| Padrão | Linhas | Fontes |
|---|---:|---|
| A1. Mesmo título e empresa; candidatas na mesma fonte, com outro `external_id`, mesmo local e mesmo modo | 231 | Workday 168, inHire 32, Hacker News 18, Ashby 10, Lever 2, Teamtailor 1 |
| A2. Idem; difere de parte das candidatas e empata ou não tem local contra as outras | 92 | Workday 71, Teamtailor 13, inHire 6, Ashby 2 |
| A3. Idem; local desconhecido em um dos lados | 282 | Workday 242, Workable 38, Hacker News 2 |
| A0. Idem; todas as candidatas diferem em local ou modo (o padrão já aprovado) | 1 | Workday 1 |
| B1. `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`, sem vaga concorrente gravada (linhas até 2026-10-05) | 503 | Ashby 287, Lever 190, Workday 15, Greenhouse 11 |
| B2. `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`, com vaga concorrente gravada | 89 | Workday 86, Greenhouse 3 |
| C. Identidade já decidida (`MERGED` ou `REFRESHED`), retida por `CONFLICTING_COMPENSATION_EVIDENCE` | 24 | Greenhouse 19, Ashby 4, Workable 1 |

Em todas as 606 linhas do grupo A, **todas as candidatas estão na
mesma fonte, com outro `external_id`**. Nenhuma tem candidata em outra fonte.

## Propostas

### A. `SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY` (606 linhas)

**Regra proposta:** quando todas as candidatas estão na mesma fonte com outro `external_id`,
a linha vira `SUCCEEDED`/`NEW` com o motivo `REVIEW_RESOLVED_DISTINCT_POSTING`, sem exigir
local ou modo diferente. É a regra já aprovada sem a segunda condição. Motivo: a própria
fonte lista as duas como publicações separadas, com identificadores separados; o produto não
tem como saber que são a mesma vaga, e a decisão de não fundir automaticamente continua
valendo. Nenhuma vaga, ocorrência ou vínculo de duplicata muda.

**Exceção proposta: Hacker News (20 linhas).** Lá o `external_id` é o comentário do mês, e a
mesma empresa repete o anúncio a cada thread. Marcar como `NEW` cria uma vaga por mês. Para
essas, a proposta é deixar na fila até existir regra de republicação mensal.

**Risco:** vagas repetidas no Inbox quando a empresa publica a mesma vaga duas vezes (A1).
Quem decide se quer vê-las separadas é o dono.

**Achado ao lado, não é regra:** as 242 linhas Workday do A3 são quase todas da Accenture,
cujas vagas chegam sem local, embora o `external_id` traga a cidade
(`/job/Bengaluru/...`). Corrigir isso é mudança de coletor (SPEC 51) e não foi feito.

A1, mesmo local e modo:

| Fonte | Empresa | Título | Local / modo | `external_id` | Candidatas (local / modo) |
|---|---|---|---|---|---|
| OpenAI (Ashby) | OpenAI | Strategic Sourcing Leader, Professional Services | san francisco / HYBRID | `ashby:78e55050abc237a3a1dcc8e5f9ff550fc71a6c3dc…` | 1: san francisco/HYBRID |
| Abbott (workday) | Abbott | MitraClip Specialist I | united states - indiana - westfield / UNKNOWN | `/job/United-States---Indiana---Westfield/MitraC…` | 2: united states - indiana - westfield/UNKNOWN |
| NVIDIA (Workday) | NVIDIA | Senior C++ Software Engineer – AI Developer Tools | israel, tel aviv / UNKNOWN | `/job/Israel-Tel-Aviv/Senior-C---Software-Engine…` | 1: israel, tel aviv/UNKNOWN |
| Abbott (workday) | Abbott | Electrical Engineer | united states - massachusetts - westford / UNKNOWN | `/job/United-States---Massachusetts---Westford/E…` | 1: united states - massachusetts - westford/UNKNOWN |
| Proposed Infobip workday | Infobip | Mid Market Account Executive (Platforms) | 4 locations / UNKNOWN | `/job/Vodnjan-Croatia/Mid-Market-Account-Executi…` | 1: 4 locations/UNKNOWN |
| Abbott (workday) | Abbott | CONSULTOR | peru - lima / UNKNOWN | `/job/Peru---Lima/CONSULTOR_31154036` | 1: peru - lima/UNKNOWN |
| Santander (Workday) | Santander | Asesor  Oper y Proc | ofna edificio distrito qro / UNKNOWN | `/job/OFNA-EDIFICIO-DISTRITO-QRO/Asesor--Oper-y-…` | 1: ofna edificio distrito qro/UNKNOWN |
| Abbott (workday) | Abbott | SW Test Engineer II | india - mumbai / UNKNOWN | `/job/India---Mumbai/SW-Test-Engineer-II_31163307` | 1: india - mumbai/UNKNOWN |
| Proposed nstech inhire | nstech | Auxiliar de Operações - Paulínia/SP | paulínia, sp, br / ONSITE | `d1643aeb-b218-4f6f-a726-95ec34a1d35b` | 1: paulínia, sp, br/ONSITE |
| Proposed BRQ inhire | BRQ | Desenvolvedor (a) .NET e AWS Pleno - Híbrido/SP | são paulo, sp, br / HYBRID | `85712f1c-abaf-4bee-8c76-a65130437b04` | 1: são paulo, sp, br/HYBRID |

A2, difere de parte das candidatas:

| Fonte | Empresa | Título | Local / modo | `external_id` | Candidatas (local / modo) |
|---|---|---|---|---|---|
| Abbott (workday) | Abbott | Operator I | united states - minnesota - plymouth / UNKNOWN | `/job/United-States---Minnesota---Plymouth/Opera…` | 5: united states - california - pleasanton/UNKNOWN ; united states - minnesota - minnetonka/… |
| Leroy Merlin Brasil (teamtailor) | Leroy Merlin Brasil | Operador(a) de Loja | são paulo, regional são paulo, br / UNKNOWN | `53bf3356-0be5-49ad-89d1-9643a74659a5` | 5: barueri, regional são paulo, br/UNKNOWN ; londrina, regional sul, br/UNKNOWN ; sorocaba, … |
| Chanel (workday) | Chanel | Skincare Therapist | victoria / UNKNOWN | `/job/Victoria/Skincare-Therapist_JOBREQ00116795` | 3: ?/UNKNOWN ; hong kong s.a.r./UNKNOWN ; petaling jaya/UNKNOWN |
| Santander (Workday) | Santander | MEX Cajero Sucursal | 2 locations / UNKNOWN | `/job/Mrida/MEX-Cajero-Sucursal_Req1549906-1` | 5: 2 locations/UNKNOWN ; 3 locations/UNKNOWN ; 4 locations/UNKNOWN ; 5 locations/UNKNOWN ; x… |
| Leroy Merlin Brasil (teamtailor) | Leroy Merlin Brasil | Operador(a) de Logística | são paulo, regional são paulo, br / UNKNOWN | `62606c3e-8149-4d55-a470-52123ff7d08f` | 5: curitiba, regional sul, br/UNKNOWN ; porto alegre, regional sul, br/UNKNOWN ; são josé do… |
| NVIDIA (Workday) | NVIDIA | Developer Technology Engineer – AI | 3 locations / UNKNOWN | `/job/China-Shanghai/Developer-Technology-Engine…` | 2: 3 locations/UNKNOWN ; korea, seoul/UNKNOWN |
| Leroy Merlin Brasil (teamtailor) | Leroy Merlin Brasil | Fiscal de Caixa | são paulo, regional são paulo, br / UNKNOWN | `e65fb80d-6b1d-4a59-be33-d8330a6a09b4` | 2: bauru, regional interior são paulo, br/UNKNOWN ; são paulo, regional são paulo, br/UNKNOWN |
| Obramax (teamtailor) | Obramax | Vendedor Pleno - Cerâmica | brasília, br / UNKNOWN | `b9f6bc74-3710-4bc6-a87d-5c8ab796b87c` | 2: brasília, br/UNKNOWN ; várzea grande, br/UNKNOWN |
| NVIDIA (Workday) | NVIDIA | Senior Software Engineer - Networking | us, ca, santa clara / UNKNOWN | `/job/US-CA-Santa-Clara/Senior-Software-Embedded…` | 2: israel, raanana/UNKNOWN ; us, ca, santa clara/UNKNOWN |
| ERM (workday) | ERM | EHS Manager (Field Based) | 2 locations / UNKNOWN | `/job/Cincinnati-Ohio/EHS-Manager--Field-Based-_…` | 3: 2 locations/UNKNOWN ; 7 locations/UNKNOWN ; indianapolis, indiana/UNKNOWN |

A3, local desconhecido:

| Fonte | Empresa | Título | Local / modo | `external_id` | Candidatas (local / modo) |
|---|---|---|---|---|---|
| Accenture jobs | Accenture | Engineering Services Practitioner | ? / UNKNOWN | `/job/Bengaluru/Engineering-Services-Practitione…` | 1: ?/UNKNOWN |
| Proposed Weekday workable | Weekday | Radiology Expert | ? / UNKNOWN | `22CDEAD666` | 1: ?/UNKNOWN |
| Accenture jobs | Accenture | AI / ML Engineer | ? / UNKNOWN | `/job/Lisbon-Amoreiras-Square/AI---ML-Engineer_1…` | 1: ?/UNKNOWN |
| Accenture jobs | Accenture | Functional and Industry Intelligence Associate Director | ? / UNKNOWN | `/job/Hyderabad/Offering-Dev-Associate-Director_…` | 1: ?/UNKNOWN |
| Accenture jobs | Accenture | Delivery Operations Senior Analyst | ? / UNKNOWN | `/job/Bengaluru/Delivery-Operations-Team-Lead_AI…` | 2: ?/UNKNOWN |
| Accenture jobs | Accenture | SAP SuccessFactors Consultant | ? / UNKNOWN | `/job/Malaga/SAP-SuccessFactors-Consultant_R0036…` | 1: ?/UNKNOWN |
| Accenture jobs | Accenture | Infra Tech Support Practitioner | ? / UNKNOWN | `/job/Bengaluru/Infra-Tech-Support-Practitioner_…` | 3: ?/UNKNOWN |
| Accenture jobs | Accenture | Intellectual Property Counsel | ? / UNKNOWN | `/job/Bengaluru/Intellectual-Property-Counsel_R0…` | 1: ?/UNKNOWN |
| Accenture jobs | Accenture | Test Automation Engineer | ? / UNKNOWN | `/job/Bengaluru/Test-Automation-Engineer_ATCI-57…` | 3: ?/UNKNOWN |
| Accenture jobs | Accenture | Senior ServiceNow Developer | ? / UNKNOWN | `/job/Sofia/Senior-ServiceNow-Developer_R00356239` | 1: ?/UNKNOWN |

A0, o único caso novo do padrão já aprovado (`resolve_review_queue.py --apply` o resolve):

| Fonte | Empresa | Título | Local / modo | `external_id` | Candidatas (local / modo) |
|---|---|---|---|---|---|
| Procter & Gamble (workday) | Procter & Gamble | Lagerist (m/w/d) | spittal a.d. drau / UNKNOWN | `/job/Spittal-AD-Drau/Lagerist--m-w-d-_R000158433` | 1: spittal a.d. drau plant/UNKNOWN |

### B. `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED` (592 linhas)

O mesmo `external_id` da mesma fonte chegou com outra identidade (título ou local editado na
origem).

**Regra proposta para B1 e parte de B2:** rodar `scripts/backfill_identity_refresh.py`, que
já existe para isso (card F48-09: a identidade passou a ser atualizada no lugar e as linhas
antigas só precisam ser normalizadas de novo). O `--dry-run` de 2026-10-07 lista **320
linhas** afetadas. A execução real apaga só essas linhas de resultado; a passada seguinte de
normalização as recria. A linha cuja identidade nova pertence a outra vaga volta para a fila,
agora com a concorrente gravada. Exige `pg_dump` antes.

**Regra proposta para o que sobrar com concorrente gravada (B2, hoje 89):** a
concorrente está na mesma fonte com outro `external_id` e tem título, empresa, local e modo
iguais em 86 das 89. É o caso A visto pelo outro lado (uma vaga mudou de título e passou a
coincidir com outra publicação). Mesma regra de A: manter separadas, `SUCCEEDED` sem fusão.

**Sem proposta:** as linhas de B1 que o backfill não alcança (o item bruto já não é o que
alimenta a ocorrência; 592 menos 320, a conferir depois da execução). Sugestão: marcar como
superadas, porque uma coleta mais nova da mesma vaga já foi normalizada.

B1, sem concorrente gravada:

| Fonte | Empresa | Título | Local / modo | `external_id` | Candidatas (local / modo) |
|---|---|---|---|---|---|
| CI&T jobs | CI&T | [Job-26705] Senior Data Engineer, Campinas, Brazil (Hybrid) | campinas, sp / HYBRID | `516abaa8-8dcf-4231-a98d-da9ee09f7ab6` | não gravadas |
| Nubank jobs | Nubank | Lead Product Designer - Lending | são paulo / UNKNOWN | `ashby:c6d2db2acd33f346328e78c3624032af1814ae5a2…` | não gravadas |
| CI&T jobs | CI&T | [Job-30904] Mid level Java Developer, Brazil | brazil / REMOTE | `418f5dc8-275b-4434-be0d-c401d234cf75` | não gravadas |
| CI&T jobs | CI&T | [Job-0008] Senior Salesforce Developer, Brazil | brazil / REMOTE | `e539d765-5a57-4fb6-bbbc-6eca301cbc6f` | não gravadas |
| Nubank jobs | Nubank | Senior Software Engineer - Buenos Aires, Argentina (Hybrid) | buenos aires / UNKNOWN | `ashby:0877a2aafc48f3f86e4961bae24e27a824d410153…` | não gravadas |
| CI&T jobs | CI&T | [Job -  30900] Master Data Developer (Amazon Neptune), Colombia | colombia / REMOTE | `b51b1a14-b9cd-4f45-b732-595936ed8a61` | não gravadas |
| CI&T jobs | CI&T | [Job- 31929] - QA Automation Tester | brazil / REMOTE | `7754c754-1a88-44d7-8a25-ba034cafc07e` | não gravadas |
| Nubank jobs | Nubank | Staff Software Engineer - Lending Foundations (Policy & Data Platform) | são paulo / UNKNOWN | `ashby:089dd03eb33b61a5a79fc85b5680ccc9e17dd76dd…` | não gravadas |
| CI&T jobs | CI&T | [Job -  30900] Master Data Developer, Brazil | brazil / REMOTE | `51618054-a487-4ffe-a60f-78392ad250d0` | não gravadas |
| Nubank jobs | Nubank | Senior Staff Systems Engineer - Performance Engineer | miami / UNKNOWN | `ashby:0e8411589e6eef810c466dab8084ef86cbddccbc4…` | não gravadas |

B2, com concorrente gravada:

| Fonte | Empresa | Título | Local / modo | `external_id` | Vaga concorrente |
|---|---|---|---|---|---|
| Accenture jobs | Accenture | Custom Software Engineer | ? / UNKNOWN | `/job/Hyderabad/Custom-Software-Engineer_ATCI-54…` | Custom Software Engineer @ ? |
| Accenture jobs | Accenture | Custom Software Engineer | ? / UNKNOWN | `/job/Mumbai/Application-Lead_ATCI-4927568-S1852…` | Custom Software Engineer @ ? |
| Accenture jobs | Accenture | Custom Software Engineer | ? / UNKNOWN | `/job/Bengaluru/Custom-Software-Engineer_ATCI-57…` | Custom Software Engineer @ ? |
| AIG (workday) | AIG | Collections Supervisor | mexico city / UNKNOWN | `/job/Mexico-City/Collections-Supervisor_JR26017…` | Collections Supervisor @ mexico city |
| Accenture jobs | Accenture | Data Engineer | ? / UNKNOWN | `/job/Mumbai/Data-Engineer_ATCI-5392570-S1967863` | Data Engineer @ ? |
| Accenture jobs | Accenture | Technology Architect | ? / UNKNOWN | `/job/Bengaluru/Technology-Architect_ATCI-537609…` | Technology Architect @ ? |
| Accenture jobs | Accenture | Custom Software Engineer | ? / UNKNOWN | `/job/Bengaluru/Application-Developer_ATCI-52354…` | Custom Software Engineer @ ? |
| Accenture jobs | Accenture | Custom Software Engineer | ? / UNKNOWN | `/job/Mumbai/Custom-Software-Engineer_ATCI-56110…` | Custom Software Engineer @ ? |
| Abbott (workday) | Abbott | Instrumentation/Automation Service Engineer I | united states - wisconsin - madison / UNKNOWN | `/job/United-States---Wisconsin---Madison/Equipm…` | Instrumentation/Automation Service Engineer I @ united states - wisconsin - madison |
| Accenture jobs | Accenture | Application Support Engineer | ? / UNKNOWN | `/job/Mumbai/Application-Support-Engineer_ATCI-5…` | Application Support Engineer @ ? |

### C. Evidência de remuneração em conflito (24 linhas)

A identidade já foi decidida (`EXACT_VERSIONED_FINGERPRINT` 12, `SAME_SOURCE_EXTERNAL_IDENTITY`
8, `IDENTITY_REFRESHED_SAME_EXTERNAL_ID` 4). O que retém a linha é a remuneração: duas
ocorrências da mesma vaga trazem valores diferentes, e os valores lidos da descrição são em
boa parte lixo de extração (mínimo de `3273525928.00`, `1900000` por semana, `136` sem moeda).

**Regra proposta:** manter a decisão de identidade e fechar a linha como `SUCCEEDED`. Quando
uma das evidências é estruturada (por exemplo `ashby.compensation`), ela vence a da descrição;
quando as duas vêm da descrição, a remuneração da vaga fica desconhecida. Nenhuma fusão nova:
a fusão já aconteceu pela identidade.

| Fonte | Empresa | Título | Local / modo | `external_id` | Candidatas (local / modo) |
|---|---|---|---|---|---|
| Proposed Instawork greenhouse | Instawork | Field Operations Executive | bengaluru, karnataka, india / UNKNOWN | `4625772006` | não gravadas |
| MongoDB (Greenhouse) | MongoDB | Senior Enterprise Account Executive, Growth | san francisco / UNKNOWN | `8147923` | não gravadas |
| MongoDB (Greenhouse) | MongoDB | Senior Enterprise Account Executive, Growth | san francisco / UNKNOWN | `8147949` | não gravadas |
| Proposed Daybreak Health greenhouse | Daybreak Health | Remote Mental Health Therapist – LCSW/LPCC/LMFT/LP (1099, California) | california (remote) / REMOTE | `5211902007` | não gravadas |
| Proposed Daybreak Health greenhouse | Daybreak Health | Remote Mental Health Therapist – LCSW/LPCC/LMFT/LP (1099, California) | california (remote) / REMOTE | `5206102007` | não gravadas |
| MongoDB (Greenhouse) | MongoDB | Senior Manager, Financial Planning & Analysis | austin; new york city / UNKNOWN | `8154864` | não gravadas |
| Proposed Daybreak Health greenhouse | Daybreak Health | Remote Mental Health Therapist – LCSW/LPCC/LMFT/LP (1099, California) | california (remote) / REMOTE | `5242914007` | não gravadas |
| Proposed Daybreak Health greenhouse | Daybreak Health | Remote Mental Health Therapist – LCSW/LPCC/LMFT/LP (1099, California) | california (remote) / REMOTE | `5211879007` | não gravadas |
| Proposed Weekday workable | Weekday | DevOps Engineer | ? / UNKNOWN | `E1AD11D35C` | não gravadas |
| Databricks (Greenhouse) | Databricks | Staff Software Engineer - AI Research Infrastructure | new york city, new york; san francisco, cali… / UNKNOWN | `8532682002` | não gravadas |

## O que cada decisão custa

| Decisão | Linhas | O que roda | Mudança de código |
|---|---:|---|---|
| A, sem Hacker News | 586 | `resolve_review_queue.py` com a condição relaxada | No script (SPEC 52). Para a fila parar de crescer, também no normalizador |
| B, backfill | 320 | `backfill_identity_refresh.py`, depois a normalização | Nenhuma |
| B2, restante | cerca de 89 | o mesmo script de A | No script |
| C | 24 | script novo, pequeno | Script novo; regra de precedência no normalizador |

Consultas usadas: classificação por padrão em `normalization_result.reasons`, com os
candidatos de `candidate_opportunity_ids` e `competing_opportunity_id` comparados à vaga da
linha por fonte, `external_id`, `normalized_location` e `work_mode`. Dez exemplos por padrão,
ordenados por `md5(id)`.
