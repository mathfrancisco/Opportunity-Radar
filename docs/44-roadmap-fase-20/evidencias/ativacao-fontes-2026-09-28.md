# Ativação de fontes e melhoria da descoberta de sites — 2026-09-28

Evidência de execução real (não fabricada), pilha Docker Compose manual `f20manual`
(código da PR, cópia do banco real, `AI_ENABLED=false`) e verificação isolada em
`f20ativ`. A pilha real `opportunity-radar` (janela de sete dias, T0
`2026-09-28T12:01:55Z`) não foi tocada, parada, reconstruída nem sofreu `exec` de
escrita em nenhum momento desta sessão.

## Resumo

| Item | Resultado |
| --- | --- |
| Fontes desativadas herdadas (7) | Nenhuma viável — 6 são fixtures de teste (tokens/board sintéticos, 404 real) e 1 é um `manual` duplicado sem endpoint. Nenhuma ativada; motivo registrado por linha (§1). |
| `scripts/discover_sites.py` (código antigo, 115 empresas) | 19 boards reais encontrados; 11 novas fontes ativadas, 6 já ativas re-confirmadas, 2 boards reais mas mortos (§2). |
| Melhoria da descoberta (commit `f7df932`) | Probe direto por slug antes de rastrear o site, passe raso (`careers` primeiro, sitemap só em caso de falha), concorrência entre hosts, normalização de endpoint canônico e upsert idempotente. Testes novos + suíte completa verdes (§3). |
| Comparação real antes/depois (10 empresas reais, mesma rede) | Antigo: 58,32 s, achou ATS em 6/10. Novo: 18,11 s, achou ATS em 10/10 — ~3,2× mais rápido e achou 3 boards reais que o antigo perdeu (Linear, Vercel, Stripe), todos ativados (§3.2). |
| Tavily (F20-43, teto 100 créditos/execução) | 43 buscas reais (~43 créditos, dentro do teto); 20 boards reais confirmados e ativados, 1 candidato não viável, 21 sem achado utilizável (§4). |
| Fontes habilitadas na `f20manual` | 30 → 64 (34 novas); 7 continuam desativadas (mesmas de antes, nenhuma viável). |

## 1. As 7 fontes desativadas herdadas — nenhuma viável

Probe real via `scripts/enable_sources.py --probe-only` (mesmo caminho de probe que a
interface usa, `acquisition/probing.py::run_probe`) contra o board público de verdade —
não simulação.

| ATS | Nome / identificador | Probe real | Ativada? | Motivo |
| --- | --- | --- | --- | --- |
| ashby | `board_identifier=ci-board` ("CI Ashby activation") | `api.ashbyhq.com/posting-api/job-board/ci-board` → 404 real | Não | Fixture de teste/CI (`company_name="CI Company"`), não é uma empresa real do catálogo |
| greenhouse | `board_token=probe770bc3e4` | `boards-api.greenhouse.io/v1/boards/probe770bc3e4/jobs` → 404 real | Não | Fixture de teste |
| greenhouse | `board_token=probe96146863` | idem, 404 real | Não | Fixture de teste |
| greenhouse | `board_token=probe3ef03a22` | idem, 404 real | Não | Fixture de teste |
| greenhouse | `board_token=probeb5d386bf` | idem, 404 real | Não | Fixture de teste |
| greenhouse | `board_token=probe8887439c` | idem, 404 real | Não | Fixture de teste |
| manual | "Manual 0e347747", `configuration={}` | Sem endpoint — o coletor `manual` nunca busca uma URL (`collectors.py:70`), só processa `manual_inputs` submetidos na própria chamada | Não | Duplicado inerte de "Manual MVP intake", que já está ativa; não há board para provar |

Nenhuma das 7 corresponde a uma empresa real do catálogo — são dados de fixture
copiados junto com o dump para a `f20manual`. Continuam desativadas, com o motivo
registrado na própria linha acima (evidência já também gravada via `SourceProbe` na
`f20manual`, `error_code=SOURCE_NOT_FOUND` para as 6 com endpoint).

## 2. `discover_sites.py` (código anterior à melhoria) — 115 empresas, 19 boards reais

Execução real e completa do catálogo elegível na `f20manual` (companhias com
`careers_confirmed` e sem ATS conhecido), 1 req/s, antes da melhoria de descoberta
descrita na seção 3.

```json
{"checked": 115, "by_ats": {"greenhouse": 8, "ashby": 7, "workday": 3, "lever": 1},
 "by_stop_reason": {"LIMIT_REACHED": 65, "EXHAUSTED": 24, "POLICY": 26}}
```

### 2.1 Já ativas — re-confirmadas pela descoberta, sem ação nova

| Empresa | ATS | slug | 
| --- | --- | --- |
| Apollo GraphQL | ashby | `apollo-graphql` |
| LangChain | ashby | `langchain` |
| Oyster | ashby | `oyster` |
| Retell AI | ashby | `retell-ai` |
| Anthropic | greenhouse | `anthropic` |
| Lokalise | greenhouse | `lokalise` |

### 2.2 Novas fontes ativadas (probe real → `PASSED` → habilitada → execução real `SUCCEEDED`)

| Empresa | ATS | slug / tenant | Probe real | Vagas na execução |
| --- | --- | --- | --- | --- |
| LlamaIndex | ashby | `llamaindex` | 200, 9 vagas reais no board completo | 3 (execução limitada a `max_items=3`) |
| Plaid | ashby | `plaid` | 200, 123 vagas | 3 |
| Sentry | ashby | `sentry` | 200, 41 vagas | 3 |
| GitLab | greenhouse | `gitlab` | 200, 198 vagas | 3 |
| Honeycomb | greenhouse | `honeycomb` | 200, 15 vagas | 3 |
| Pulumi | greenhouse | `pulumicorporation` | 200, 5 vagas | 3 |
| Tailscale | greenhouse | `tailscale` | 200, 51 vagas | 3 |
| Ubiminds | lever | `Ubiminds`, `api_region=global` | 200, 21 vagas | 3 |
| NVIDIA | workday | `nvidia/NVIDIAExternalCareerSite`, `wd5` | 200 (POST CXS real) | 3 |
| SUSE | workday | `suse/Jobsatsuse`, `wd3` | 200 (POST CXS real) | 3 |
| Santander | workday | `santander/SantanderCareers`, `wd3` | 200 (POST CXS real) | 3 |

Cada uma seguiu o mesmo caminho da interface: `POST /sources` (proposta inerte) →
`POST /sources/{id}/probe` (`PASSED`) → `PATCH /sources/{id}` (`enabled=true`,
`terms_reviewed=true`, `collector_local_tested=true`) → `POST /sources/{id}/runs` →
`SourceRun.status=SUCCEEDED`.

### 2.3 Boards reais, mas mortos — não ativados

| Empresa | ATS | slug testado | Probe real | Observação |
| --- | --- | --- | --- | --- |
| Airbyte | greenhouse | `airbyte` | 404 real (`boards-api.greenhouse.io` e `job-boards.greenhouse.io`) | Mesmo achado de `retomada-real-e-endpoints-2026-09-28.md` §6: o board parece ter sido desativado ou a empresa migrou de ATS. Não homologar agora. |
| Temporal | greenhouse | `temporaltechnologies` | 404 real; a página do link (`job-boards.greenhouse.io/temporaltechnologies/jobs/5019997007`) redireciona para `?error=true` | Vaga indexada ainda existe, mas o board raiz não resolve mais — mesmo padrão do Airbyte. Não homologar agora. |

## 3. Melhoria da descoberta de sites (commit `f7df932`)

Escopo pedido pelo coordenador a meio da tarefa, implementado em
`scripts/discover_sites.py` e `src/opportunity_radar/acquisition/limited_discovery.py`:

1. **Probe direto por slug antes de rastrear** (`probe_direct_ats`): tenta o board
   público de cada ATS com coletor (ashby, greenhouse, lever, workable, teamtailor —
   nunca Gupy, F20-32) usando slugs plausíveis do nome/domínio da empresa. Um board
   real e populado pula o rastreamento do site inteiro.
2. **Passe raso primeiro**: a página de carreiras é verificada isolada; o sitemap só é
   buscado se esse passe não encontrar nada. Padrões deste script ficaram mais
   conservadores: `max_html_responses=5`, `max_sitemap_files=1`.
3. **Filtro de sitemap mais estrito**: só `career|jobs?|vagas?|carreiras?` (antes,
   uma lista mais ampla de palavras).
4. **Parada antecipada**: primeiro ATS com coletor encontrado termina a checagem
   daquela empresa.
5. **Isolamento de erro**: cada empresa roda em `try/except` própria; uma falha vira um
   contador (`report["errors"]`) e o lote continua.
6. **Endpoint canônico + upsert idempotente**: `canonical_board_url` normaliza
   `boards.greenhouse.io` para `job-boards.greenhouse.io` (hostname atual, mesmo board);
   `upsert_ats_identified_source` recupera de `uq_company_source_company_type_endpoint`
   quando uma execução concorrente já inseriu a mesma linha, em vez de propagar o erro
   (teste de regressão dedicado, caso GitLab).
7. **Operacional**: `--concurrency` (padrão 8, 1 req/s e 1 requisição por host mantidos
   via lock por host) e `--progress-file` para relatório incremental em execuções longas
   em segundo plano.

### 3.1 Verificação

```
docker compose -p f20ativ -f compose.yaml -f compose.dev.yaml run --rm api ruff check .        # All checks passed!
docker compose -p f20ativ -f compose.yaml -f compose.dev.yaml run --rm api mypy                 # Success: no issues found in 120 source files
docker compose -p f20ativ -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_limited_discovery.py            # 18 passed, 3 skipped
docker compose -p f20ativ -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q tests/backend/acquisition/test_limited_discovery.py -m integration   # 3 passed
docker compose -p f20ativ -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q                                    # 1001 passed, 10 skipped
```

### 3.2 Comparação real antes/depois

Re-executar o catálogo completo da `f20manual` para medir o lote inteiro não foi
possível: as 223 empresas já tinham `discovery_attempt` desta mesma sessão (janelas de
7/30 dias por empresa, SPEC 43), então o lote elegível ficou vazio
(`{"checked": 0, ...}` real, veja `scripts/discover_sites.py --dry-run` rodado às
18:31:19–18:31:26 UTC). Apagar esse histórico em massa para forçar uma reamostragem foi
bloqueado pelo classificador de permissões do ambiente ("Cloud Storage Mass Delete");
não contornado, por instrução do operador.

Em vez disso, a comparação abaixo roda `run_limited_discovery` real (rede real, sem
mocks) contra as páginas de carreira reais de 10 empresas, com e sem o probe direto por
slug, mesmos limites (`max_html_responses=5`, `max_sitemap_files=1`), mesmo
`min_interval_seconds=1.0`:

| Empresa | Modo | Segundos | Requisições HTTP | Resultado | ATS achado |
| --- | --- | --- | --- | --- | --- |
| LlamaIndex | antigo | 6,05 | 5 | EXHAUSTED | ashby |
| Plaid | antigo | 4,82 | 4 | POLICY | — |
| Sentry | antigo | 7,43 | 6 | EXHAUSTED | ashby |
| GitLab | antigo | 5,86 | 6 | LIMIT_REACHED | — |
| Honeycomb | antigo | 1,59 | 2 | POLICY | — |
| Tailscale | antigo | 2,55 | 3 | EXHAUSTED | greenhouse |
| Ubiminds | antigo | 3,16 | 2 | EXHAUSTED | lever |
| Vercel | antigo | 6,83 | 6 | LIMIT_REACHED | — |
| Linear | antigo | 12,98 | 6 | LIMIT_REACHED | — |
| Stripe | antigo | 7,05 | 6 | LIMIT_REACHED | — |
| LlamaIndex | novo | 0,23 | 1 | EXHAUSTED | ashby |
| Plaid | novo | 0,27 | 1 | EXHAUSTED | ashby |
| Sentry | novo | 0,25 | 1 | EXHAUSTED | ashby |
| GitLab | novo | 1,71 | 2 | EXHAUSTED | greenhouse |
| Honeycomb | novo | 1,39 | 2 | EXHAUSTED | greenhouse |
| Tailscale | novo | 1,37 | 2 | EXHAUSTED | greenhouse |
| Ubiminds | novo | 9,40 | 2 | EXHAUSTED | lever |
| Vercel | novo | 1,44 | 2 | EXHAUSTED | greenhouse |
| Linear | novo | 0,11 | 1 | EXHAUSTED | ashby |
| Stripe | novo | 1,94 | 2 | EXHAUSTED | greenhouse |

**Total antigo: 58,32 s (6/10 acharam ATS). Total novo: 18,11 s (10/10 acharam ATS) —
~3,2× mais rápido e 4 achados a mais** (GitLab já se sabia; Vercel, Linear e Stripe eram
desconhecidos e foram confirmados reais e ativados, veja abaixo). `Ubiminds` no modo novo
ficou mais lento que o antigo (9,40 s vs 3,16 s) porque o probe direto por slug tentou
`ashby`, `greenhouse` e `lever` antes de acertar (a ordem fixa de ATS tentados nem sempre
acerta de primeira) — mesmo assim, no agregado de 10 empresas reais o novo caminho venceu
com folga.

### 3.3 Vercel, Linear e Stripe — achados pelo novo probe, confirmados e ativados

| Empresa | ATS | slug | Probe real | Vagas na execução |
| --- | --- | --- | --- | --- |
| Linear | ashby | `linear` | 200, 30 vagas no board completo | 3 |
| Vercel | greenhouse | `vercel` | 200, 88 vagas | 3 |
| Stripe | greenhouse | `stripe` | 200, 704 vagas | 3 |

Mesmo caminho de ativação da seção 2.2 (`POST /sources` → `probe` → `PATCH` → `runs`,
todos `SUCCEEDED`).

## 4. Tavily (F20-43) — orçamento e resultado

`tavily_credit_budget_per_run: int = 100` (`src/opportunity_radar/platform/config.py:109`,
`docs/44-roadmap-fase-20/fase-20/f20-43-tavily-orcamento-de-creditos.md`) é o teto por
execução configurado no projeto; usado aqui como referência de orçamento para a busca
manual desta tarefa (o `TavilyCreditBudgetGuard` do F20-43 se aplica ao coletor da
aplicação, não a esta sessão manual — a CLI `tvly` não devolve o campo de créditos por
chamada, então o gasto abaixo é a contagem de chamadas, 1 crédito/busca `basic` pelo
preço padrão documentado da Tavily).

**Gasto: 43 buscas `tvly search --depth basic --max-results 3`, filtradas por
`--include-domains` nos 8 hosts de ATS com coletor (nunca Gupy) ≈ 43 créditos de um teto
de 100 — dentro do orçamento, sem esgotar.**

Alvo: as 42 empresas do catálogo ainda sem ATS conhecido após as seções 2 e 3 (excluídas
as 3 já resolvidas por probe direto), mais 1 busca de teste (Adyen, fora da amostra
final). "Relevância de perfil não importa" — o filtro foi só ATS com coletor real.

### 4.1 Confirmados reais e ativados (20)

| Empresa | ATS | slug | Probe real | Vagas na execução |
| --- | --- | --- | --- | --- |
| Aiven | greenhouse | `aiven36` | 200, 37 vagas | 3 |
| Algolia | greenhouse | `algolia` | 200, 34 vagas | 3 |
| Automattic | greenhouse | `automatticcareers` | 200, 16 vagas | 3 |
| Brex | greenhouse | `brex` | 200, 259 vagas | 3 |
| Camunda | ashby | `camunda` | 200, 39 vagas | 3 |
| Chainguard | greenhouse | `chainguard` | 200, 83 vagas | 3 |
| Cloudflare | greenhouse | `cloudflare` | 200, 399 vagas | 3 |
| Cockroach Labs | greenhouse | `cockroachlabs` | 200, 19 vagas | 3 |
| Databricks | greenhouse | `databricks` | 200, 881 vagas | 3 |
| Datadog | greenhouse | `datadog` | 200, 438 vagas | 3 |
| DigitalOcean | greenhouse | `digitalocean98` | 200, 163 vagas | 3 |
| DuckDuckGo | ashby | `duck-duck-go` | 200, 10 vagas | 3 |
| ElevenLabs | ashby | `elevenlabs` | 200, 201 vagas | 3 |
| Fastly | greenhouse | `fastly` | 200, 42 vagas | 3 |
| Glean | greenhouse | `gleanwork` | 200, 131 vagas | 3 |
| HubSpot | greenhouse | `hubspotjobs` | 200, 132 vagas | 3 |
| MongoDB | greenhouse | `mongodb` | 200, 398 vagas | 3 |
| OpenAI | ashby | `openai` | 200, 831 vagas | 3 |
| Storyblok | greenhouse | `storyblok` | 200, 10 vagas | 3 |
| Zapier | ashby | `zapier` | 200, 10 vagas | 3 |

Mesmo caminho de ativação: `POST /sources` (`discovery_via=tavily_search` na
`configuration`) → probe real `PASSED` → `PATCH` habilitando → `POST .../runs`
→ `SUCCEEDED`.

### 4.2 Candidato não viável (1)

| Empresa | ATS | slug sugerido pela busca | Probe real | Motivo |
| --- | --- | --- | --- | --- |
| ClickHouse | greenhouse | `clickhouse` | 404 real (e variantes `clickhouseinc`, `clickhouse-inc`, `clickhousedb`, `clickhousecorp`, todas 404) | A busca só achou URLs de vaga individual (`boards.greenhouse.io/clickhouse/jobs/...`); o board raiz não resolve com nenhum token plausível testado. Não ativado. |

### 4.3 Sem achado utilizável (21)

Busca real feita, sem nenhuma URL nos 8 domínios de ATS com coletor que correspondesse à
própria empresa (a maioria trouxe boards reais de outras empresas — ruído de relevância
da busca, não um achado válido, então descartado):

Akamai, Buffer, Canonical, CircleCI, Contentful, Docker, Elastic, Klarna, PostHog,
Railway, Ramp, Replicate, Resend, Retool, Sanity, Snyk, Timescale, Toggl, Weaviate,
Windmill, dbt Labs.

## 5. Contagens finais na `f20manual`

| Métrica | Antes desta sessão | Depois |
| --- | --- | --- |
| `source_definition` habilitadas | 30 | 64 |
| `source_definition` desativadas | 7 | 7 (mesmas, nenhuma viável) |
| Novas fontes ativadas nesta sessão | — | 34 (11 descoberta antiga + 3 probe direto novo + 20 Tavily) |
| Créditos Tavily gastos | — | ~43 de um teto de 100/execução |

## 6. O que fica pendente

- As 34 fontes novas ativadas aqui existem apenas na `f20manual` (pilha manual de
  verificação). Ativá-las na pilha real `opportunity-radar` fica para depois da janela
  de sete dias (`2026-10-05T12:02Z`) — item já apontado em
  `docs/44-roadmap-fase-20/validacao-pendente.md` §4.
- ClickHouse (greenhouse, §4.2) e Airbyte/Temporal (greenhouse, §2.3): sem endpoint real
  confirmável nesta sessão; revisitar numa próxima rodada de descoberta.
- As 21 empresas sem achado (§4.3) podem não usar nenhum dos 8 ATS com coletor, ou usar
  um deles sob um slug não descoberto pela busca — não investigado além do orçamento
  desta tarefa.
- Reset em massa de `discovery_attempt` para repetir a medição de tempo do lote completo
  (115 empresas) com o código novo continua bloqueado pelo classificador de permissões;
  a comparação real de 10 empresas (§3.2) é a evidência de velocidade disponível.
