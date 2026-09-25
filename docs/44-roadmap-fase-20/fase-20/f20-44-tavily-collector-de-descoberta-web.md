# CARD F20-44 — Collector de descoberta web

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** E — Tavily
- **Depende de:** F20-42, F20-43
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F19-02](../../42-roadmap-tavily/fase-19/f19-02-collector-de-descoberta-web.md); [SPEC 41](../../41-spec-tavily.md)

## Ajustes da Fase 20

- Sem mudança de escopo. A Tavily é busca e extração, não LLM; o orçamento de créditos é separado da quota do Groq.

## Resultado

`TavilySearchCollector` entra no registry como mais uma fonte de busca por palavra-chave,
lado a lado com a Remotive, produzindo `CollectedItem` com procedência e sem duplicar
URLs já vistas.

## Contexto

O radar só encontra vaga onde já sabe procurar: ATS conhecidos e a Remotive. A Tavily
amplia isso sem virar navegador nem substituir coletor nativo — ela busca, o resto do
pipeline (normalização, identidade, matching) trata o resultado como trataria qualquer
outro.

## Escopo

- `TavilySearchCollector` com `source_type = "tavily_search"`,
  `capabilities = CollectorCapabilities(keyword_search=True)`, registrado em
  `acquisition/registry.py`.
- `discover()` monta `query` a partir de `CollectionRequest.keywords`; quando
  configurado, soma `include_domains` com os boards de ATS conhecidos
  (`boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`); usa `time_range`
  configurado (nunca aberto).
- Mapeamento para `CollectedItem`: `url`, `title`, trecho de `content` como
  `description`, `raw_payload` cru. `metadata` carrega `query`, `rank`, `score`,
  `retrieved_at`, `parser_version="tavily-search-v1"`.
- Dedupe por URL canônica (sem query de rastreamento, sem fragmento, host em
  minúsculas) contra os itens já emitidos na execução.
- Resultado cuja URL bate com padrão de board de ATS coberto e cuja empresa não tem
  `CompanySource` habilitada para aquele board recebe
  `metadata["source_proposal_candidate"] = True` em vez de seguir como ingestão comum.
- `healthcheck()` reusa o estado do F20-42 (antigo F19-01) (bloqueado por configuração sem chave).

## Fora de escopo

- Orçamento de créditos e o que acontece quando o teto é atingido (F20-43 (antigo F19-03)).
- Extração de conteúdo completo via `/extract` (F20-45 (antigo F19-04)).
- Criar a `SourceDefinition`/proposta a partir do candidato marcado (F20-46 (antigo F19-05)).
- Filtrar por relevância de área da vaga — fica com a classificação de área já definida
  em `docs/37-spec-busca.md`, Frente F, aplicada depois na normalização.

## Notas de implementação

- Query e `include_domains` seguem a mesma fonte de palavras-chave que a Remotive já usa
  hoje (perfil ativo), sem reimplementar a extração de cargos/skills.
- A normalização de URL do dedupe é a mesma função usada pelo cache de extração do
  F20-45 (antigo F19-04) — extrair para um único lugar compartilhado em vez de duplicar a lógica.
- Item marcado como candidato de proposta ainda é um `CollectedItem` válido; a decisão
  de não ingerir como oportunidade comum é de quem consome o resultado do `discover()`
  no worker, não do coletor recusar emitir.

## Critérios de aceite

- [ ] O coletor está registrado e resolve por `"tavily_search"`.
- [ ] Query inclui as palavras-chave do perfil; `include_domains` aplica quando
      configurado.
- [ ] `time_range` nunca fica aberto.
- [ ] Cada `CollectedItem` carrega `query`, `rank`, `score`, `retrieved_at`,
      `parser_version` em `metadata`.
- [ ] Duas URLs equivalentes (variação de query string/fragmento/caixa) não geram dois
      itens na mesma execução.
- [ ] URL de board de ATS já coberto marca `source_proposal_candidate` em vez de seguir
      como ingestão comum.

## Verificação

- **CI:** testes com `httpx.MockTransport` para resposta de `/search`, fixtures de
  dedupe (URLs equivalentes), fixture de candidato de proposta, teste de registro no
  `CollectorRegistry`.
- **Máquina de referência:** sem chamada real à Tavily.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/tavily.py`
- `src/opportunity_radar/acquisition/registry.py`
- `tests/acquisition/test_tavily_collector.py` (novo)

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/acquisition/tavily.py` | `TavilySearchCollector`, `canonicalize_url()`, `detect_ats_board()` |
| Alterar | `src/opportunity_radar/acquisition/registry.py` | registrar `TavilySearchCollector()` em `build_collector_registry` (`registry.py:14-23`, ao lado de `RemotiveCollector()`) |
| Criar | `tests/backend/acquisition/test_tavily_collector.py` | testes deste card (não `tests/acquisition/`, ver nota do F20-42) |

## Interfaces

```python
# acquisition/tavily.py

def canonicalize_url(url: str) -> str:
    """Sem query de rastreamento, sem fragmento, host em minúsculas — mesma normalização
    usada pelo dedupe daqui e pelo hash de cache do F20-45; um único lugar, não duplicado."""
    ...

# padrão de board por ATS, mesma chave que proposals.py.IDENTIFIER_KEYS usa
# (proposals.py:20-24): ashby -> board_identifier, lever -> site_identifier,
# greenhouse -> board_token.
_ATS_BOARD_PATTERNS: dict[str, re.Pattern[str]] = {
    "ashby": re.compile(r"^jobs\.ashbyhq\.com/([^/?#]+)"),
    "greenhouse": re.compile(r"^boards\.greenhouse\.io/([^/?#]+)"),
    "lever": re.compile(r"^jobs\.lever\.co/([^/?#]+)"),
}

def detect_ats_board(url: str) -> tuple[str, str] | None:
    """(source_type, board_key) se a URL casar com um padrão conhecido, senão None."""
    ...

class TavilySearchCollector:
    source_type = "tavily_search"
    capabilities = CollectorCapabilities(keyword_search=True)

    def __init__(
        self,
        *,
        client: TavilyClient | None = None,
        client_factory: Callable[[], TavilyClient] | None = None,
        settings: TavilySettings,  # tavily_base_url, *_depth, include_domains padrão
        budget_guard: TavilyBudgetGuard | None = None,  # F20-43; None = sem teto aplicado aqui
        known_ats_boards: frozenset[tuple[str, str]] = frozenset(),
        # Pares (source_type, board_key) que JÁ têm CompanySource habilitada. O
        # coletor não tem sessão de banco (nenhum outro Collector tem — Protocol em
        # collectors.py:27-36 só define healthcheck/discover); por isso este conjunto
        # é pré-calculado e injetado por quem monta o registry antes de chamar
        # discover(). A cadência de atualização (por execução vs. por processo) é uma
        # decisão de implementação do worker — a confirmar no PR.
    ) -> None: ...

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult: ...  # reusa o estado do TavilyClient do F20-42

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]: ...
```

## Exemplos

Um resultado de `/search` (ver F20-42, seção Exemplos) virando `CollectedItem`:

```python
CollectedItem(
    source_type="tavily_search",
    url="https://boards.greenhouse.io/acme/jobs/12345",
    title="Backend Engineer (Remote, Brazil)",
    description="We are hiring a backend engineer...",  # trecho de "content"
    raw_payload={"title": "...", "url": "...", "content": "...", "score": 0.87, "...": "..."},
    metadata={
        "query": "backend engineer remote brazil",
        "rank": 0,
        "score": 0.87,
        "retrieved_at": "2026-09-25T12:00:00+00:00",
        "parser_version": "tavily-search-v1",
        "source_proposal_candidate": True,  # greenhouse/acme sem CompanySource habilitada
    },
)
```

## Passos

1. Escrever `tests/backend/acquisition/test_tavily_collector.py` para cada critério de
   aceite (ver "Testes a escrever") — falham até o coletor existir.
2. Implementar `canonicalize_url()` em `tavily.py` (host minúsculo, sem
   query de rastreamento, sem fragmento).
3. Implementar `detect_ats_board()` com os três padrões (`_ATS_BOARD_PATTERNS`).
4. Implementar `TavilySearchCollector.__init__` recebendo `known_ats_boards` e o
   `budget_guard` do F20-43.
5. Implementar `discover()`: montar `TavilySearchParams.query` a partir de
   `request.keywords`; somar `include_domains` com os boards de ATS conhecidos quando
   configurado; `time_range` sempre vindo da configuração.
6. Mapear cada resultado de `/search` para `CollectedItem` com o `metadata` da seção
   Interfaces/Exemplos (`query`, `rank`, `score`, `retrieved_at`, `parser_version`).
7. Aplicar dedupe por `canonicalize_url()` contra os itens já emitidos nesta execução
   (um `set[str]` local ao `discover()`).
8. Para cada item, chamar `detect_ats_board(item.url)`; se casar e o par
   `(source_type, board_key)` não estiver em `known_ats_boards`, marcar
   `metadata["source_proposal_candidate"] = True` em vez de tratar como ingestão
   comum (o item ainda é emitido — quem decide não ingerir é o worker, não o coletor).
9. Implementar `healthcheck()` delegando ao `TavilyClient` do F20-42.
10. Registrar `TavilySearchCollector()` em `build_collector_registry`
    (`registry.py:14-23`).
11. Escrever o teste de registro no `CollectorRegistry` (`resolve("tavily_search")`).
12. Rodar os testes até verdes; `ruff check .`; `mypy`.

## Testes a escrever

`tests/backend/acquisition/test_tavily_collector.py`:

- `test_registered_and_resolves_by_tavily_search` — cobre "O coletor está registrado e
  resolve por `\"tavily_search\"`".
- `test_query_includes_profile_keywords_and_include_domains_when_configured` — cobre
  "Query inclui as palavras-chave... `include_domains` aplica quando configurado".
- `test_time_range_never_open` — cobre "`time_range` nunca fica aberto".
- `test_collected_item_metadata_has_query_rank_score_retrieved_at_parser_version` —
  cobre o critério homônimo.
- `test_equivalent_urls_deduplicate_within_one_run` (variação de query
  string/fragmento/caixa) — cobre "Duas URLs equivalentes ... não geram dois itens".
- `test_known_ats_board_marks_source_proposal_candidate` e
  `test_unknown_ats_board_url_does_not_marks_candidate` — cobrem "URL de board de ATS
  já coberto marca `source_proposal_candidate`".
- `test_canonicalize_url_strips_tracking_query_and_fragment_lowercases_host` — unidade
  isolada de `canonicalize_url()`.
- `test_detect_ats_board_matches_known_patterns_and_returns_none_otherwise` — unidade
  isolada de `detect_ats_board()`.

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
docker compose -p f20-44 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_tavily_collector.py
docker compose -p f20-44 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-44 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
