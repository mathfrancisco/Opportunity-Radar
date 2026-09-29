# Evidência — sondagem de boards de early careers/university separados (F20-71, 2026-09-29)

- **Card:** [F20-71](../fase-20/f20-71-boards-early-careers-separados.md)
- **Base:** `f20manual` (container `f20manual-postgres-1`, banco `opportunity_radar`), API em
  `127.0.0.1:8001`. Nenhuma escrita nesta base além de leituras de contagem — nenhum
  código, migração ou fixture alterado nesta sessão.
- **Restrição respeitada:** nenhuma empresa da lista em coleta pelo outro worker do F20-60
  (Loadsmart, Zup, EBANX, Devsu, Azumo, Grafana, TestGorilla, Customer.io, NTT DATA,
  Accenture e demais do mapa de carreira) foi sondada, tocada ou consultada nesta sessão.
  Enquanto esta sessão rodava, o número de fontes habilitadas na `f20manual` subiu de 67
  para 77 por conta desse outro worker — não é resultado deste card.

## 1. Método

Sondagem direta (1 requisição por candidato, endpoint público do próprio ATS, nunca o
site institucional da empresa), mesma régua do F20-27/F20-36/F20-60
(`probe_direct_ats`/`limited_discovery.py`): pausa de 1s entre requisições, sem crawling
de HTML, sem login, `User-Agent` próprio do projeto
(`OpportunityRadarDiscoveryBot/1.0`). Scripts pontuais no scratchpad da sessão (não
commitados — nenhum código de produção foi necessário, nenhum board populado foi
encontrado para justificar uma mudança em `scripts/`/`src/`).

Cobertas as empresas citadas na tarefa (Nubank, Stripe, Datadog, Adobe, Spotify, CI&T) e,
para ampliar a chance de achado sem tocar a lista do F20-60, duas empresas adicionais do
catálogo com programa de trainee/graduate publicamente conhecido e ATS já
identificado — Santander (Workday) e NVIDIA (Workday) — nenhuma das duas na lista
protegida.

Uso de Tavily (permitido dentro do orçamento F20-43): 2 buscas `tvly search --json
--max-results 5` (profundidade `basic`), custo estimado 2 créditos no total (1 crédito
por busca `basic`, típico do plano Tavily; não há endpoint de saldo neste `tvly` para
confirmar o número exato). Só para confirmar nome de board/aplicação pública, nunca para
raspar conteúdo de vaga.

## 2. Resultado por empresa

| Empresa | ATS do board principal já coletado | Board(s) de early-careers sondados | Resultado |
| --- | --- | --- | --- |
| Nubank | Ashby (`nubank`, 119 vagas, 0 JUNIOR/INTERN) | Ashby: 9 slugs derivados (`nubank-university`, `nubankuniversity`, `nubank-jovens`, `nubank-trainee`, `nubank-early-careers`, `nubankearlycareers`, `nubank-campus`, `nubank-graduates`, `nubank-formacao`) — todos HTTP 404. **Achado real via busca:** Nubank também tem um board **Greenhouse** ativo (`job-boards.greenhouse.io/nubank`), distinto do board Ashby já coletado — confirmado por sondagem direta em `boards-api.greenhouse.io/v1/boards/nubank/jobs` (HTTP 200) | Board Greenhouse existe e é diferente do Ashby já coletado, mas **0 vagas no momento da sondagem** (`{"jobs": []}`) — não passa o critério "confirmado e populado" do card. Registrado para revisita futura, não habilitado agora. |
| Stripe | Greenhouse (`stripe`) | Greenhouse: 8 slugs (`stripeuniversity`, `stripe-university`, `stripeearlycareers`, `stripe-early-careers`, `stripecampus`, `stripe-campus`, `stripeinternship`, `stripe-internship`) — todos HTTP 404 | Não encontrado |
| Datadog | Greenhouse (`datadog`) | Greenhouse: 8 slugs (`datadoguniversity`, `datadog-university`, `datadogearlycareers`, `datadog-early-careers`, `datadogcampus`, `datadog-campus`, `datadoginternship`, `datadog-internship`) — todos HTTP 404 | Não encontrado |
| CI&T | Lever (`ciandt`) | Lever: 7 slugs (`ciandt-university`, `ciandt-trainee`, `ciandt-jovens`, `ciandt-early-careers`, `ciandtjovens`, `ciandt-estagio`, `ciandt-graduates`) — todos HTTP 404 | Não encontrado |
| Spotify | Lever (`spotify`) | Lever: 5 slugs (`spotify-university`, `spotify-earlycareers`, `spotify-students`, `spotify-grad`, `spotify-internship`) — todos HTTP 404 | Não encontrado (Spotify já traz 2 INTERN pelo board principal, ver diagnóstico de origem) |
| Adobe | Workday (`adobe/external_experienced`, pod `wd5`) | Workday: 11 `Job_Posting_Site_ID` (`university`, `External_Career_Site_University`, `ExternalCareerSiteUniversity`, `students`, `campus`, `earlycareer`, `early_career`, `universityrecruiting`, `Adobe_University`, `ExternalCareerSite-University`, `external_university`) | 10 de 11 com erro Workday `S21` ("not found", site realmente não existe). **`external_university` retornou HTTP 403 com erro Workday `S22` ("permission denied")** — o site existe no tenant, mas não é um board público de candidato (provavelmente site interno/referral); não coletável, não conta como achado válido. |
| Santander | Workday (`santander/SantanderCareers`, pod `wd3`) | Workday: 9 `Job_Posting_Site_ID` (`SantanderGraduates`, `SantanderUniversity`, `Santander_Graduates`, `SantanderTrainee`, `Trainee`, `University`, `SantanderCareersUniversity`, `SantanderUniversidades`, `Graduates`) — todos erro `S21` "not found" | Não encontrado |
| NVIDIA | Workday (`nvidia/NVIDIAExternalCareerSite`, pod `wd5`) | Workday: 8 `Job_Posting_Site_ID` (`NVIDIAUniversityRecruiting`, `NVIDIAExternalUniversity`, `University`, `UniversityRecruiting`, `NVIDIAUniversity`, `NVIDIAGraduates`, `NVIDIAInternships`, `NVIDIAEarlyCareers`) — todos erro `S21` "not found" | Não encontrado |

Total: 8 empresas pesquisadas e sondadas com sondagem real (acima do mínimo de 3 do
critério de aceite), 65 requisições HTTP diretas a APIs de ATS, 0 boards confirmados e
populados.

## 3. Por que nenhum board foi habilitado

O critério de aceite do card e a regra "não fazer" exigem board **confirmado e
populado** antes de qualquer `source_definition`/`enabled=true`. Nesta rodada:

- A maioria dos slugs candidatos (nomes plausíveis de board de university/early-careers)
  não existe nos ATS sondados — erro genuíno de "não encontrado" (`404`/Workday `S21`),
  não um bloqueio de acesso.
- Um caso (Adobe `external_university`) existe mas está fechado por permissão
  (Workday `S22`) — não é um board público de candidato, mesmo tratamento que o card dá a
  qualquer endpoint que exija autenticação: não coletável.
- Um caso (Nubank Greenhouse) existe, é público e é um board diferente do já coletado,
  mas está vazio agora (`0` vagas) — não atende "populado". Registrado como achado real
  para o card revisitar depois, sem inventar coleta que a sondagem não confirmou.

Por isso: nenhum código foi escrito (nenhum arquivo em `src/opportunity_radar/acquisition/`
ou `scripts/` criado ou alterado), nenhuma `source_definition` nova foi criada via
`CompanyService.reconcile`/`scripts/import_research_catalog.py`, e `enable_sources.py
--probe-only` não foi executado contra candidatos porque nenhum board novo chegou a
existir como fonte a sondar por esse fluxo (a sondagem desta rodada foi direta contra a
API do ATS, não contra fontes já registradas no banco).

## 4. Métrica antes/depois

| Momento | JUNIOR | INTERN | Total oportunidades | JUNIOR+INTERN | % |
| --- | --- | --- | --- | --- | --- |
| Antes (diagnóstico de origem, 2026-09-28) | 5 | 13 | 2288 | 18 | 0,79% |
| Depois desta sondagem (2026-09-29, mesma base `f20manual`) | 5 | 13 | 2288 | 18 | 0,79% |

**Sem mudança.** Nenhuma fonte nova foi habilitada e nenhuma coleta foi executada para
este card — não havia board confirmado e populado para ativar. A contagem de 77 fontes
habilitadas observada na `f20manual` durante esta sessão vem do worker concorrente do
F20-60, não deste card.

## 5. Empresas avaliadas como "sem early-careers separado encontrado"

Por não fazer (regra do card): Stripe, Datadog, CI&T, Spotify, Santander e NVIDIA ficam
registradas como **avaliadas, sem board separado de early-careers encontrado** — não é
pendência aberta indefinidamente, é um resultado negativo real desta rodada de sondagem.
Nubank e Adobe ficam com um achado parcial (board existe, mas não coletável/não populado
hoje) documentado na tabela acima, também não como pendência aberta — uma futura
sondagem pode revisitar especificamente esses dois pontos (Nubank Greenhouse population,
e uma verificação institucional de qual sistema real processa o Programa de Estágio
Nubank/Adobe, fora do escopo de sondagem direta de ATS deste card).

## 6. Incertezas e limites

- A lista de slugs candidatos por empresa é heurística (nomes plausíveis em
  inglês/português); um board de early-careares real com um nome menos previsível
  (ex.: um código interno) não seria encontrado por esse método. Mitigado parcialmente
  por 2 buscas Tavily, mas não eliminado.
- Não foi possível confirmar o custo exato em créditos Tavily (`tvly` não expõe um
  comando de saldo/uso nesta instalação); a estimativa de 2 créditos assume o custo
  padrão de uma busca `basic`.
- Adobe/Santander/NVIDIA/Nubank/Stripe/Datadog têm múltiplos pods/tenants possíveis em
  teoria (Workday) ou múltiplas contas ATS por marca/subsidiária (Ashby/Greenhouse/Lever)
  que não foram exaustivamente sondados — a sondagem cobriu os pods/tenants já
  confirmados no catálogo (`api_region` da fonte existente), não uma busca de pod
  alternativo.
- Não foi executada nenhuma coleta real (`collect.py`) nesta sessão porque não havia
  fonte nova a coletar; a seção 4 usa a mesma leitura de banco do início e do fim da
  sessão para provar a ausência de mudança, não uma medição antes/depois de uma
  ativação real.

## Rodada 2 — descoberta por busca Tavily nos domínios de ATS (2026-09-29)

A rodada 1 (acima) adivinhou boards separados de empresas grandes e não achou nenhum.
A rodada 2 inverte o método, o mesmo do piloto F20-53 (`docs/pesquisas/descoberta-startups-ats.md`):
busca Tavily restrita aos domínios de ATS que o radar coleta, com termos de vaga
junior/estágio; do resultado tira-se o **board da empresa**, sonda-se a API real do ATS e
só se ativa board populado com pelo menos uma vaga JUNIOR/INTERN pelo título. Gupy nunca
consultado; nenhuma empresa protegida do F20-60 tocada.

### Método e custo

- 12 buscas `tvly search --max-results 10` (basic, 1 crédito cada), `--include-domains` por
  ATS (`jobs.ashbyhq.com`, `job-boards.greenhouse.io`/`boards.greenhouse.io`,
  `jobs.lever.co`, `apply.workable.com`, `teamtailor.com`, `myworkdayjobs.com`), uma
  consulta PT (`estágio OR estagiário OR trainee ... Brasil`) e uma EN (`intern OR
  internship OR "entry level" OR "new grad" ... Brazil OR LATAM OR remote`) por domínio.
  **Créditos: 12 (estimado por chamada; `tvly` não expõe saldo). Total do card com a rodada 1:
  ~14 de ~40 pedidos / 100 por execução (F20-43).**
- A consulta PT em Workable devolveu quase só sites fora do domínio (o `include-domains`
  da Tavily é preferência, não filtro rígido); a EN funcionou.
- Sondagem direta (1 req/candidato, 1 s de pausa) de ~35 boards: título casado por
  palavras-chave (`estágio/estagiário/trainee/jovem aprendiz/aprendiz/intern/internship/
  entry level/new grad/junior/júnior/graduate`). Workday paginado até 120 vagas nos que não
  mostraram sinal na 1ª página.
- Correção de sonda: o JSON Feed do Teamtailor usa a chave `items` (não `data`); a
  primeira passada com `data` deu falso "0 vagas" em Loft/Leroy Merlin/Obramax/BYD e foi refeita.

### Boards ativados (26, todos `probe` ok, `enable_sources.py --accept-terms`, execução real `SUCCEEDED`)

Cadastro via `CompanyService.reconcile` + `SourceDefinitionModel` (mesmo padrão de
`import_research_catalog.py`), depois `enable_sources.py --probe-only` (26/26 ok) e
`--accept-terms` (26 ativadas), depois `collect.py` só nos 26 IDs (`--max-items 200`).

| ATS | Fontes (vagas coletadas → JUNIOR/INTERN pelo normalizador / por título) |
| --- | --- |
| Ashby | Upvest 17→4/4; Cohere 145→3/4; Quora 6→0/1; Realm 11→1/2; Replit 75→0/1 |
| Greenhouse | XP Inc 172→8/12; Artefact 118→27/20; Grupo Burson Brasil 187→12/14; Monks 197→9/8; Hunter Douglas 73→1/6; Stone 193→0/2; Altafonte Brasil 1→1/0 |
| Lever | Palantir 200→25/46; Zippi 5→1/0; Welo Global 200→2/2 |
| Workable | Valatam 12→5/4 |
| Teamtailor | Leroy Merlin Brasil 100→0/8 (Jovem Aprendiz); Obramax 96→1/30 (Vendedor Júnior) |
| Workday | P&G 199→41/58; AIG 198→19/19; ERM 200→9/16; Chanel 199→9/8; Toyota TLAC 51→5/0*; Biogen 197→4/4; RELX 196→4/5; Abbott 179→2/1 |

\* o regex de título desta medição usa `estagi` sem acento; "Estágio" acentuado do Toyota
não casa nele, mas o normalizador o marcou INTERN (5). Ambas as contagens são conservadoras.

Total das 26 fontes: **3227 oportunidades, 193 JUNIOR/INTERN pelo normalizador, 275 por
palavra-chave de título** (a correção F20-70 ainda não está mergeada: "Estagiário",
"Trainee", "Jovem Aprendiz", "New Grad" caem em UNKNOWN, então a contagem por título é a
mais fiel). Os boards brasileiros (XP, Stone, Burson, Artefact, Monks, Leroy Merlin,
Obramax, Zippi, Altafonte, Toyota) trazem vagas de estágio/aprendiz em PT.

### Antes/depois

| Escopo | Antes | Depois |
| --- | --- | --- |
| Acervo da `f20manual` no início do card (diagnóstico) | 18 JUNIOR+INTERN / 2288 (0,79%) | — |
| Acervo global agora | — | 249 JUNIOR+INTERN / 8850 (2,81%); 349 por título |
| Global excluindo as 26 fontes desta rodada | 56 / 5623 (1,00%) | — |
| Só as 26 fontes desta rodada | 0 | 193 / 3227 (5,98%); 275 por título |

**Confusor:** a `f20manual` é compartilhada com o worker do F20-60, que coletou fontes em
paralelo (2288 → ~5600 oportunidades sem as minhas). Por isso o efeito atribuível a esta
rodada é a linha "só as 26 fontes" (193 JUNIOR/INTERN novos pelo normalizador, 275 por
título), não a diferença global.

### Incertezas

- `--max-items 200` truncou boards grandes (Workday, Palantir, Stone, Monks, Welo Global);
  os números são piso, não o total dos boards.
- Vários JUNIOR/INTERN são de vagas nos EUA/Europa (Palantir, AIG, Cohere), não Brasil/LATAM;
  a filtragem por localização é do matching, não da coleta.
- Doctoralia Brasil (Ashby, 17 vagas, "Jovem Aprendiz" visto na busca) e Mechanical Orchard
  (Lever) não tinham vaga junior/intern no título na sonda e não foram ativados; Loft e BYD
  Brasil (Teamtailor) idem; Nubank Greenhouse continua vazio (rodada 1).
- Créditos Tavily estimados, sem contador da CLI. Docker da `f20manual` caiu (exit 255)
  entre a coleta e a medição; reiniciada com `docker compose -p f20manual ... start`, dados intactos.
