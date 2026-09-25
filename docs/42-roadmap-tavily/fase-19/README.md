# Fase 19 — Integração Tavily

[Escopo e contratos](../../41-spec-tavily.md). Objetivo: achar vaga fora dos ATS já
cobertos, preencher corpo de postagem sem descrição e, depois, alimentar propostas de
fonte com evidência — sem gastar crédito além do orçamento e sem contornar o gate de
homologação que toda fonte já segue.

| Card | Depende de | Status |
| --- | --- | --- |
| [F19-01 — Cliente Tavily e configuração](f19-01-cliente-e-configuracao.md) | Nenhum | Backlog |
| [F19-02 — Collector de descoberta web](f19-02-collector-de-descoberta-web.md) | F19-01 | Backlog |
| [F19-03 — Orçamento de créditos e telemetria](f19-03-orcamento-de-creditos.md) | F19-01 | Backlog |
| [F19-04 — Extração de conteúdo com cache](f19-04-extracao-com-cache.md) | F19-01, F19-02 | Backlog |
| [F19-05 — Evidência para propostas de fonte](f19-05-evidencia-para-propostas.md) | F19-02, F17-04, F17-05 | Backlog |

## Invariantes

- Sem `TAVILY_API_KEY`, a fonte é relatada como bloqueada por configuração, nunca como
  falha; o resto do radar continua funcionando sem ela.
- `auto_parameters` nunca é enviado ativo — o radar decide `search_depth` e
  `extract_depth` de forma explícita, sempre `basic` até uma medição justificar
  `advanced`.
- Nenhuma chamada real à Tavily roda em CI; todo teste automatizado usa
  `httpx.MockTransport`.
- Um resultado que aponta para um board de ATS já coberto não vira ingestão duplicada:
  vira candidato de evidência para o F19-05.
- O teto de créditos por execução nunca é ultrapassado silenciosamente; ao ser
  atingido, a execução termina como parcial e o motivo fica no `SourceRun`.

## Dependências com outras fases

| Card | Depende de | Por quê |
| --- | --- | --- |
| F19-05 | F17-04, F17-05 | a evidência da Tavily entra na mesma fila de propostas e homologação que a Frente A da SPEC de busca já define |
