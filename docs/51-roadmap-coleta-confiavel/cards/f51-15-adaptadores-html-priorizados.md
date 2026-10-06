# F51-15 — adaptadores HTML para fontes priorizadas

- **Status:** Planejado/condicional
- **Prioridade:** P2
- **Esforço:** G
- **Risco:** alto para parser drift, identidades erradas e tráfego em fonte de baixa utilidade.
- **Dependências:** F51-13; fonte e termos aprovados; seleção baseada em gap medido.

## Evidência e limites

O coletor genérico [`jobposting.py`](../../../src/opportunity_radar/acquisition/jobposting.py) consome JSON-LD `JobPosting` de URL configurada; isso não demonstra que adaptadores HTML adicionais sejam necessários. Escolher fontes por falta medida de descrição útil/recall no benchmark F51-01/F51-02, volume elegível e viabilidade de termos. Não generalizar seletor para todos os sites nem esconder falha com fallback para scrape irrestrito.

## Arquivos existentes

- [`jobposting.py`](../../../src/opportunity_radar/acquisition/jobposting.py): extração genérica de JSON-LD.
- [`registry.py`](../../../src/opportunity_radar/acquisition/registry.py) e [`service.py`](../../../src/opportunity_radar/acquisition/service.py): capacidades, registro e execução dos coletores.
- [`test_jobposting_collector.py`](../../../tests/backend/acquisition/test_jobposting_collector.py): fixtures e contratos JSON-LD existentes.
- Fixtures/site adapters novos só entram após fonte específica aprovada; não há adaptador HTML universal alegado.

## Tarefas concretas

1. Abrir decisão para uma fonte por vez: evidência do gap, termos, owner, host, amostra de volume, causa pela qual API/ATS/JSON-LD não atende e campos mínimos esperados. Fonte sem ganho justificável fica fora.
2. Capturar fixtures públicas reais minimizadas e sanitizadas de lista, detalhe, paginação e erro; fixar URL base, parâmetros identificadores e versão/layout. Não armazenar cookies, dados pessoais ou páginas autenticadas.
3. Implementar parser isolado por adapter que transforma cada item em contrato `CollectedItem` já existente. Requerer identificador estável, URL, título e evidência do conteúdo; campos não presentes seguem ausentes. Validar mesmo comportamento para lista, paginação, detalhe e duplicatas.
4. Detectar seletor/campo obrigatório ausente como `schema_changed` ou parse failure. Não reinterpretar HTML de consentimento/erro como lista vazia. Resposta 200 com zero itens inesperados gera `suspect_zero`/parcial até validar prova de catálogo realmente vazio.
5. Definir limites por host, páginas, bytes, requests e deadline; respeitar redirect/DNS/SSRF comum. Sem fallback oculto: se adapter falha, registrar motivo e manter anteriores; fallback só existe se configurado explicitamente e versionado.
6. Versionar parser/layout e medir taxa de campos ausentes, descrição útil, deduplicação e drift por run antes de ampliar a fonte.

## Critérios de aceite

| ID | Critério | Given / When / Then | Teste proposto e artefato |
| --- | --- | --- | --- |
| AC01 | Adapter só é construído para fonte escolhida por gap medido e termos aprovados. | Dada fonte sem decisão ou sem gap, quando registry é carregado, então adapter não participa e fonte continua desabilitada. | `test_html_adapter_requires_approved_source_and_gap` (proposto em `tests/backend/acquisition/test_html_adapter.py`); registro de decisão e zero HTTP. |
| AC02 | Fixture de lista/detalhe/paginação preserva identidade e converte conteúdo. | Dada fixture com dois IDs em páginas diferentes e detalhes relacionados, quando parser executa, então duas identidades estáveis e corpo correto são produzidos, sem duplicata. | `test_html_adapter_list_detail_pagination_contract` (proposto); fixtures redigidas e `CollectedItem`s. |
| AC03 | Drift e zero suspeito não viram inventário vazio completo. | Dada página sem seletor obrigatório ou 200 inesperado com zero resultados, quando executa, então run é parcial com reason `schema_changed`/`suspect_zero`; ausência não fecha vaga. | `test_html_adapter_schema_drift_and_suspect_zero` (proposto); status/reason e itens prévios preservados. |
| AC04 | Limite ou erro não dispara fallback oculto. | Dado adapter excedendo cap de páginas ou falhando, quando termina, então requests não excedem cap, razão é registrada e nenhum outro coletor inicia sem fallback configurado. | `test_html_adapter_limit_does_not_fallback_implicitly` (proposto); contador HTTP por host. |
| AC05 | Drift é observável por versão. | Dada mudança de layout/version do parser, quando métricas do run são emitidas, então taxa de missing field e conteúdo útil são separadas por adapter/parser version. | `test_html_adapter_metrics_are_versioned` (proposto); relatório com denominadores e versão. |

## Rollout, rollback e entregáveis

Primeiro validar fixtures offline; depois ativar uma fonte/host com limites conservadores e execução monitorada. Nenhum site novo é ativado automaticamente pelo cadastro do adapter. Parar ao receber schema drift, suspeita de zero, violação de termos ou cap recorrente. Rollback desabilita apenas aquele adapter/source e mantém `SourceRun`, raw evidence e parser version; não apaga dados prévios nem faz fallback automático. Entregáveis: decisão de gap, termos, fixtures, adapter específico, reason codes, métricas por versão e go/no-go para a fonte seguinte. Este card é adiável se API/JSON-LD resolverem o gap.
