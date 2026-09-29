# CARD F19-01 — Cliente Tavily e configuração

- **Status:** Backlog
- **Fase:** 19 — Integração Tavily
- **Depende de:** Nenhum
- **Bloqueia:** F19-02, F19-03, F19-04
- **Origem:** [SPEC 41](../../41-spec-tavily.md), §2, §3, §4

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
  enviado), exposta para o F19-03 consumir sem reimplementar o parsing.
- Sem `TAVILY_API_KEY`: o `healthcheck()` do cliente/coletor devolve
  `HealthResult(healthy=True, summary="Tavily bloqueada por configuração: TAVILY_API_KEY ausente")`,
  seguindo o precedente de `source_alert_webhook_url` vazio (`config.py`) — ausência
  configurada não é falha de execução.

## Fora de escopo

- O collector de descoberta em si (F19-02).
- Orçamento de créditos por execução e persistência em `SourceRun` (F19-03).
- Extração de conteúdo e cache por URL (F19-04).

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
