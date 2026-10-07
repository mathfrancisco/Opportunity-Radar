# F51-01 — baseline e benchmark auditável por fonte

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** M
- **Risco:** médio. Uma população ambígua, mistura de ocorrências e vagas canônicas ou exclusões silenciosas pode produzir melhora percentual sem melhora real. A consulta operacional deve ser somente leitura; coleta externa só entra numa fase autorizada própria.
- **Dependências:** nenhuma.

## Problema e evidência

**Fatos:** no snapshot de 2026-10-05 17:51 UTC havia 25.702 oportunidades e 10.705 sem descrição (41,7%). O catálogo é mutável; uma vaga pode ter várias ocorrências de fonte. `SourceRun.complete` descreve a coleta, não prova que cada conteúdo é útil. A auditoria observou esses dados em [auditoria de 2026-10-05](../../../docs/pesquisas/2026-10-05-auditoria-coleta-workers-ia.md).

**Inferência a validar:** um corte versionado por fonte, coorte, janela e rótulo humano dará comparação mais confiável do que contagens globais. O snapshot de um instante não demonstra tendência, recall nem causalidade.

## Objetivo e exclusões

Produzir uma baseline reproduzível, inicialmente de leitura, que separe itens brutos, ocorrências por fonte e oportunidades canônicas; documente a regra de descrição útil; e inclua amostra manual de vagas publicadas permitidas, inclusive as que o coletor deixou passar. Reportar contagens e denominadores, versão da consulta/regra, origem, data, filtros, exclusões e incerteza.

Não ativar fontes, chamar ATS, fazer scraping, editar oportunidades, recalcular score/veredito, alterar critérios de recomendação ou transformar a amostra em verdade permanente do catálogo. Não excluir vaga só porque o parser ou a regra atual a rejeitou; exclusão de recall exige rótulo humano e motivo permitido.

## Arquivos e contratos existentes

- [`SourceRun` e `CollectionTelemetry`](../../../src/opportunity_radar/acquisition/domain.py): estado e contadores de execução; não usar `complete` como proxy de conteúdo útil.
- [`AcquisitionRepository`](../../../src/opportunity_radar/acquisition/repository.py): leitura de runs e dados de aquisição; preferir consultas existentes antes de propor schema.
- [`funnel_report`](../../../src/opportunity_radar/dashboard/funnel.py) e [métricas do dashboard](../../../src/opportunity_radar/dashboard/metrics.py): verificar se já oferecem estágios reutilizáveis; não presumir que atendem a recall manual.
- [Testes de telemetria de aquisição](../../../tests/backend/acquisition/test_run_telemetry.py) e [métricas do dashboard](../../../tests/backend/dashboard/test_metrics.py): contratos atuais a preservar.

## Tarefas executáveis

1. Definir o contrato do snapshot com `captured_at`, janela, IDs/versões de fonte e coletor, filtros, coorte, unidade (`raw_item`, `source_occurrence` ou oportunidade canônica), execução considerada e versão do avaliador. Guardar cada corte como artefato imutável; não sobrescrever baseline anterior.
2. Inspecionar tabelas e relatórios disponíveis antes de adicionar persistência. Implementar a extração do baseline como consulta somente leitura e tornar a consulta/versionamento reproduzível. Separar contagem de ocorrência de contagem canônica e explicitar quando deduplicação impede atribuição a uma fonte.
3. Especificar “descrição útil” em regra versionada: conteúdo textual não vazio, sem mensagem de erro, HTML residual, título isolado ou boilerplate; guardar método e motivo da classificação. `NULL`, não medido e erro permanecem estados distintos de zero.
4. Definir amostra de recall por fonte, área e data. Capturar URLs públicas da população aprovada e anotar manualmente achadas, elegíveis, fora de área, fora de escopo/termos e inacessíveis. Vagas elegíveis descartadas incorretamente continuam no denominador; somente exclusões humanas documentadas saem dele. Não coletar login ou dados pessoais.
5. Publicar numeradores, denominadores, exclusões e tamanho da amostra junto aos resultados; marcar “insuficiente” quando não houver três runs completos ou amostra válida. Não inferir zero falhas a partir da falta de dados.

## Critérios de aceite

| ID | Critério mensurável | Cenário Given / When / Then | Teste proposto e artefato esperado |
| --- | --- | --- | --- |
| AC01 | Duas execuções da mesma consulta, coorte e corte retornam o mesmo denominador por unidade; novo corte cria outra versão. | Dado um snapshot registrado, quando o relatório é refeito sem mudança da coorte, então os totais e hash da consulta coincidem; ao mudar janela, o relatório ganha novo identificador. | Proposto: `tests/backend/dashboard/test_source_baseline.py::test_snapshot_is_reproducible_and_versioned`; fixture isolada e manifesto com consulta, filtros e totais. |
| AC02 | Ocorrências e oportunidades canônicas nunca são somadas como uma população única. | Dada uma vaga ligada a duas fontes e dois raw items, quando o relatório agrupa por fonte e por canônico, então mostra duas ocorrências atribuídas e uma oportunidade; não duplica o denominador canônico. | Proposto: `test_occurrences_and_canonical_jobs_have_separate_denominators`; tabela de contagens por unidade. |
| AC03 | Recall inclui todos os elegíveis da amostra, inclusive os descartados pelo parser; exclusões têm motivo humano. | Dada uma vaga pública elegível rejeitada pelo coletor, quando a amostra é calculada, então ela permanece no denominador como não encontrada; fora de área só sai com rótulo e razão. | Proposto: `test_recall_keeps_eligible_parser_rejections_in_denominator`; CSV/JSON de amostra anonimizado e razão por linha. |
| AC04 | Run parcial, falho ou sem baseline suficiente nunca aparece como cobertura completa nem como zero. | Dado um run parcial sem duas páginas, quando o relatório calcula cobertura, então retorna “incompleto/insuficiente”, não usa ausências desse run para fechar vagas e preserva presenças positivas observadas. | Proposto: `test_partial_run_is_not_a_complete_inventory_baseline`; relatório com estado e denominador não mensurável. |
| AC05 | Auditoria operacional comprova acesso somente leitura sem exigir contagens estáticas num banco concorrente. | Dada uma sessão operacional com papel read-only, quando executa a consulta, então o log SQL não contém DML; contagens antes/depois são comparadas apenas na fixture isolada. | Proposto: `test_baseline_query_is_read_only` contra fixture; evidência operacional inclui papel, comando, log SQL e timestamp, sem usar igualdade de contagens concorrentes como prova. |

## Casos negativos e rollout

Snapshot sem população publicada de referência, sem permissão/termos, com joins ambíguos ou menos de três inventários completos deve retornar “não mensurável” com razão; não preencher ausências nem relaxar elegibilidade. Query quebrada ou esquema inesperado falha fechada e não grava dados. Testes mutantes usam somente banco com sufixo `_test`, `RUN_DATABASE_INTEGRATION=1` e `DATABASE_INTEGRATION_ISOLATED=1`.

O primeiro rollout é consulta read-only no banco operacional autorizado e amostra pública permitida, sem disparar coleta. Revisar denominadores e amostra antes de divulgar baseline. Se a consulta causar carga, interrompê-la e executar sobre réplica/snapshot; não há migração para reverter. Preservar o artefato produzido e marcá-lo inválido, sem sobrescrever, se a definição de coorte estiver errada.

## Entregáveis

Contrato e consulta versionados, regra de descrição útil, amostra manual datada com rótulos/exclusões, relatório por fonte com unidades separadas, testes propostos implementados na fase de código e evidência de leitura operacional sem mutação. A saída deve declarar limites, contagens não mensuráveis e fonte do dado; baseline não equivale a aprovação de expansão.

## Medição na abertura da janela (2026-10-07, sexta sessão)

`scripts/source_baseline.py`, rodado no contêiner da API contra a base de dev, em transação
`REPEATABLE READ READ ONLY` (snapshot `420150:420150:`), capturado em 2026-10-07 13:53:53 UTC,
janela de sete dias corridos até esse instante. `query_hash`
`ad4a673821dc5329ce66d626f889db58db46a8641f60fd38c31c91d571d6e105`, coletor
`source-baseline-collector-v1`. O artefato JSON não foi versionado: lista as 32.023 vagas.

| Medida | Valor |
|---|---:|
| Fontes na base | 283 |
| Fontes elegíveis (habilitadas) | 276 |
| Fontes com três execuções completas em sete dias | 233 |
| Fontes sem três execuções completas | 43 (25 com duas, 16 com uma, 2 com nenhuma) |
| Vagas canônicas | 32.023 |
| Com descrição útil (`useful-description-v1`) | 15.428 |
| Sem descrição | 12.813 |
| Com descrição inválida | 3.782 |

O estado da base de execuções é "insuficiente": 43 fontes ainda não têm três execuções
completas. Dessas, 42 têm a última tentativa `SUCCEEDED` e uma `PARTIAL`; em 29 a última
tentativa não é inventário completo (resposta `304` sem reuso de inventário). Entre elas
estão Santander, NVIDIA e SUSE (Workday), Hacker News e as fontes Teamtailor.

`scripts/measure_descriptions.py`, 2026-10-07 14:13 UTC: 32.249 vagas, 19.436 com descrição;
texto limpo (`cleaner-v2`) com mediana de 4.630 caracteres e p95 de 9.167; 397 descrições
passam sozinhas do orçamento de 3.600 tokens.

**Estado: parcial.** As três execuções completas por fonte e a contagem de descrição útil têm
de ser medidas de novo no fim da janela, com a coorte de 276 fontes congelada em
[f51-18-coorte-2026-10-07.tsv](../f51-18-coorte-2026-10-07.tsv). O recall do AC03 depende da
amostra humana do dono. `scripts/benchmark_report.py` compara relatórios do
`eval_analysis.py` e não mede nada deste card.
