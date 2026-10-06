# F51-17 — benchmark FTS e relevância end-to-end

- **Status:** Planejado
- **Prioridade:** P1
- **Esforço:** M
- **Risco:** médio para inferência de ganho sobre corpus pequeno ou enviesado; benchmark mede, não altera rank.
- **Dependências:** F51-01, F51-02, F51-05 e F51-11; medição final após piloto/backfill F51-05.

## Fatos e escopo

Busca textual atual está em [`queries.py`](../../../src/opportunity_radar/dashboard/queries.py): usa `search_document @@ websearch_to_tsquery` e ordenação `ts_rank_cd`; busca semântica não está ativa. FTS permanece baseline e não será alterada por este card. Conteúdo piloto pode mudar recall; sem medição congelada não se declara melhora.

## Arquivos existentes

- [`queries.py`](../../../src/opportunity_radar/dashboard/queries.py): busca FTS e ranking.
- [`dashboard.py`](../../../src/opportunity_radar/presentation/http/dashboard.py): rota/contrato HTTP de busca.
- [`test_search_fulltext.py`](../../../tests/backend/dashboard/test_search_fulltext.py) e [`test_metrics.py`](../../../tests/backend/dashboard/test_metrics.py): busca e filtros atuais.
- Corpus/queries/gold e `tests/backend/dashboard/test_search_benchmark.py` são novos artefatos propostos; nunca atualizar rótulos depois de ver resultados sem publicar versão nova.

## Protocolo

1. Congelar snapshot do corpus, `captured_at`, versão de index/config, idioma, coorte e hash de dados. Fixar consultas antes de executar: português/inglês, sinônimos, acento/plural, consulta ambígua, filtros de localização/área, zero resultado e consulta específica.
2. Dois revisores humanos rotulam relevância por query usando critério documentado e IDs independentes do ranking retornado. Gold inclui relevantes que não aparecem no top-k; caso contrário recall fica artificialmente alto. Resolver discordância sem olhar posição do FTS ou registrar adjudicação.
3. Registrar denominadores: total julgados elegíveis da query; total relevante no corpus; total retornado até k; relevantes no top-k. Definir precision@10/20 = relevantes retornados / resultados efetivamente retornados até k; recall@10/20 = relevantes retornados / total relevante elegível do corpus. Se total relevante=0, recall fica N/D; zero resultados com gold positivo implica recall 0 e precision N/D.
4. Para o efeito do enriquecimento F51-05, congelar IDs/coorte, queries, filtros e gold humano independente; medir snapshot A antes e snapshot B após, esperando payload/hash distintos quando descrição mudou. Registrar parser/transformação de cada snapshot e atribuir deltas ao conteúdo, não ao algoritmo. Uma comparação de algoritmo exige em separado o mesmo snapshot de payload em ambos os lados; mudança de membros, gold, query ou filtro torna a comparação não comparável.
5. Definir precision@k convencional como relevantes no top-k / k (slots vazios não relevantes); opcionalmente publicar `precision_returned` = relevantes / min(k, retornados). Recall@k = relevantes no top-k / total de relevantes elegíveis do gold. Se gold relevante=0, recall=N/D; se nenhum item retornou, precision@k=0 e precision_returned=N/D. Latência: ao menos 5 repetições frias e 10 quentes por query, p50/p95; reiniciar cache apenas em snapshot isolado, nunca no banco operacional.

## Critérios de aceite

| ID | Critério | Given / When / Then | Teste/artefato |
| --- | --- | --- | --- |
| AC01 | Corpus, queries e gold são congelados antes do ranking. | Dado manifesto versionado, quando benchmark roda, então hashes de corpus/query/rotulagem e revisão humana constam do relatório. | `test_search_benchmark_uses_frozen_manifest` (proposto); arquivos de manifesto/gold assinados. |
| AC02 | Casos PT/EN, sinônimo, ambiguidade, filtro e zero estão representados. | Dada suíte fixa com todos os tipos, quando avaliação percorre queries, então cada tipo tem contagem e denominador próprio; zero resultado não é omitido. | `test_benchmark_covers_language_ambiguity_filters_and_zero` (proposto); matriz query/categoria. |
| AC03 | P@10/P@20 e recall têm fórmula e denominadores explícitos. | Dada query com 13 relevantes, 8 relevantes no top 10 e 11 no top 20, quando métricas são calculadas, então recall é 8/13 e 11/13, P@10=8/10 e P@20=11/20; slots vazios contam como não relevantes. | `test_precision_recall_k_uses_independent_gold_denominators` (proposto); cálculo auditável por query. |
| AC04 | Latência informa p50/p95 para amostras quentes e frias separadas. | Dadas repetições de execução controladas, quando resumo é criado, então cold (>=5) e warm (>=10) têm número de observações, p50/p95 e parâmetros de ambiente. | `test_benchmark_latency_separates_warm_and_cold` (proposto); JSON/CSV de tempos brutos. |
| AC05 | Delta de conteúdo compara coorte fixa mesmo com payloads diferentes; delta de algoritmo exige payload idêntico. | Dados snapshots A/B com mesmos IDs, queries, filtros e gold, mas payload/hash alterado pelo enriquecimento, quando mede F51-05, então relatório atribui delta ao conteúdo e informa versões do parser; se membros/gold/queries/filtros mudam, marca N/D. Para algoritmo, hashes do corpus devem coincidir. | `test_benchmark_separates_content_and_algorithm_deltas` (proposto); relatório com decisão comparável e hashes. |

## Rollout e reversão

Benchmark roda read-only em snapshot de dados e não publica ranking alternativo nem muda endpoint. Repetir a medição final só após piloto F51-05; resultados preliminares são rotulados. Rollback descarta relatório inválido sem alterar índice, gold ou busca; manter versões e explicar invalidade. Entregáveis: corpus e gold congelados, suite de queries, script de métrica, latência bruta, comparação por coorte e decisão sobre FTS. Nenhum ganho é alegado até produzir evidência.
