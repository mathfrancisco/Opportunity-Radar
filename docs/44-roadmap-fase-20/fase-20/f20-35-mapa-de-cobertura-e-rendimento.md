# CARD F20-35 — Mapa de cobertura e rendimento

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-01, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-01](../../40-roadmap-varredura-produtiva/fase-18/f18-01-mapa-de-cobertura-e-rendimento.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

Cada empresa mostra se está coberta, por que não está e qual é a próxima ação. O operador mede vagas únicas úteis por custo e atraso.

## Escopo

- Estender search-metrics com funil catálogo → descoberta → homologação → habilitação → coleta completa recente, contando empresas canônicas.
- Separar cobertura cadastrada de operacional e tipos ATS sem coletor. Guardar motivo, última tentativa e próxima ação por lacuna.
- Medir requisições, bytes, erros, vagas únicas novas, suporte de julgamento, rendimento útil, frescor e atraso de processamento; sem datas confiáveis, atraso de descoberta é null.
- Atribuição multifuente separa primeira descoberta e contribuição. Marcas ausentes não são negativas; comparar coortes/janelas iguais.
- Registrar baseline de sete dias e metas/tetos antes da mudança. Recall amostral usa snapshots manuais de boards estratificados, sem prometer recall global.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Fonte habilitada falhando não conta como operacional.
- [ ] Aliases e oportunidades multifuente não inflam totais.
- [ ] Cada métrica expõe janela, denominador, suporte e null quando indisponível.
- [ ] Relatório registra baseline, lacunas acionáveis e plano de comparação.

## Verificação

- **CI:** Fixtures de fontes saudáveis/falhas, aliases, multifuente, datas ausentes e marcas parciais; endpoint e apresentação no painel.
- **Máquina de referência:** Relatório de baseline e amostra manual dos boards; não executar nesta tarefa documental.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`dashboard/metrics.py`, `dashboard/queries.py`, API de dashboard, telas de empresas/fontes, migrations de métricas quando necessário.

## Contexto no código

`dashboard/queries.py:942-` (`search_metrics`) e `dashboard/metrics.py` já cobrem parte do
que o card pede, mas nenhum dos dois soma o funil completo por empresa canônica:

- `_companies_coverage` (`dashboard/queries.py:868-886`) só devolve dois números:
  empresas com pelo menos uma `SourceDefinitionModel.enabled` (via
  `CompanySource.company_id`) e empresas com `CompanySource.source_type` num ATS
  conhecido. Não distingue catalogada → endpoint descoberto → homologado → habilitado
  → coleta completa recente, que é exatamente o funil pedido na SPEC 39 §4.
- `dashboard/metrics.py:_coverage_state` (linhas 216-238) já decide, por fonte, se ela
  está `NOT_ENABLED`, `CONFIGURATION_BLOCKED` (falta `evidence_status == "confirmed"` +
  `reviewed_at` + `terms_reviewed` + `collector_local_tested`), `NOT_SCHEDULED`,
  `NOT_RUN` ou o status do último run — essa é a lógica de homologação que o funil de
  empresa deve reaproveitar, só que hoje ela roda por fonte, não por empresa canônica.
- `SourceRunModel.complete` e `items_announced` (migração
  `20260925_0025_run_completeness_and_last_seen.py`) já existem e são o critério de
  "coleta completa recente" — nenhuma consulta atual os usa para o funil.
- `SourceDefinitionModel.company_source_id` (`acquisition/models.py:45-48`) liga a fonte à
  `CompanySource`, que liga à `Company` canônica (`companies/models.py:26-56`,
  `81-125`) — é o join que falta para agrupar por empresa em vez de por fonte.
- `SourceMetricsReport`/`SourceWindowMetrics` (`dashboard/metrics.py:73-120`) já expõem
  janela (`METRIC_WINDOWS = {"24h", "7d"}`), mas por fonte; o card pede o mesmo tipo de
  transparência (janela, denominador, suporte, null quando indisponível) por empresa e
  por funil, não substituindo o que já existe.
- Atribuição multifuente: `SourceOccurrenceModel` (`opportunities/models.py:199-`) tem
  `raw_item_id` único — uma oportunidade pode ter várias `SourceOccurrence`s (uma por
  fonte que a viu), então "primeira descoberta" é o `first_seen_at` mínimo entre elas e
  "contribuição" é a contagem por fonte; hoje não há consulta que separe as duas.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/dashboard/metrics.py` | expor `_coverage_state` para reuso por empresa (extrair função pura) |
| Alterar | `src/opportunity_radar/dashboard/queries.py` | `company_coverage_funnel`, substituindo/estendendo `_companies_coverage` |
| Alterar | `src/opportunity_radar/presentation/http/dashboard.py` | novo bloco no `GET /search-metrics` com o funil e rendimento útil |
| Criar | `tests/backend/dashboard/test_coverage_funnel.py` | fixtures de fontes saudáveis/falhas, aliases, multifuente, datas ausentes |

Nenhuma migração nova é esperada: o funil é lido de colunas e tabelas já existentes
(`source_definition`, `company_source`, `company`, `source_run.complete`). Se a
apuração de atraso de descoberta precisar de uma coluna nova em `opportunity` ou
`source_occurrence`, registrar a necessidade no PR em vez de expandir o escopo aqui.

## Interfaces

```python
# src/opportunity_radar/dashboard/queries.py
@dataclass(frozen=True, slots=True)
class CompanyFunnelStage:
    stage: str  # "cataloged" | "endpoint_discovered" | "homologated" | "enabled" | "collected_recently"
    companies: int
    # Denominador do estágio anterior no funil; None só no primeiro estágio.
    of_previous: int | None


@dataclass(frozen=True, slots=True)
class CompanyCoverageFunnel:
    window_days: int
    generated_at: datetime
    canonical_companies_total: int
    stages: tuple[CompanyFunnelStage, ...]
    #: Empresas com fonte habilitada cuja última execução falhou — não contam como
    #: operacionais mesmo estando "enabled" (critério de aceite 1).
    enabled_but_unhealthy: int


@dataclass(frozen=True, slots=True)
class UsefulYieldMetric:
    window_days: int
    requests: int
    new_unique_opportunities: int
    #: None quando a amostra de julgamento é pequena demais para sustentar a taxa.
    judged_relevant: int | None
    judgement_rate: Decimal | None
    yield_per_100_requests: Decimal | None
    #: None quando nenhuma data de publicação da fonte é confiável (SPEC 39 §4).
    discovery_delay_p50_seconds: float | None
    discovery_delay_p95_seconds: float | None


def company_coverage_funnel(
    session: Session, *, window_days: int = 7, now: datetime | None = None,
) -> CompanyCoverageFunnel: ...


def useful_yield_metrics(
    session: Session, *, window_days: int = 7, now: datetime | None = None,
) -> UsefulYieldMetric: ...
```

## Passos

1. Escrever `tests/backend/dashboard/test_coverage_funnel.py` primeiro, com fixtures
   para: empresa só catalogada, empresa com `CompanySource` descoberto mas sem
   homologação, empresa homologada mas `enabled=False`, empresa habilitada com última
   `SourceRunModel` falhando (não deve contar como operacional — critério de aceite 1),
   empresa com `SourceRunModel.complete=True` recente, duas fontes da mesma empresa
   (multifume, não deve inflar o total) e uma empresa sem nenhuma data de publicação
   confiável (atraso de descoberta deve vir `None`).
2. Extrair de `dashboard/metrics.py:_coverage_state` a checagem de homologação
   (`evidence_status`, `reviewed_at`, `terms_reviewed`, `collector_local_tested`) para
   uma função reutilizável (`_is_homologated(source) -> bool`), sem mudar o
   comportamento hoje testado em `tests/backend/dashboard/test_metrics.py`.
3. Implementar `company_coverage_funnel` em `dashboard/queries.py`, substituindo o corpo
   de `_companies_coverage` (mantendo a assinatura pública que o Overview já consome, ou
   ajustando os dois pontos de chamada em `queries.py:617` e `1028`) para agrupar por
   `Company.id` via `CompanySource`/`SourceDefinitionModel` e contar cada estágio do
   funil (catalogada → endpoint descoberto → homologado → habilitado → coleta completa
   recente usando `SourceRunModel.complete`).
4. Implementar `useful_yield_metrics`, reaproveitando `SourceRunModel.http_requests`
   (já persistido) e o total de oportunidades novas únicas por janela; separar
   `discovery_delay_p50/p95_seconds` como `None` quando a fonte não tem
   `published_at` confiável.
5. Adicionar o bloco de resposta em `presentation/http/dashboard.py:417-428` (endpoint
   `GET /search-metrics`) sem remover os campos que a Fase 17 já consome.
6. Registrar, no corpo do PR (não em código), o baseline de sete dias pedido no critério
   de aceite 4 — esta tarefa é documental/de instrumentação, não de coleta real.
7. Rodar o comando de verificação abaixo e conferir os quatro critérios de aceite.

## Testes a escrever

- `tests/backend/dashboard/test_coverage_funnel.py::test_funnel_counts_each_stage_once_per_canonical_company` — duas `CompanySource` da mesma `Company` não duplicam a contagem em nenhum estágio.
- `tests/backend/dashboard/test_coverage_funnel.py::test_enabled_source_with_failing_run_is_not_operational` — fonte habilitada cuja última execução falhou não conta como coleta completa recente (critério de aceite 1).
- `tests/backend/dashboard/test_coverage_funnel.py::test_multisource_opportunity_counts_once` — oportunidade vista por dois coletores da mesma empresa conta uma vez no total, com primeira descoberta e contribuição separadas (critério de aceite 2).
- `tests/backend/dashboard/test_coverage_funnel.py::test_metrics_expose_window_denominator_support_and_null` — cada métrica do relatório expõe `window_days`, denominador e vem `None` quando a data de publicação não é confiável (critério de aceite 3).
- `tests/backend/dashboard/test_coverage_funnel.py::test_endpoint_reports_funnel_block` — `GET /search-metrics` inclui o bloco novo sem remover os campos existentes.

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
docker compose -p f20-35 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/dashboard/test_coverage_funnel.py tests/backend/dashboard/test_metrics.py tests/backend/dashboard/test_queries.py
docker compose -p f20-35 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-35 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
