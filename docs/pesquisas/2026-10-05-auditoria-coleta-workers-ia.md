# Auditoria da coleta de vagas, workers e dependência de IA

**Data:** 5 de outubro de 2026

**Código:** `main` em `46ebbedfaa89174ac2028e39d696fbed70a11693`

**Runtime:** stack `opportunity-radar-dev`

## Síntese e método

A ingestão usa integrações determinísticas para ATS; não depende em geral de
LLM. O gargalo principal é conteúdo: no snapshot SQL das 17:51 UTC, 41,7% das
vagas não tinham descrição, incluindo todas as ocorrências Workday. A IA estava
ativa para sugestões de campos, mas telemetria incompleta impede calcular a
parcela de vagas dependente de IA. Regras V4 estavam desativadas; não havia
embeddings e a busca observada era textual.

Analisei documentação, código, consultas PostgreSQL somente leitura e logs do
worker. A [CI run 37348807438](https://github.com/mathfrancisco/Opportunity-Radar/actions/runs/37348807438)
foi informada como success para backend, frontend, smoke E2E/persistência e
publicação. Não rodei testes locais, benchmark externo ou coleta contra sites.
Os contadores a seguir são o snapshot fornecido de 17:51. Ocorrências não
equivalem a vagas únicas.

## Evidências

| Indicador às 17:51 UTC | Quantidade | % |
| --- | ---: | ---: |
| Vagas | 25.702 | — |
| Sem descrição | 10.705 | 41,7% |
| Senioridade `UNKNOWN` | 14.566 | 56,7% |
| Modalidade `unknown` | 18.223 | 70,9% |
| Contrato `unknown` | 20.060 | 78,0% |

| Fonte | Ocorrências | Sem descrição |
| --- | ---: | ---: |
| Workday | 12.339 | 12.339 |
| Greenhouse | 7.330 | 0 |
| Ashby | 3.205 | 0 |
| Lever | 2.934 | 0 |
| Workable | 807 | 0 |
| Teamtailor | 445 | 0 |

`job_match` nas últimas 24h: 125 registros, 124 sucessos, uma falha de quota,
154.567 tokens de entrada e 63.603 de saída (218.170 registrados). Esses
registros não medem toda a classificação. Havia zero embeddings; 592
`AI_COMPLETED`, 2.218 `AI_FAILED` e 144 `AI_SKIPPED` são eventos históricos,
não vagas únicas. Havia 18 fontes Workday habilitadas às 17:51, nenhuma com
`fetch_detail=true`; uma consulta posterior encontrou 19, ainda sem detalhe
ativo.

## Código e operação

`collect_enabled_sources` percorre fontes elegíveis em série e registra gates
e resultados (`src/opportunity_radar/worker.py:442-572`). `max_instances=1`
limita instâncias no processo, não entre hosts. Reconsulta orçamento por host
durante o passe. Logs mostraram skips a cada minuto enquanto uma página Workday
levava cerca de cinco segundos. Em 28 runs Workday completos, média de 132 s;
Ashby/Greenhouse, cerca de 2 s. Passe iniciado 17:38:55 seguia sem conclusão
às 17:54; passes das 13:29 e 11:56 também apareciam abertos. Não há evidência
da causa histórica. `scripts/collect.py:171-187` usa semáforo e `gather` como
referência para concorrência limitada. Scheduler precisa preservar sessões
isoladas e orçamento compartilhado; checkout/CI não provam imagem em execução.

Workday pagina CXS e tem caminho de detalhe (`src/opportunity_radar/acquisition/workday.py:130-229`,
`381-453`), mas runtime tinha `EXTRACTION_SKIP_SOURCE_TYPES=workday`; fixtures
são sintéticas. Tavily não extraía Workday. Flags: `AI_ENABLED=true`,
`WORKER_SUGGEST_ENABLED=true`, `AI_ANALYSIS_PROMPT=v3`,
`CONTENT_CLASSIFICATION_V4_ENABLED=false`, `CONTENT_CLASSIFICATION_ENABLED_RULES=''`.

Sugestões chamam router (`src/opportunity_radar/opportunities/suggestions.py:266-321`).
`ProviderError` não persiste sugestão e essa chamada direta não grava
`ai_call_record` (`suggestions.py:310-321`). A fila ordena por criação e limita
`limit * 5` antes de filtrar em Python (`suggestions.py:210-235`): risco de
atraso dos seguintes, sem starvation medida. Busca usa FTS (`src/opportunity_radar/dashboard/queries.py:780-795`);
sem embeddings não há busca semântica ativa.

| Etapa | Mecanismo | LLM necessário? |
| --- | --- | --- |
| Descoberta de ATS/fontes | Regras; Tavily opcional | Não |
| Coleta ATS e JSON-LD | API/endpoint ou página configurada | Não |
| Normalização, deduplicação, matching/score/veredito e FTS | Código determinístico | Não |
| Análise textual de compatibilidade | Groq opcional | Opcional |
| Sugestões de campos desconhecidos | Router de modelo | Sim, se ativadas |
| Classificação V4 | Regras | Não; desligada no runtime |
| Busca semântica | Embeddings | Inativa |

## Melhorias recomendadas

1. **Workday:** piloto autorizado por fonte; medir descrição útil, latência,
   erros e orçamento antes de ativar detalhe. Concluir revisão de termos e
   validar resposta real; após piloto, enriquecer backlog e persistir cooldown
   em 429.
2. **Workers:** concorrência limitada, sessão isolada, orçamento por host,
   deadline, retomada idempotente e recuperação de lease. Validar que fonte
   lenta não bloqueia as demais nem duplica ocorrências.
3. **IA/fila:** registrar todas as chamadas, falhas e cooldowns sem dados
   pessoais; paginar após filtro ou usar overfetch progressivo. Reconciliar fila
   com telemetria e provar avanço após erro do provider.
4. **Extração:** priorizar APIs ATS, JSON-LD, sitemaps e parsers por fonte;
   navegador só quando JavaScript for necessário. Descoberta deve gerar
   proposta revisável. Referências: [Greenhouse](https://docs.greenhouse.io/job-board.html),
   [Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api) e
   [Google JobPosting](https://developers.google.com/search/docs/appearance/structured-data/job-posting),
   que exige descrição completa.
5. **Qualidade:** acompanhar cobertura, atualidade, duplicatas, campos
   desconhecidos e custo por oportunidade útil. Validar regras V4 com amostra
   humana; gate de 90% ainda estava pendente. `run.complete` não prova conteúdo
   completo.

Sequência: piloto Workday; telemetria/fila; métricas por fonte; concorrência e
retomada; expansão estruturada; avaliação humana V4. Snapshots são mutáveis,
telemetria não permite percentual de dependência de IA, e logs não explicam
passes antigos abertos. Esta auditoria não implementa mudanças nem valida
scraping adicional em produção.
