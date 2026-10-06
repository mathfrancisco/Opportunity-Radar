# F51-11 — gold humano, regras V4 e reclassificação

- **Status:** Planejado
- **Prioridade:** P1
- **Esforço estimado:** M
- **Risco:** alto para falsos positivos e colisão de identidade; ativação é por regra e exige gold congelado suficiente.
- **Dependências:** F51-01; concluir F50-01/F50-02 originais antes de habilitar regras.

## Problema e evidência

O baseline operacional registrou `CONTENT_CLASSIFICATION_V4_ENABLED=false` e `CONTENT_CLASSIFICATION_ENABLED_RULES=''`. O código declara `PRECISION_GATE = 0.90` e `GATED_RULES` vazio em `content_classification.py`; portanto não se deve sugerir que regras estejam aprovadas em runtime. F50-01/F50-02 deixaram gold humano pendente. Precisão de 90% ainda não foi demonstrada. Isso impede ligar regra automaticamente a partir de heurística ou média agregada.

## Objetivo e limites

Concluir protocolo gold e medir cada regra elegível individualmente; liberar apenas regras que atinjam limiar com suporte e auditoria definidos. Preservar categorias humanas `inapplicable` e `unknown`: não aplicável sai do denominador daquela regra, desconhecido permanece reportado e não vira negativo. Não usar label de IA como gold, não mesclar oportunidades automaticamente e não alterar conteúdo original sem dry-run/revisão.

## Arquivos e símbolos existentes

- [`content_classification.py`](../../../src/opportunity_radar/opportunities/content_classification.py): `PRECISION_GATE`, `GATED_RULES`, avaliação/medição e regras V4.
- [`config.py`](../../../src/opportunity_radar/platform/config.py): parsing/validação de `CONTENT_CLASSIFICATION_ENABLED_RULES`.
- [`service.py`](../../../src/opportunity_radar/opportunities/service.py): reclassificação e persistência de campos canônicos.
- [`reclassify_content.py`](../../../scripts/reclassify_content.py): CLI com dry-run padrão e `--apply` explícito.
- [`test_measure_content_classification.py`](../../../tests/backend/opportunities/test_measure_content_classification.py) e [`test_reclassify_content_integration.py`](../../../tests/backend/opportunities/test_reclassify_content_integration.py): medição, aplicação e colisões existentes.

## Execução

1. Recuperar os critérios originais F50-01/F50-02 e congelar guia de anotação, campos, evidência literal, versão do classificador e regras candidatas. Gold mínimo: 200 exemplos rotulados no total e ao menos 50 exemplos por tipo de fonte coberto; reportar desequilíbrio e não compensar ausência de suporte com duplicação de exemplos.
2. Para cada regra/campo, anotar `applicable`, `inapplicable` ou `unknown`, valor esperado e trecho de evidência. Fazer dupla revisão de discordância. Gold nunca é gerado ou corrigido pelo modelo.
3. Medir precision por regra apenas sobre amostras aplicáveis e com label conhecido, publicar matriz TP/FP/FN, total e cobertura por tipo de fonte. Uma regra só passa se precisão >=90% e tiver pelo menos 20 emissões válidas para aquela regra (`GATED_RULE_MIN_EMISSIONS`); regra abaixo de qualquer limite continua não aprovada. Não agregar regras para mascarar uma abaixo do limiar.
4. Reusar `PRECISION_GATE` e `GATED_RULES` (ou sua extensão já existente) em vez de criar um gate paralelo. Configurar uma regra aprovada por vez via `CONTENT_CLASSIFICATION_ENABLED_RULES`; manter `CONTENT_CLASSIFICATION_V4_ENABLED` e regras fora da allowlist desligadas.
5. Antes de `--apply`, executar `scripts/reclassify_content.py` em dry-run e revisar alterações, conflitos de fingerprint, valores humanos e contagens. Manter idempotência por versão de regra e hash de entrada; registrar versão e evento de reavaliação dirigida.
6. Em colisão fingerprint, preservar fingerprint e campos originais da linha perdedora, registrar conflito e não mesclar. Aplicar apenas regras aprovadas, sem auto-merge ou side effect em decisão humana.

## Critérios de aceite

| ID | Critério mensurável | Given / When / Then | Teste proposto e artefato |
| --- | --- | --- | --- |
| AC01 | Gold tem pelo menos 200 rótulos totais e 50 por tipo de fonte; unknown/inapplicable ficam distintos. | Dada amostra congelada com esses mínimos, quando métricas são calculadas, então unknown aparece fora da precisão, inapplicable é excluído apenas da regra correspondente e as contagens são publicadas por tipo de fonte/regra. | `test_gold_counts_support_and_label_states_per_source` (proposto em `test_measure_content_classification.py`); manifesto versão e distribuição. |
| AC02 | Gate >=90% e mínimo de 20 emissões são avaliados regra a regra. | Dadas regras A com 89%, B com 90% e C com 90% mas 19 emissões, quando gate roda, então só B é elegível; A falha precisão e C falha suporte. | `test_precision_gate_is_per_rule_and_requires_support` (proposto); matriz de confusão e allowlist gerada. |
| AC03 | Configuração existente controla ativação sem novo caminho paralelo. | Dada uma regra aprovada em `GATED_RULES`, quando apenas seu nome está em `CONTENT_CLASSIFICATION_ENABLED_RULES`, então nenhuma outra regra V4 roda. | `test_enabled_rules_allowlist_is_respected` (proposto em `test_reclassify_content_integration.py`); saída por regra. |
| AC04 | Dry-run não altera dados e aplicação repetida é idempotente. | Dada mesma versão/regra e oportunidades fixas, quando dry-run e depois duas aplicações isoladas são executadas, então dry-run não escreve e a segunda aplicação faz zero mudanças adicionais. | `test_reclassification_is_dry_run_then_idempotent` (proposto; extensão do teste de integração); hashes/versões antes/depois. |
| AC05 | Colisão não mescla ou altera fingerprint da oportunidade protegida. | Dadas duas linhas que convergem ao mesmo fingerprint após regra, quando `--apply` é solicitado, então conflito é reportado e fingerprints/campos do perdedor permanecem. | `test_reclassification_fingerprint_collision_preserves_both_rows` (proposto; existente `test_a_taken_fingerprint_keeps_the_work_mode_and_reports_the_collision` é referência); relatório de colisão. |
| AC06 | Reavaliação dirigida identifica regra e versão. | Dada alteração de conteúdo ou versão de regra, quando reclassificação é rodada, então apenas coorte afetada é reavaliada e evento indica regra, versão e motivo. | `test_reclassification_records_targeted_rule_version` (proposto); relatório por coorte e eventos. |

## Falhas, rollout e rollback

Gold abaixo do mínimo, discordância não resolvida, precisão menor que 90%, unknown elevado, migração de regra sem versão ou conflito de fingerprint bloqueiam ativação. Todos os testes mutáveis usam `_test`; não rodar `--apply` contra operacional nesta fase. Rollout: uma regra, allowlist explícita, dry-run revisado, aplicação pequena, medição pós-aplicação; sem automerge. Rollback remove a regra da allowlist, preserva gold e histórico, e reverte apenas campos derivados pela versão no manifesto após validação; não restaura por delete amplo. Entregáveis: gold revisado, relatório por fonte/regra, decisão gate, dry-run, manifesto e prova de colisões preservadas. Implementação/execução não foram realizadas neste card documental.
