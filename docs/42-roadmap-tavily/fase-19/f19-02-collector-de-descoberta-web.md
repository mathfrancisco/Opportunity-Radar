# CARD F19-02 — Collector de descoberta web

- **Status:** Backlog
- **Fase:** 19 — Integração Tavily
- **Depende de:** F19-01
- **Bloqueia:** F19-04, F19-05
- **Origem:** [SPEC 41](../../41-spec-tavily.md), §5

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
- `healthcheck()` reusa o estado do F19-01 (bloqueado por configuração sem chave).

## Fora de escopo

- Orçamento de créditos e o que acontece quando o teto é atingido (F19-03).
- Extração de conteúdo completo via `/extract` (F19-04).
- Criar a `SourceDefinition`/proposta a partir do candidato marcado (F19-05).
- Filtrar por relevância de área da vaga — fica com a classificação de área já definida
  em `docs/37-spec-busca.md`, Frente F, aplicada depois na normalização.

## Notas de implementação

- Query e `include_domains` seguem a mesma fonte de palavras-chave que a Remotive já usa
  hoje (perfil ativo), sem reimplementar a extração de cargos/skills.
- A normalização de URL do dedupe é a mesma função usada pelo cache de extração do
  F19-04 — extrair para um único lugar compartilhado em vez de duplicar a lógica.
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
