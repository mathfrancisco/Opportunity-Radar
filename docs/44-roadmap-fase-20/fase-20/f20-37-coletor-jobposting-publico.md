# CARD F20-37 — Coletor JobPosting público

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-36, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-03](../../40-roadmap-varredura-produtiva/fase-18/f18-03-coletor-jobposting-publico.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

Páginas públicas sem ATS suportado entram no radar pelo mesmo contrato e com evidência de cada campo.

## Escopo

- Homologar source_type jobposting, probe, registro e formulário; preferir API/feed existente antes de HTML.
- Extrair JSON-LD JobPosting em objeto/lista/@graph; validar identidade, empresa, título, descrição e link de candidatura.
- Separar local, residência permitida, trabalho remoto, visto, salário/moeda/período e validade. Ausência é UNKNOWN.
- HTML sem JSON-LD só com mapeamento versionado específico e fixture; sem headless ou seletores adivinhados.
- Challenge, soft-404, estrutura alterada e conflito entre texto/marcação são falha/revisão. Detalhe individual não prova board completo.
- Produzir SourceRun/RawItem; ausência em sitemap ou validThrough vencido não fecha oportunidade global automaticamente.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Objetos, listas e @graph geram itens com procedência.
- [ ] Página bloqueada/quebrada não vira sucesso vazio.
- [ ] Remoto não vira elegibilidade global por inferência.
- [ ] Probe e homologação exercitam o coletor real; implementação entra no fluxo normal.

## Verificação

- **CI:** Fixtures pt/en, múltiplas vagas, campos ausentes, schema divergente, soft-404 e persistência/normalização.
- **Máquina de referência:** Homologar pequena coorte de páginas estáticas e comparar extração com leitura manual.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`acquisition/jobposting.py` novo, registry/probing/proposals, normalização, SourceCreateForm e fixtures.

## Contexto no código

Não existe `src/opportunity_radar/acquisition/jobposting.py`; este card cria o coletor do
zero, mas seguindo exatamente o mesmo contrato dos outros quatro:

- `acquisition/collectors.py:28-38` define o `Collector` Protocol (`source_type`,
  `capabilities`, `healthcheck`, `discover`) que todo coletor implementa; `remotive.py`
  (o mais simples, feed JSON) é o melhor modelo de estrutura: `_client`/`_client_factory`
  injetáveis, `discover` que itera e emite `CollectedItem`, mapeamento de erro HTTP em
  `AcquisitionErrorCode` (`remotive.py:1-100` e além).
- `acquisition/domain.py:217-231` (`CollectedItem`) só tem campos genéricos
  (`title`, `company_name`, `location_text`, `description`, `published_at`,
  `metadata: Mapping[str, Any]`, ...) — não tem campos próprios para residência,
  trabalho remoto, visto ou salário/moeda/período/validade. Esses campos entram pelo
  `metadata`, do mesmo jeito que o `collected_item_v1` (`opportunities/domain.py:225`,
  `opportunities/service.py:600-742`) já carrega o resto do envelope estável para a
  normalização.
- `opportunities/regions.py:109` (`resolve_allowed_countries`) já resolve texto de local
  ("Remote — Brazil", "LATAM") para países ISO 3166-1; o extrator de JobPosting deve
  alimentar essa função com `jobLocation`/`applicantLocationRequirements` separados, sem
  reimplementar a resolução de região.
- `acquisition/domain.py:13-28` (`AcquisitionErrorCode`) não tem um código para
  "challenge/soft-404/schema incompatível"; hoje o mais próximo é
  `PARSER_SCHEMA_CHANGED`, usado pelos coletores existentes para pular item inválido sem
  derrubar o run (`remotive.py:80-84`) — usar o mesmo código para página bloqueada, não
  inventar um novo sem necessidade.
- `acquisition/service.py:870-914` (`_persist_item`) e `canonical_payload_hash`
  (linha 935) já cuidam de dedupe e de gravar `RawItem`/`RawItemPayloadModel` — o novo
  coletor não escreve no banco diretamente, só emite `CollectedItem`s para o `discover`
  já orquestrado pelo `AcquisitionService`.
- `acquisition/probing.py:24` (`PROBE_TYPES`) lista os coletores que a sonda de
  homologação exercita; `jobposting` precisa entrar nessa tupla para que a homologação
  rode o coletor real, como o critério de aceite 4 pede.
- `acquisition/registry.py:12-26` (`build_collector_registry`) precisa registrar o novo
  `JobPostingCollector`.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/acquisition/jobposting.py` | `JobPostingCollector`, extração de JSON-LD, mapeamento de erro |
| Alterar | `src/opportunity_radar/acquisition/probing.py` | adicionar `"jobposting"` a `PROBE_TYPES` e a `probe_request` |
| Alterar | `src/opportunity_radar/acquisition/registry.py` | registrar `JobPostingCollector` |
| Alterar | `src/opportunity_radar/acquisition/domain.py` | `evidence_status` já aceita `"careers_page"`; confirmar se falta valor para o novo `source_type` (registrar no PR se precisar) |
| Criar | `tests/backend/acquisition/test_jobposting_collector.py` | fixtures objeto/lista/`@graph`, pt/en, campos ausentes, soft-404 |
| Criar | `tests/e2e/fake_jobposting_site.py` | páginas estáticas com JSON-LD para o teste de homologação/probe |

Nenhuma migração é esperada: o coletor produz `SourceRun`/`RawItem` pelo fluxo já
existente e usa `evidence_status` já presente em `source_definition`
(`ck_source_definition_evidence_status`, `acquisition/models.py:33-36`).

## Interfaces

```python
# src/opportunity_radar/acquisition/jobposting.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobPostingFields:
    """O que o JSON-LD separa, sem inferência: ausência é UNKNOWN, não vazio."""

    identifier: str | None
    title: str | None
    description_html: str | None
    hiring_organization_name: str | None
    apply_url: str | None
    date_posted: "datetime | None"
    valid_through: "datetime | None"
    employment_type: str | None
    job_location_text: str | None            # jobLocation
    job_location_type: str | None             # jobLocationType ("TELECOMMUTE" | None)
    applicant_location_requirements: tuple[str, ...]  # países/regiões declarados
    base_salary_min: "Decimal | None"
    base_salary_max: "Decimal | None"
    base_salary_currency: str | None
    base_salary_unit: str | None              # "HOUR" | "YEAR" | ...


class JobPostingCollector:
    source_type = "jobposting"
    capabilities: "CollectorCapabilities"  # direct_input=False, keyword_search=False

    async def healthcheck(self, context: "HealthcheckContext | None" = None) -> "HealthResult": ...
    def discover(self, request: "CollectionRequest") -> "AsyncIterator[CollectedItem]": ...


def extract_job_postings(html: str, *, page_url: str) -> list[JobPostingFields]:
    """Lê JSON-LD `JobPosting` em objeto, lista ou `@graph`. Lança `AcquisitionError`
    com `PARSER_SCHEMA_CHANGED` quando não há marcação compatível, challenge, login,
    HTML vazio ou soft-404 — nunca devolve lista vazia como sucesso."""


def job_posting_metadata_v1(fields: JobPostingFields) -> dict[str, object]:
    """Serializa `JobPostingFields` para `CollectedItem.metadata['job_posting_v1']`,
    consumido depois por `opportunities/service.py` na normalização."""
```

## Passos

1. Escrever `tests/e2e/fake_jobposting_site.py` com páginas fixas em pt/en cobrindo:
   `JobPosting` único, lista de `JobPosting`, `@graph`, campos ausentes, schema
   divergente do Schema.org, soft-404 (HTTP 200 com corpo de erro) e página sem
   marcação nenhuma.
2. Escrever `tests/backend/acquisition/test_jobposting_collector.py` primeiro, cobrindo
   os quatro critérios de aceite antes do coletor existir.
3. Implementar `extract_job_postings` (parsing de `<script type="application/ld+json">`,
   suporte a objeto/lista/`@graph`, validação de identidade/empresa/título/link de
   candidatura) — sem headless, sem seletor CSS adivinhado; HTML sem JSON-LD só é
   suportado com um mapeamento por site versionado e sua fixture própria.
4. Separar `job_location_text`/`job_location_type`/`applicant_location_requirements` em
   campos distintos (nunca inferir residência global a partir de "remote"); alimentar
   `opportunities/regions.py:resolve_allowed_countries` só na normalização, não aqui.
5. Implementar `job_posting_metadata_v1` e emitir `CollectedItem` com
   `metadata={"job_posting_v1": ...}`, preservando `UNKNOWN` (campo ausente) em vez de
   valor inventado.
6. Implementar `JobPostingCollector.discover`, preferindo API/feed já homologado quando
   a configuração indicar um (a SPEC pede essa ordem de preferência); mapear challenge,
   login, HTML vazio e soft-404 para `AcquisitionErrorCode.PARSER_SCHEMA_CHANGED` via
   `request.telemetry.record_invalid_item`, nunca como sucesso vazio.
7. Adicionar `"jobposting"` a `PROBE_TYPES`/`probe_request` (`acquisition/probing.py`) e
   registrar o coletor em `acquisition/registry.py`.
8. Conferir que a homologação (`SourceCreateForm`/fluxo de sonda) exercita o coletor
   real contra a fixture, sem atalho de implementação fora do fluxo normal.
9. Rodar o comando de verificação e confirmar os quatro critérios de aceite.

## Testes a escrever

- `tests/backend/acquisition/test_jobposting_collector.py::test_object_list_and_graph_produce_items_with_provenance` — as três formas de JSON-LD geram `CollectedItem`s equivalentes com origem registrada.
- `tests/backend/acquisition/test_jobposting_collector.py::test_blocked_page_is_not_empty_success` — challenge/login/HTML vazio resultam em item inválido registrado, nunca em `discover` vazio bem-sucedido.
- `tests/backend/acquisition/test_jobposting_collector.py::test_telecommute_does_not_imply_global_eligibility` — `jobLocationType=TELECOMMUTE` sem `applicantLocationRequirements` não gera países permitidos por inferência.
- `tests/backend/acquisition/test_jobposting_collector.py::test_probe_exercises_real_collector` — `run_probe("jobposting", ...)` chama `JobPostingCollector.discover` de fato, contra a fixture.
- `tests/backend/acquisition/test_jobposting_collector.py::test_soft_404_is_flagged_not_persisted` — corpo de erro com HTTP 200 não gera `CollectedItem`.

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI; usar `httpx.MockTransport` ou os servidores falsos de `tests/e2e/`.
- Não adicionar dependência nova sem registrar o motivo no PR.
- Não usar LLM neste card, salvo quando a seção "Ajustes da Fase 20" disser o contrário.

## Como trabalhar este card

1. Ler "Ajustes da Fase 20" primeiro: eles prevalecem sobre o texto herdado.
2. Ler "Arquivos prováveis" e confirmar cada caminho com `ls`/`grep` antes de editar; caminho inexistente vira nota no PR.
3. Escrever primeiro os testes dos critérios de aceite, depois o código.
4. IDs antigos no texto aparecem como `F20-xx (antigo F1x-yy)`; a tabela completa está no README da Fase 20.
5. O que depende do acervo real ("Máquina de referência") é medido fora do CI e colado no PR.

## Comando de verificação

```bash
docker compose -p f20-37 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_jobposting_collector.py
docker compose -p f20-37 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-37 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
