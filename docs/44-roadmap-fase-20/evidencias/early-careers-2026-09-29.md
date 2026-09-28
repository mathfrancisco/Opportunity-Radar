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
