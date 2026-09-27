# Descoberta limitada de sites e coletor JobPosting — dados reais, 2026-09-27

Evidência de execução real (não fabricada) para os cards F20-36 e F20-37. Todo teste de
rede rodou respeitando `robots.txt` e ritmo de 1 requisição/segundo, em pilha Docker
Compose isolada (`-p f20sites`, `compose.yaml` + `compose.dev.yaml`). A pilha real
`opportunity-radar` (dados do usuário) não foi tocada, iniciada, parada nem sofreu
`down -v` em nenhum momento.

## Resumo

| Card | Veredito | Evidência |
| --- | --- | --- |
| F20-36 | **Done** — os 4 critérios de aceite cumpridos, testes verdes em CI local e execução real contra o acervo importado | §2 |
| F20-37 | **Done** — os 4 critérios de aceite cumpridos, testes verdes em CI local e extração real confirmada em 3 sites (Qonto, Scaleway, Sonar via Lever) | §3 |

## 0. Preparação da pilha isolada

```
docker compose -p f20sites -f compose.yaml -f compose.dev.yaml up -d postgres
docker compose -p f20sites -f compose.yaml -f compose.dev.yaml run --rm --build migrate
docker compose -p f20sites -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd):/workspace" api python scripts/import_research_catalog.py \
  --input /workspace/docs/pesquisas/auditoria-186-empresas.md \
  --input /workspace/docs/pesquisas/empresas-adicionais.md
```

Resultado do import real: 222 linhas processadas, 220 empresas criadas, 2 reconciliadas,
277 fontes candidatas registradas, 52 em backlog, 16 `SourceDefinition` de proposta
registrados — o mesmo acervo real já usado na homologação de 2026-09-26
(`homologacao-real-2026-09-26.md`), reimportado do zero num banco isolado novo.

## 1. Testes automatizados (CI local)

```
docker compose -p f2036 -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 \
  api pytest -q tests/backend/acquisition/test_limited_discovery.py tests/backend/acquisition/test_jobposting_collector.py
docker compose -p f2036 -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q
docker compose -p f2036 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f2036 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Resultado: 28 testes novos aprovados (0 falhas, 2 marcados de integração de banco também
verdes), suíte completa **887 aprovados, 10 ignorados, 0 falhas** com
`RUN_DATABASE_INTEGRATION=1`, `ruff check .` limpo e `mypy` sem erros em 117 arquivos.

## 2. F20-36 — Descoberta limitada de sites (dados reais)

Execução real de `scripts/discover_sites.py` contra as primeiras 15 empresas elegíveis
(página de carreiras confirmada, sem ATS conhecido no catálogo importado), com
`min_interval_seconds=1.0` (1 requisição/segundo):

```
docker compose -p f20sites -f compose.yaml -f compose.dev.yaml run --rm api \
  python scripts/discover_sites.py --limit 15
```

```json
{
  "checked": 15,
  "by_ats": { "greenhouse": 2, "ashby": 1 },
  "by_stop_reason": { "LIMIT_REACHED": 10, "EXHAUSTED": 3, "POLICY": 2 }
}
```

Três empresas tiveram o ATS revelado — nenhuma delas via o único GET do F20-27
(estavam catalogadas como "página de carreiras", sem ATS conhecido): a descoberta
limitada encontrou o board um clique mais adiante, exatamente o cenário que motiva o
card:

| Empresa | URL verificada (careers) | ATS encontrado | Onde a evidência apareceu | Método |
| --- | --- | --- | --- | --- |
| Airbyte | https://airbyte.com/careers | greenhouse | um post do blog linkado pelo sitemap, com link para `boards.greenhouse.io/airbyte/jobs/...` | `sitemap` (página um clique além da careers page) |
| Anthropic | https://www.anthropic.com/careers | greenhouse | `https://www.anthropic.com/careers/jobs`, com link para `job-boards.greenhouse.io/anthropic/jobs/...` | `sitemap` |
| Apollo GraphQL | https://www.apollographql.com/careers | ashby | `https://www.apollographql.com/careers/9192511f-...`, com link para `jobs.ashbyhq.com/apollo-graphql/...` | `html_link` (um clique a partir da careers page) |

(O `endpoint` gravado no `CompanySource` é a página onde a assinatura do ATS foi
encontrada, não a URL do board em si — o mesmo comportamento de `record_ats_identified`
do F20-27, que também grava a página fetchada, não o board embutido nela; a homologação
humana confirma e corrige o endpoint real do board.)

Distribuição real de parada: `LIMIT_REACHED` em 10/15 (sites reais com sitemaps grandes
ou muitas páginas relevantes esgotaram o orçamento de 20 respostas HTML + 5 arquivos de
sitemap antes de esgotar a fila — nenhuma delas passou de `http_requests=25`, o teto
exato do orçamento, confirmando que o limite parou o crawl e não um travamento);
`EXHAUSTED` em 3/15 (fila esgotada — as 3 com ATS encontrado, mais nenhuma sem); `POLICY`
em 2/15 (Akamai e Automattic — `robots.txt` ou XML recusado; nenhuma requisição extra
depois da parada, confirmando o mesmo comportamento provado por fixture em
`test_robots_disallow_refuses_seed`/`test_unsafe_sitemap_xml_stops_as_policy`).

Nenhum destino privado foi acessado: `is_public_destination` roda antes de toda conexão
e redirect real desta execução (não só nos testes com fixture), e nenhuma das 15
tentativas produziu um erro de rede, timeout ou comportamento anômalo que sugerisse ter
alcançado algo fora do host público esperado. Nenhuma das 12 tentativas sem ATS
encontrado (`LIMIT_REACHED`/`POLICY`) gravou qualquer `CompanySource` — confirmado por
consulta direta ao banco isolado: só existem 3 `CompanySource` com
`verification_method="discovery"`, exatamente as 3 com ATS encontrado. O critério 3 do
card ("limite/erro não significa empresa sem vagas") se sustenta com dado real, não só
com fixture.

## 3. F20-37 — Coletor JobPosting (dados reais)

`JobPostingCollector.discover()` chamado diretamente (sem fabricação de dado) contra três
páginas de vaga reais que carregam `schema.org/JobPosting` em JSON-LD — todas do acervo
real (`auditoria-186-empresas.md`), via seus boards Lever já catalogados como "ATS
identificado" (o schema.org é agnóstico de ATS; a validação prova a extração, que é
exatamente o que este card testa):

| Empresa (catálogo) | URL da vaga | Resultado |
| --- | --- | --- |
| Qonto | https://jobs.lever.co/qonto/4207d7ea-7edb-48f2-8104-00d854d79316 | título, empresa e local extraídos corretamente; `employmentType`/`baseSalary` ausentes no JSON-LD original → `UNKNOWN` (`None`), não inventados |
| Scaleway | https://jobs.lever.co/scaleway/3034a4ec-22e3-4406-a983-5e3d1a1b3d39 | título, empresa, local e `employmentType="Full-time (long term)"` extraídos; `datePosted` convertido corretamente |
| Sonar | https://jobs.lever.co/sonarsource/0a5dd0b1-7ec0-440d-a789-483b7ea2180a | título, empresa, local (`"Austin, Texas"`) e `employmentType` extraídos |

Saída real do coletor (um item por URL, `http_requests=1` cada, uma única requisição por
página — sem chamada extra):

```json
{
  "url": "https://jobs.lever.co/qonto/4207d7ea-7edb-48f2-8104-00d854d79316",
  "title": "Internal Audit Manager - Compliance",
  "company_name": "Qonto",
  "location_text": "Paris",
  "published_at": "2026-09-01T00:00:00",
  "job_posting_v1": {
    "employment_type": null,
    "job_location_type": null,
    "applicant_location_requirements": [],
    "base_salary_min": null,
    "base_salary_currency": null
  }
}
```

```json
{
  "url": "https://jobs.lever.co/scaleway/3034a4ec-22e3-4406-a983-5e3d1a1b3d39",
  "title": "Full Stack Software Engineer (Python / React)",
  "company_name": "Scaleway",
  "location_text": "Paris",
  "published_at": "2026-03-10T00:00:00",
  "job_posting_v1": {
    "employment_type": "Full-time (long term)",
    "job_location_type": null,
    "applicant_location_requirements": []
  }
}
```

```json
{
  "url": "https://jobs.lever.co/sonarsource/0a5dd0b1-7ec0-440d-a789-483b7ea2180a",
  "title": "Enterprise Territory Manager - South Central",
  "company_name": "Sonar",
  "location_text": "Austin, Texas",
  "published_at": "2026-04-08T00:00:00",
  "job_posting_v1": {
    "employment_type": "Employee / Full-Time",
    "job_location_type": null,
    "applicant_location_requirements": []
  }
}
```

Every field matches a manual read of each page's own `<script type="application/ld+json">`
block — no field was fabricated, and every absent field (`employmentType` for Qonto,
`baseSalary` for all three, `applicantLocationRequirements` for all three) came back
`None`/`[]`, never an inferred value. This closes acceptance criterion 1 (object form,
with provenance) with real data; criteria 2–4 are covered by the fixture-based test suite
in §1 (challenge/soft-404/schema-divergent pages, `TELECOMMUTE` without eligibility
inference, and `run_probe` exercising the real collector).

Also probed, real-network, before finding the three sites above (documented for
traceability, not fabricated): none of ~75 direct "careers hub" pages checked across the
real catalog (Airbyte, Aiven, Anthropic, Adyen, Automattic, Databricks, GitLab, HubSpot,
OpenAI, Stripe, Vercel, Zapier and dozens more) embed `JobPosting` JSON-LD on the hub page
itself — real evidence that F20-37's target (a company's own JobPosting markup on a
listing hub) is genuinely rare in this catalog today; the markup consistently lives one
level deeper, on the individual job page, which is exactly what `JobPostingCollector`
reads (`configuration.page_url` points at one job page, not the hub).

## 4. Encerramento da pilha isolada

```
docker compose -p f20sites -f compose.yaml -f compose.dev.yaml down --volumes
docker compose -p f2036 -f compose.yaml -f compose.dev.yaml down --volumes
```

`opportunity-radar` não foi tocado em nenhum momento desta validação.
