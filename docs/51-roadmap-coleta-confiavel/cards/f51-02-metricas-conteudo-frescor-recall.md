# F51-02 — métricas de conteúdo, frescor e recall

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** M
- **Risco:** médio. Métrica mal definida pode fazer um run parecer saudável sem conteúdo útil, confundir ausência com falha ou duplicar contagem por ocorrência.
- **Dependências:** F51-01 define coorte, snapshot e regra de descrição útil.

## Problema e evidência

**Fatos:** `SourceRun` guarda contagens como vistos, persistidos, inválidos, requests, bytes, idade do item mais novo, área-alvo e completude. Esses valores não equivalem a inventário completo ou conteúdo completo. Há três unidades diferentes: `RawItem`, `SourceOccurrence` e oportunidade canônica. Presença condicional já depende de execução completa; não pode ser substituída por uma métrica de conteúdo.

**Inferência a validar:** as métricas existentes permitem derivar parte da cobertura sem migração; campos de descrição útil, páginas e causa de parcialidade podem exigir telemetria adicional. Antes de alterar schema, mapear origem e disponibilidade de cada numerador e denominador.

## Objetivo e exclusões

Estabelecer um contrato por fonte/run para medir: inventário completo, itens vistos e elegíveis, conteúdo útil, descrição ausente e motivo de parcialidade. Derivar frescor de fontes elegíveis em janela móvel de sete dias, separando concluída, suspensa, bloqueada e falha. Relacionar recall apenas ao benchmark manual versionado do F51-01; o banco do produto não revela sozinho vagas publicadas que nunca foram coletadas.

Não alterar fechamento de oportunidades, política de retenção, execução de coleta nem score/veredito. Não inferir páginas vistas a partir de itens persistidos, `NULL` para zero, ausência de fonte desativada para falha, nem descrição útil a partir de HTTP 200 ou texto com mais de 200 caracteres.

## Arquivos e contratos existentes

- [`SourceRun` e `CollectionTelemetry`](../../../src/opportunity_radar/acquisition/domain.py): contadores e estados em memória.
- [`SourceRunModel`](../../../src/opportunity_radar/acquisition/models.py): campos persistidos existentes, inclusive `complete`, `items_seen`, `items_persisted`, `items_invalid`, `http_requests`, `items_target_area` e `items_off_target`.
- [`AcquisitionService.execute`](../../../src/opportunity_radar/acquisition/service.py): consolida run e telemetria; verificar contadores que realmente chegam ao banco.
- [`AcquisitionRepository`](../../../src/opportunity_radar/acquisition/repository.py) e [`collection_alarm.py`](../../../src/opportunity_radar/operations/collection_alarm.py): consultas e alarmes a reaproveitar.
- [Testes de telemetria de aquisição](../../../tests/backend/acquisition/test_run_telemetry.py): comportamento de persistência atual.

## Tarefas executáveis

1. Criar matriz métrica → fonte → unidade → fórmula → estados válidos → lacunas. Identificar quais valores são do coletor, do normalizador, do catálogo ou do benchmark manual; bloquear fórmula que mistura essas origens.
2. Derivar inventário completo somente do contrato do run (páginas/total/cursor quando disponíveis, encerramento normal e ausência de erro). Se fonte não anuncia total, registrar a regra de paginação/terminação usada e “completude não verificável” quando não houver prova.
3. Derivar conteúdo útil por ocorrência e versão da regra F51-01. Contar descrição útil, ausente, inválida e não avaliada como estados distintos. Não aplicar conteúdo útil como condição de presença/fechamento.
4. Definir denominadores: fontes habilitadas e elegíveis na janela; runs iniciados; runs com inventário completo; itens/ocorrências; canônicos. Exibir n/d quando origem ou denominador faltar.
5. Publicar duas métricas com denominadores diferentes: cadência operacional usa idade da última tentativa/execução e estado atual; frescor dos dados usa idade do último inventário completo bem-sucedido. Uma falha recente pode melhorar cadência observada, mas nunca renova frescor das vagas. Fonte habilitada em cooldown temporário permanece visível na janela como degradada, não sai do denominador para inflar taxa. Recall vem do benchmark humano, com todas as vagas publicadas elegíveis no denominador e exclusões humanas explicitadas; não estimar recall por fontes coletadas.
6. Só propor migração se a matriz provar que contadores necessários se perdem e não podem ser derivados. Migração aditiva, defaults que não convertam legado em zero, backfill apenas onde evidência original sustente valor; caso contrário, iniciar série nova.

## Critérios de aceite

| ID | Critério mensurável | Cenário Given / When / Then | Teste proposto e artefato |
| --- | --- | --- | --- |
| AC01 | Run completo e parcial mantêm inventário e motivo distintos; total ausente continua desconhecido. | Dado run completo e outro interrompido após página 1 de 3, quando o relatório agrega, então apenas o primeiro conta no inventário completo e o segundo exibe `partial` e razão. | Proposto: `tests/backend/acquisition/test_source_quality_metrics.py::test_inventory_completeness_is_separate_from_content`; matriz com ambos os runs e denominadores. |
| AC02 | Cadência e frescor não se confundem, e cooldown elegível não desaparece do denominador. | Dada última tentativa com falha há 5 min e último inventário completo há 3 dias numa fonte habilitada em cooldown, quando a janela semanal é calculada, então cadência mostra tentativa recente, frescor continua com 3 dias e a fonte aparece degradada no denominador. | Proposto: `test_failed_attempt_does_not_refresh_inventory_freshness`; relatório inclui idade/denominador de cada métrica e estado cooldown. |
| AC03 | `NULL`/não medido nunca vira zero; conteúdo útil é versionado e não altera `complete` nem fechamento. | Dada run antigo sem contador e ocorrência sem descrição avaliada, quando a série é gerada, então aparecem “não disponível” e “não avaliada”, não zeros; descrição ruim não muda presença positiva. | Proposto: `tests/backend/opportunities/test_content_metric_does_not_change_presence.py::test_content_metric_does_not_close_occurrence`; snapshot comparativo. |
| AC04 | Relatório separa `raw_item`, ocorrência e canônico sem duplicar uma vaga em contagem canônica. | Dado duas ocorrências em fontes diferentes ligadas ao mesmo canônico, quando agregado, então são duas ocorrências e uma oportunidade. | Proposto: `tests/backend/dashboard/test_source_quality_report.py::test_population_units_are_disjoint`; saída tabular com unidade explícita. |
| AC05 | Recall tem amostra manual externa e denominador explícito; sem amostra não é calculado. | Dada vaga elegível que o coletor descartou, quando o recall é calculado, então permanece no denominador como não encontrada; sem amostra aprovada o campo é `unmeasurable`. | Proposto: `test_recall_requires_human_sample_and_keeps_missed_jobs`; manifesto ligado à amostra F51-01. |

## Casos negativos, rollout e rollback

Falha de parser, fonte sem total, run interrompido, fonte desativada ou métrica de conteúdo ausente não podem produzir 100%, zero ou “saudável” silenciosamente. Tentativa recente com falha não pode atualizar o timestamp de inventário completo; cooldown temporário não pode remover fonte habilitada do denominador. Métricas de detalhe devem continuar separadas de inventário. Testes que escrevem no banco usam apenas `_test` com `RUN_DATABASE_INTEGRATION=1` e `DATABASE_INTEGRATION_ISOLATED=1`.

Iniciar com relatório aditivo e leitura operacional; não mudar alarmes nem cadência no mesmo rollout. Se campo legado não puder ser interpretado, marcar não medido e iniciar nova série em vez de reescrever histórico. Reverter apenas a publicação/flag do relatório; preservar runs e snapshots já coletados.

## Entregáveis

Matriz de origem/fórmula, relatório por fonte e janela, testes para estados completos/parciais e NULLs, decisão documentada sobre necessidade de migração e comparação de três runs completos quando disponíveis. O relatório deve deixar visível quando uma métrica é proposta, não mensurável ou baseada em amostra manual.
