# CARD F19-04 — Extração de conteúdo com cache

- **Status:** Backlog
- **Fase:** 19 — Integração Tavily
- **Depende de:** F19-01, F19-02
- **Bloqueia:** Nenhum
- **Origem:** [SPEC 41](../../41-spec-tavily.md), §3.2, §6

## Resultado

Postagens sem descrição — da própria Tavily ou de outra fonte — ganham corpo via
`POST /extract`, e a mesma URL nunca é extraída duas vezes: uma vez por URL, para
sempre, dentro da validade do cache.

## Contexto

O `TavilySearchCollector` (F19-02) usa um trecho curto de `content` como descrição
provisória; a extração completa custa crédito à parte e só compensa para URLs que
realmente ficaram sem corpo depois da normalização.

## Escopo

- Rotina que recebe uma lista de URLs sem descrição (do resultado da Tavily ou de
  qualquer `CollectedItem` de outra fonte que chegou sem corpo) e chama `/extract` em
  lotes de até 20 URLs, `extract_depth="basic"`, `format="markdown"`.
- Cache por hash da URL canônica (mesma normalização do dedupe do F19-02): hit não gera
  chamada nova; miss chama, grava o resultado e o hash antes de devolver.
- Validade do cache configurável; entrada expirada é tratada como miss, não como erro.
- Falha de extração para uma URL específica dentro de um lote não derruba as demais —
  cada URL do lote tem resultado próprio (sucesso, falha, sem conteúdo).
- Créditos gastos na extração entram no mesmo acumulador do F19-03 (1 crédito a cada 5
  URLs bem-sucedidas em `basic`).

## Fora de escopo

- `extract_depth="advanced"` como padrão — fica reservado a medição futura (SPEC §10).
- Extrair URL que já tem descrição suficiente — critério de "sem descrição" é definido
  pela normalização existente, não reavaliado aqui.
- Servir o cache para outros consumidores fora da extração Tavily.

## Notas de implementação

- Reusar a função de normalização de URL do F19-02 para o hash do cache — a mesma URL
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
- [ ] Créditos gastos na extração aparecem no acumulador do F19-03.
- [ ] Markdown extraído substitui a descrição provisória quando presente.

## Verificação

- **CI:** teste de cache hit/miss/expirado com `httpx.MockTransport`; teste de lote
  particionado acima de 20 URLs; teste de falha isolada dentro de um lote; teste de
  soma de créditos compartilhada com F19-03.
- **Máquina de referência:** sem chamada real à Tavily.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/tavily.py`
- `src/opportunity_radar/acquisition/models.py` (tabela/coluna de cache, se persistida)
- `tests/acquisition/test_tavily_extract_cache.py` (novo)
