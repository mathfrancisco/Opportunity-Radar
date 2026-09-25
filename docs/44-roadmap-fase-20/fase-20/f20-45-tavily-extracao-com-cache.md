# CARD F20-45 — Extração de conteúdo com cache

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** E — Tavily
- **Depende de:** F20-44
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F19-04](../../42-roadmap-tavily/fase-19/f19-04-extracao-com-cache.md); [SPEC 41](../../41-spec-tavily.md)

## Ajustes da Fase 20

- Sem mudança de escopo. A Tavily é busca e extração, não LLM; o orçamento de créditos é separado da quota do Groq.
- A descrição extraída passa pelo limpador e pelo Token Guard (F20-13) antes de qualquer análise no Groq.

## Resultado

Postagens sem descrição — da própria Tavily ou de outra fonte — ganham corpo via
`POST /extract`, e a mesma URL nunca é extraída duas vezes: uma vez por URL, para
sempre, dentro da validade do cache.

## Contexto

O `TavilySearchCollector` (F20-44 (antigo F19-02)) usa um trecho curto de `content` como descrição
provisória; a extração completa custa crédito à parte e só compensa para URLs que
realmente ficaram sem corpo depois da normalização.

## Escopo

- Rotina que recebe uma lista de URLs sem descrição (do resultado da Tavily ou de
  qualquer `CollectedItem` de outra fonte que chegou sem corpo) e chama `/extract` em
  lotes de até 20 URLs, `extract_depth="basic"`, `format="markdown"`.
- Cache por hash da URL canônica (mesma normalização do dedupe do F20-44 (antigo F19-02)): hit não gera
  chamada nova; miss chama, grava o resultado e o hash antes de devolver.
- Validade do cache configurável; entrada expirada é tratada como miss, não como erro.
- Falha de extração para uma URL específica dentro de um lote não derruba as demais —
  cada URL do lote tem resultado próprio (sucesso, falha, sem conteúdo).
- Créditos gastos na extração entram no mesmo acumulador do F20-43 (antigo F19-03) (1 crédito a cada 5
  URLs bem-sucedidas em `basic`).

## Fora de escopo

- `extract_depth="advanced"` como padrão — fica reservado a medição futura (SPEC §10).
- Extrair URL que já tem descrição suficiente — critério de "sem descrição" é definido
  pela normalização existente, não reavaliado aqui.
- Servir o cache para outros consumidores fora da extração Tavily.

## Notas de implementação

- Reusar a função de normalização de URL do F20-44 (antigo F19-02) para o hash do cache — a mesma URL
  não pode cair em duas entradas por causa de diferença de query string ou caixa.
- O lote de até 20 URLs por chamada é limite da API, não escolha do radar; a rotina
  particiona listas maiores automaticamente.
- Erro de item dentro de um lote de sucesso parcial usa o mesmo `AcquisitionErrorCode`
  por item que os coletores já aplicam a item inválido (`INVALID_ITEM`/
  `PARSER_SCHEMA_CHANGED`, conforme a causa), sem falhar a chamada inteira.

## Critérios de aceite

- [ ] Uma URL nunca gera duas chamadas de extração bem-sucedidas dentro da validade do
      cache.
- [ ] Cache expirado é tratado como miss, com nova chamada e novo registro.
- [ ] Lote de 20 URLs com uma falha isolada preserva o resultado das demais 19.
- [ ] Créditos gastos na extração aparecem no acumulador do F20-43 (antigo F19-03).
- [ ] Markdown extraído substitui a descrição provisória quando presente.

## Verificação

- **CI:** teste de cache hit/miss/expirado com `httpx.MockTransport`; teste de lote
  particionado acima de 20 URLs; teste de falha isolada dentro de um lote; teste de
  soma de créditos compartilhada com F20-43 (antigo F19-03).
- **Máquina de referência:** sem chamada real à Tavily.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/tavily.py`
- `src/opportunity_radar/acquisition/models.py` (tabela/coluna de cache, se persistida)
- `tests/acquisition/test_tavily_extract_cache.py` (novo)

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/acquisition/tavily.py` | `TavilyExtractionCache`, rotina de extração em lote |
| Alterar | `src/opportunity_radar/acquisition/models.py` | `TavilyExtractCacheModel` (tabela nova) |
| Criar | `migrations/versions/20260926_0051_tavily_extract_cache.py` | `down_revision = "20260926_0050"` (a migração do F20-43); numeração 0050+ é indicativa |
| Criar | `tests/backend/acquisition/test_tavily_extract_cache.py` | testes deste card (não `tests/acquisition/`, ver nota do F20-42) |

## Interfaces

```python
# acquisition/models.py — tabela nova, schema "acquisition" como as demais deste módulo
class TavilyExtractCacheModel(Base):
    __tablename__ = "tavily_extract_cache"
    __table_args__ = ({"schema": "acquisition"},)

    # hash sha256 de canonicalize_url(url) (F20-44) — mesma normalização do dedupe,
    # para que a mesma URL nunca caia em duas entradas por diferença de query/caixa.
    url_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "success"|"failed"
    error: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

# acquisition/tavily.py
@dataclass(frozen=True, slots=True)
class ExtractionResult:
    url: str
    raw_content: str | None
    error: str | None          # AcquisitionErrorCode.value quando a URL falhou no lote
    from_cache: bool

class TavilyExtractionCache:
    def __init__(self, *, session: Session, ttl_seconds: int) -> None: ...
    def get(self, url: str) -> ExtractionResult | None: ...  # None = miss ou expirado
    def put(self, url: str, result: ExtractionResult) -> None: ...

async def extract_missing_descriptions(
    client: TavilyClient,
    cache: TavilyExtractionCache,
    urls: Sequence[str],
    *,
    extract_depth: str,
    format: str,
    budget_guard: TavilyBudgetGuard,  # F20-43
    run: SourceRun,
) -> list[ExtractionResult]:
    """Particiona `urls` em lotes de até 20 (limite da API, não escolha do radar),
    consulta o cache antes de cada lote e só chama /extract para os misses."""
    ...
```

## Exemplos

Resposta de `/extract` com sucesso parcial (ver F20-42 seção Exemplos para o corpo
completo; aqui o caso com uma URL em `failed_results`):

```json
{
  "results": [
    {"url": "https://boards.greenhouse.io/acme/jobs/12345", "raw_content": "# Backend Engineer\n..."}
  ],
  "failed_results": [
    {"url": "https://boards.greenhouse.io/acme/jobs/99999", "error": "could not extract content"}
  ],
  "usage": {"...": "a confirmar — ver F20-42"}
}
```

O item com falha isolada não derruba os demais 19 do lote: vira
`ExtractionResult(url=..., raw_content=None, error="could not extract content", from_cache=False)`,
mapeado para `AcquisitionErrorCode.INVALID_ITEM` (ou `PARSER_SCHEMA_CHANGED`, conforme a
causa) na telemetria da execução, sem interromper o lote.

## Passos

1. Escrever `tests/backend/acquisition/test_tavily_extract_cache.py` para cada
   critério de aceite (ver "Testes a escrever") — falham até a rotina existir.
2. Criar a migração `20260926_0051_tavily_extract_cache.py` para a tabela
   `acquisition.tavily_extract_cache`.
3. Adicionar `TavilyExtractCacheModel` em `models.py`.
4. Implementar `TavilyExtractionCache.get`/`put` usando `canonicalize_url()` do F20-44
   para o hash — não duplicar a normalização.
5. Implementar o particionamento em lotes de até 20 URLs em
   `extract_missing_descriptions()`.
6. Para cada lote: separar hits (retornam do cache sem chamada) de misses; chamar
   `TavilyClient.extract()` do F20-42 só para os misses.
7. Gravar cada resultado do lote (sucesso ou falha) no cache antes de devolver,
   inclusive falhas — uma URL que falhou não deve ser tentada de novo dentro da
   validade do cache se a política decidir cachear falha (registrar a escolha no PR;
   caso contrário, falha não entra no cache e a próxima execução tenta de novo).
8. Somar o custo da chamada ao acumulador do `SourceRun` via o `TavilyBudgetGuard` do
   F20-43 (1 crédito a cada 5 URLs bem-sucedidas em `basic`, conforme SPEC 41 §3.2).
9. Tratar cache expirado como miss (comparar `expires_at` com o relógio atual antes de
   usar a entrada).
10. Substituir a descrição provisória do `CollectedItem` (F20-44) pelo `raw_content`
    extraído quando presente.
11. Rodar os testes até verdes; `ruff check .`; `mypy`.

## Testes a escrever

`tests/backend/acquisition/test_tavily_extract_cache.py`:

- `test_url_extracted_once_stays_cached_within_ttl` — cobre "Uma URL nunca gera duas
  chamadas de extração bem-sucedidas dentro da validade do cache".
- `test_expired_cache_entry_is_treated_as_miss_and_recorded_again` — cobre "Cache
  expirado é tratado como miss, com nova chamada e novo registro".
- `test_batch_over_twenty_urls_is_partitioned` — cobre o particionamento em lotes.
- `test_isolated_failure_in_batch_preserves_other_nineteen_results` — cobre "Lote de
  20 URLs com uma falha isolada preserva o resultado das demais 19".
- `test_extraction_credits_feed_the_shared_run_accumulator` — cobre "Créditos gastos
  na extração aparecem no acumulador do F20-43".
- `test_extracted_markdown_replaces_provisional_description` — cobre "Markdown
  extraído substitui a descrição provisória quando presente".

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
docker compose -p f20-45 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_tavily_extract_cache.py
docker compose -p f20-45 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-45 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
