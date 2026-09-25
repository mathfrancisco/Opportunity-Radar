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
docker compose -p f20-44 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-44 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-44 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
