# CARD F20-42 — Cliente Tavily e configuração

- **Status:** Feito
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** E — Tavily
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F19-01](../../42-roadmap-tavily/fase-19/f19-01-cliente-e-configuracao.md); [SPEC 41](../../41-spec-tavily.md)

## Ajustes da Fase 20

- Sem mudança de escopo. A Tavily é busca e extração, não LLM; o orçamento de créditos é separado da quota do Groq.

## Resultado

O backend consegue chamar `POST /search` e `POST /extract` da Tavily pelo `httpx`
existente, com autenticação, retry, telemetria e mapeamento de erro no mesmo padrão de
`acquisition/remotive.py`, e sem chave configurada a fonte se declara bloqueada por
configuração em vez de falhar.

## Contexto

Nenhum coletor de descoberta ou orçamento de crédito tem o que chamar sem isso. É a base
de toda a fase, por isso não depende de nenhum outro card.

## Escopo

- `TAVILY_API_KEY: str | None` em `Settings` (`platform/config.py`), opcional, sem
  padrão — presença determina se a fonte participa das execuções.
- `tavily_base_url: str = "https://api.tavily.com"`, `tavily_search_depth: str = "basic"`,
  `tavily_extract_depth: str = "basic"`, `tavily_extract_format: str = "markdown"`,
  configuráveis mas com o padrão de menor custo; `auto_parameters` nunca é enviado.
- Cliente HTTP para `/search` e `/extract`: `Authorization: Bearer <TAVILY_API_KEY>`,
  timeout explícito, retry com `Retry-After` para 429 (mesmo cálculo de
  `remotive.py:_retry_delay`), telemetria via `CollectionTelemetry` existente.
- Mapeamento de `AcquisitionErrorCode` conforme a SPEC §4: 401→`SOURCE_UNAUTHORIZED`,
  403→`SOURCE_FORBIDDEN`, 429→`SOURCE_RATE_LIMITED` (retryable), 5xx→`SOURCE_SERVER_ERROR`
  (retryable), timeout→`SOURCE_TIMEOUT`, transporte→`UNKNOWN_EXTERNAL_ERROR`, JSON/schema
  inválido→`PARSER_SCHEMA_CHANGED`, 432→`INVALID_CONFIGURATION` com `field` do parâmetro.
- Decisão registrada no PR para 433: acrescentar `AcquisitionErrorCode.SOURCE_QUOTA_EXHAUSTED`
  ao enum (retryable=false) ou usar `SOURCE_FORBIDDEN` como aproximação documentada — a
  SPEC §4 e §9 deixam as duas opções abertas; este card decide e registra o porquê.
- Leitura do bloco `usage`/créditos de cada resposta (`include_usage=true` sempre
  enviado), exposta para o F20-43 (antigo F19-03) consumir sem reimplementar o parsing.
- Sem `TAVILY_API_KEY`: o `healthcheck()` do cliente/coletor devolve
  `HealthResult(healthy=True, summary="Tavily bloqueada por configuração: TAVILY_API_KEY ausente")`,
  seguindo o precedente de `source_alert_webhook_url` vazio (`config.py`) — ausência
  configurada não é falha de execução.

## Fora de escopo

- O collector de descoberta em si (F20-44 (antigo F19-02)).
- Orçamento de créditos por execução e persistência em `SourceRun` (F20-43 (antigo F19-03)).
- Extração de conteúdo e cache por URL (F20-45 (antigo F19-04)).

## Notas de implementação

- Seguir a forma de `RemotiveCollector.__init__` (client/client_factory injetáveis,
  `max_retries`, `sleeper`) para manter os testes determinísticos sem `asyncio.sleep`
  real.
- `auto_parameters` fica de fora do payload por padrão — não é um campo com valor
  `False` enviado, é a ausência do campo, para não depender do comportamento da API
  para um parâmetro que ela nem espera receber quando omitido.
- `include_usage=true` é obrigatório em toda chamada; não é uma opção de configuração.

## Critérios de aceite

- [ ] Chamada autenticada a `/search` e `/extract` com os parâmetros da SPEC §3.
- [ ] 401/403/429/5xx/timeout/transporte/schema mapeiam para os códigos da tabela.
- [ ] 432 mapeia para `INVALID_CONFIGURATION` com `field` preenchido.
- [ ] 433 tem mapeamento decidido e documentado no PR (código novo ou aproximação).
- [ ] Sem `TAVILY_API_KEY`, o healthcheck relata bloqueio por configuração, não erro.
- [ ] `auto_parameters` nunca é enviado ativo em nenhuma chamada.
- [ ] Toda resposta lê o bloco de créditos quando presente.

## Verificação

- **CI:** testes com `httpx.MockTransport` cobrindo cada código HTTP da tabela, retry com
  `Retry-After` numérico e em formato de data, healthcheck sem chave configurada.
- **Máquina de referência:** nenhuma chamada real à Tavily; smoke manual documentado na
  SPEC §8 fica fora do CI.

## Arquivos prováveis

- `src/opportunity_radar/platform/config.py`
- `src/opportunity_radar/acquisition/tavily.py` (novo)
- `tests/acquisition/test_tavily*.py` (novos)

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/platform/config.py` | campos `tavily_*` novos em `Settings` (ver Interfaces); segue o padrão de `groq_api_key: SecretStr = SecretStr("")` já decidido pelo F20-08 (`docs/44-roadmap-fase-20/fase-20/f20-08-configuracao-e-segredos.md`) |
| Alterar (condicional) | `src/opportunity_radar/acquisition/domain.py` | `AcquisitionErrorCode.SOURCE_QUOTA_EXHAUSTED` novo, só se a decisão do §4/§9 da SPEC 41 for pelo código novo em vez da aproximação com `SOURCE_FORBIDDEN` |
| Criar | `src/opportunity_radar/acquisition/tavily.py` | `TavilyClient`, dataclasses de request/response, mapeamento de erro |
| Criar | `tests/backend/acquisition/test_tavily_client.py` | testes deste card (o caminho real de testes de coletor é `tests/backend/acquisition/`, não `tests/acquisition/` como o texto herdado abaixo sugere — confirmado com `ls tests/backend/acquisition/test_remotive_collector.py`) |
| Alterar | `.env.example` | `TAVILY_API_KEY=` vazio e demais variáveis `TAVILY_*` |

## Interfaces

```python
# platform/config.py — campos novos em Settings (nomes = variáveis de ambiente),
# mesmo padrão de SecretStr("") que o F20-08 já fixa para groq_api_key
tavily_api_key: SecretStr = SecretStr("")
tavily_base_url: str = "https://api.tavily.com"
tavily_search_depth: str = "basic"      # nunca "advanced" sem medição (SPEC 41 §2)
tavily_extract_depth: str = "basic"
tavily_extract_format: str = "markdown"
tavily_timeout_seconds: float = 15.0
tavily_connect_timeout_seconds: float = 5.0
tavily_max_retries: int = 2
tavily_retry_after_seconds: float = 1.0

# acquisition/tavily.py
@dataclass(frozen=True, slots=True)
class TavilySearchParams:
    query: str
    search_depth: str = "basic"
    max_results: int = 5
    topic: str = "general"
    time_range: str | None = None          # nunca None de fato quando chamado (SPEC §5)
    include_domains: tuple[str, ...] = ()
    exclude_domains: tuple[str, ...] = ()
    include_raw_content: bool = False
    # auto_parameters nunca aparece aqui: é ausência de campo, não `False` explícito.

@dataclass(frozen=True, slots=True)
class TavilyUsage:
    # a confirmar: nome exato da chave de créditos dentro do bloco "usage" da resposta —
    # a referência da API (docs.tavily.com) documenta que o bloco existe e que cada
    # chamada com include_usage=true devolve custo, mas não publica o esquema exato do
    # objeto "usage" na página de referência consultada em 2026-09-25.
    raw: Mapping[str, Any]

    @property
    def credits(self) -> int | None: ...  # extrai a chave confirmada na implementação

@dataclass(frozen=True, slots=True)
class TavilySearchResult:
    title: str | None
    url: str
    content: str | None
    score: float | None
    raw_content: str | None
    published_date: str | None

@dataclass(frozen=True, slots=True)
class TavilySearchResponse:
    query: str
    results: tuple[TavilySearchResult, ...]
    response_time: float | None
    usage: TavilyUsage | None
    raw_payload: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class TavilyExtractItem:
    url: str
    raw_content: str | None
    error: str | None  # preenchido quando o item vem de "failed_results"

@dataclass(frozen=True, slots=True)
class TavilyExtractResponse:
    results: tuple[TavilyExtractItem, ...]
    failed_results: tuple[TavilyExtractItem, ...]
    usage: TavilyUsage | None
    raw_payload: Mapping[str, Any]

class TavilyClient:
    """Mesma forma de RemotiveCollector.__init__ (remotive.py:33-59): client/client_factory
    injetáveis, max_retries, sleeper — testes determinísticos sem asyncio.sleep real."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        client_factory: (
            Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]] | None
        ) = None,
        max_retries: int = 2,
        retry_after_seconds: float = 1.0,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None: ...

    async def search(
        self, params: TavilySearchParams, *, telemetry: CollectionTelemetry
    ) -> TavilySearchResponse: ...

    async def extract(
        self,
        urls: Sequence[str],
        *,
        extract_depth: str = "basic",
        format: str = "markdown",
        telemetry: CollectionTelemetry,
    ) -> TavilyExtractResponse: ...

    async def healthcheck(self) -> HealthResult:
        """Sem `tavily_api_key`, devolve HealthResult(healthy=True, summary="Tavily
        bloqueada por configuração: TAVILY_API_KEY ausente") — nunca chama a API."""
```

## Exemplos

`POST /search` (SPEC 41 §3.1; parâmetros confirmados em 2026-09-25 contra
`https://docs.tavily.com/documentation/api-reference/endpoint/search`):

```json
{
  "query": "backend engineer remote brazil",
  "search_depth": "basic",
  "max_results": 5,
  "topic": "general",
  "time_range": "week",
  "include_domains": ["boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com"],
  "include_raw_content": false,
  "include_usage": true
}
```

Resposta 200 (campos confirmados na referência oficial; `auto_parameters` e `usage` só
aparecem quando pedidos/aplicáveis):

```json
{
  "query": "backend engineer remote brazil",
  "results": [
    {
      "title": "Backend Engineer (Remote, Brazil)",
      "url": "https://boards.greenhouse.io/acme/jobs/12345",
      "content": "We are hiring a backend engineer...",
      "score": 0.87,
      "raw_content": null,
      "published_date": "2026-09-20"
    }
  ],
  "response_time": 1.2,
  "usage": {"...": "a confirmar — ver TavilyUsage acima"},
  "request_id": "..."
}
```

`POST /extract` (SPEC 41 §3.2; confirmado contra
`https://docs.tavily.com/documentation/api-reference/endpoint/extract`):

```json
{
  "urls": ["https://boards.greenhouse.io/acme/jobs/12345"],
  "extract_depth": "basic",
  "format": "markdown",
  "include_usage": true
}
```

Resposta 200:

```json
{
  "results": [
    {"url": "https://boards.greenhouse.io/acme/jobs/12345", "raw_content": "# Backend Engineer\n..."}
  ],
  "failed_results": [],
  "response_time": 0.8,
  "usage": {"...": "a confirmar — ver TavilyUsage acima"},
  "request_id": "..."
}
```

Erros HTTP 432/433 não têm corpo de exemplo publicado na referência consultada;
tratá-los pelo código de status apenas (SPEC 41 §4), sem depender do corpo.

## Passos

1. Escrever `tests/backend/acquisition/test_tavily_client.py` cobrindo cada item de
   "Critérios de aceite" (ver "Testes a escrever") — falham até o cliente existir.
2. Adicionar os campos `tavily_*` em `Settings` (`platform/config.py`), incluindo
   `tavily_api_key: SecretStr = SecretStr("")`.
3. Decidir 433 → `SOURCE_QUOTA_EXHAUSTED` (novo) ou `SOURCE_FORBIDDEN` (aproximação);
   se novo, adicionar o membro ao `AcquisitionErrorCode` em `domain.py` e registrar a
   escolha no PR.
4. Criar `acquisition/tavily.py` com os dataclasses de request/response.
5. Implementar `TavilyClient.__init__` espelhando `RemotiveCollector.__init__`
   (`remotive.py:33-59`).
6. Implementar uma chamada HTTP autenticada genérica (`Authorization: Bearer ...`,
   `include_usage=true` sempre, sem `auto_parameters`), com retry usando
   `Retry-After` no mesmo cálculo de `remotive.py:_retry_delay` (linhas ~201-224).
7. Implementar o mapeamento de status HTTP → `AcquisitionErrorCode` da tabela da SPEC
   41 §4, incluindo 432 → `INVALID_CONFIGURATION` com `field`.
8. Implementar `search()` montando o payload de `TavilySearchParams` e parseando a
   resposta em `TavilySearchResponse`.
9. Implementar `extract()` para uma lista de URLs (o particionamento em lotes de 20 é
   do F20-45; aqui só a chamada e o parsing).
10. Implementar `TavilyUsage` tolerante a bloco ausente (confirmar a chave real do
    crédito ao implementar, contra uma resposta real ou a referência oficial).
11. Implementar `healthcheck()` checando `tavily_api_key.get_secret_value()` vazio.
12. Atualizar `.env.example` com `TAVILY_API_KEY=` vazio e as demais variáveis.
13. Rodar os testes até verdes; depois `ruff check .` e `mypy`.

## Testes a escrever

`tests/backend/acquisition/test_tavily_client.py`:

- `test_search_sends_authenticated_request_without_auto_parameters` — cobre "Chamada
  autenticada a `/search`... e "`auto_parameters` nunca é enviado ativo".
- `test_search_always_includes_usage_true` — cobre "Toda resposta lê o bloco de
  créditos quando presente".
- `test_extract_sends_basic_depth_and_markdown_format` — cobre "Chamada autenticada a
  ... `/extract`".
- `test_maps_401_to_unauthorized`, `test_maps_403_to_forbidden`,
  `test_maps_429_to_rate_limited_with_retry_after` (numérico e em formato de data),
  `test_maps_5xx_to_server_error`, `test_maps_timeout_to_source_timeout`,
  `test_maps_transport_error_to_unknown_external_error`,
  `test_maps_invalid_json_to_parser_schema_changed` — cobrem "401/403/429/5xx/timeout/
  transporte/schema mapeiam para os códigos da tabela".
- `test_maps_432_to_invalid_configuration_with_field` — cobre "432 mapeia para
  `INVALID_CONFIGURATION` com `field` preenchido".
- `test_maps_433_per_decision` — cobre "433 tem mapeamento decidido e documentado no
  PR", parametrizado pela decisão tomada no passo 3.
- `test_healthcheck_without_api_key_reports_blocked_by_configuration` — cobre "Sem
  `TAVILY_API_KEY`, o healthcheck relata bloqueio por configuração".
- `test_healthcheck_with_api_key_reports_healthy`.
- `test_settings_tavily_api_key_defaults_to_empty_secret` — usa
  `Settings(_env_file=None, database_url="...")` como o F20-08 já recomenda, nunca lê
  `.env` real.

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
docker compose -p f20-42 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_tavily_client.py
docker compose -p f20-42 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-42 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
