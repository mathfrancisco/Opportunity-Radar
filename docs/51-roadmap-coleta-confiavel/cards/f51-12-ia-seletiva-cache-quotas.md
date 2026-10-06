# F51-12 — IA seletiva por conteúdo, cache e quotas

- **Status:** Planejado
- **Prioridade:** P1
- **Esforço estimado:** M
- **Risco:** alto para bloquear análises solicitadas ou consumir quota interativa; elegibilidade do worker não pode invalidar uma solicitação explícita do usuário.
- **Dependências:** F51-09 (telemetria IA completa); F51-10 (fila justa e defer).

## Problema, fatos e hipótese

O fluxo principal de coleta, classificação explícita por regras, matching/score e busca textual é determinístico; análise semântica e sugestões Groq são opcionais/consultivas. `QuotaGuard` já reserva e liquida quota; `AIRouter` orquestra tentativas, enquanto cache existe no serviço de análise do matching e telemetria em `platform.ai.telemetry`. Sugestões de campos são uma tarefa distinta de análise explicativa de compatibilidade; os dois fluxos não devem compartilhar a mesma política de elegibilidade ou cache sem contrato.

Não há evidência fornecida de que conteúdo pobre aumente chamadas ou de que filtros de conteúdo reduzam custo com valor preservado. Isso fica como hipótese a medir, não como fato ou benefício prometido. A métrica de IA não cobre classificação determinística; a telemetria só descreve chamadas registradas.

## Objetivo e limites

Definir política seletiva que prioriza regra determinística e conteúdo disponível antes de chamadas automáticas do worker, reaproveita cache válido e consome reserva/quota compartilhada. Manter análise explicitamente solicitada disponível quando o usuário a pede, mesmo se a vaga estiver fora dos critérios de fila automática; se conteúdo insuficiente impedir qualidade, retornar motivo/abstenção clara em vez de descartar a solicitação. `AI_ENABLED=false` deve desligar toda chamada externa e preservar o core, incluindo score/veredito, coleta, busca textual e dados canônicos.

## Arquivos e contratos existentes

- [`suggestions.py`](../../../src/opportunity_radar/opportunities/suggestions.py): sugestão consultiva para campos desconhecidos e validação de evidência.
- [`analysis.py`](../../../src/opportunity_radar/matching/analysis.py): `AnalysisRequest`, preparação e `analysis_cache_key`.
- [`service.py`](../../../src/opportunity_radar/matching/service.py): execução/reuso de análise e versão de perfil.
- [`repository.py`](../../../src/opportunity_radar/matching/repository.py): elegibilidade de fila versus consulta explícita; análise fora da fila automática ainda pode ser pedida pela página.
- [`router.py`](../../../src/opportunity_radar/platform/ai/router.py), [`quota.py`](../../../src/opportunity_radar/platform/ai/quota.py), [`telemetry.py`](../../../src/opportunity_radar/platform/ai/telemetry.py): cache, reserva compartilhada, registro por chamada.
- [`config.py`](../../../src/opportunity_radar/platform/config.py) e [`worker.py`](../../../src/opportunity_radar/worker.py): `AI_ENABLED`, reserve requests e jobs de análise/sugestão.
- Testes existentes: `tests/backend/matching/test_analysis.py`, `tests/backend/matching/test_service.py` e `tests/backend/opportunities/test_suggestions.py`.

## Tarefas executáveis

1. Especificar duas políticas separadas: (a) sugestão em background só para campos desconhecidos, versão atual, evidência de texto suficiente e sem sugestão vigente; (b) análise de compatibilidade sob solicitação explícita ou fila automática permitida. Filtro de área/veredito vale para fila automática; não deve bloquear página/API de análise explicitamente pedida.
2. Aplicar determinismo primeiro: campos já definidos por regra não chamam IA; campo `UNKNOWN` pode receber sugestão consultiva, sem escrever cânone; análise Groq produz explicação estruturada e mantém score/veredito inalterados. Conteúdo insuficiente gera motivo `insufficient_content`/abstenção, não inferência fabricada.
3. Reusar `analysis_cache_key` para análise quando incluir hash do conteúdo submetido, versão do perfil, prompt, modelo/rota e opções relevantes. Se faltar dimensão, estender a chave versionada. Alterar qualquer dimensão cria cache miss. Não reutilizar análise de perfil/prompt/modelo diferente. Para sugestão, não declarar cache pronto se não existe: propor chave própria com hash sanitizado do texto + campos pendentes + prompt version + modelo/rota; definir explicitamente se rota é semântica ou apenas transporte, e incluí-la na chave enquanto essa equivalência não for demonstrada.
4. Reservar chamada antes do provider usando o mesmo `QuotaGuard` e a reserva interativa já configurada (`ai_interactive_reserve_requests`). Background respeita teto descontado da reserva interativa; chamadas interativas usam a quota global segundo o guard existente, sem presumir reserva recíproca para o worker. Falta de quota retorna defer/cooldown; não tenta rota alternativa que ignore guard.
5. Validar degradação completa com `AI_ENABLED=false`: nenhum request externo em worker ou UI; endpoints determinísticos continuam respondendo com os mesmos resultados estruturados; explicação IA indica desativada/indisponível sem alterar registros canônicos.
6. Medir impacto antes de afirmar economia: chamadas e cache hits por tarefa, tokens registrados, latência, quota deferida, sugestões aceitas/rejeitadas, análises reutilizadas e taxa de resultado útil com definição humana. Comparar baseline/piloto com mesmo perfil e coorte; reportar números absolutos, denominadores e campos sem telemetria. Não inventar percentual de redução.

## Critérios de aceite

| ID | Critério mensurável | Given / When / Then | Teste proposto e artefato |
| --- | --- | --- | --- |
| AC01 | Sugestão e análise explícita seguem elegibilidades distintas. | Dada oportunidade fora da fila automática com conteúdo, quando worker roda, então não faz sugestão indevida; quando usuário pede análise explicitamente, então serviço tenta análise (ou retorna motivo de conteúdo insuficiente) sem ser bloqueado pelo filtro da fila. | `test_explicit_analysis_bypasses_only_automatic_queue_filters` (proposto em `tests/backend/matching/test_service.py`); requests falsos e resposta UI. |
| AC02 | Cache de análise invalida em cada dimensão de entrada. | Dada análise com hash H/perfil P/prompt V/modelo M/rota R, quando uma dimensão muda, então há novo cache miss; repetição integral da chave reutiliza sem HTTP. | `test_analysis_cache_key_covers_content_profile_prompt_model_route` (proposto em `tests/backend/matching/test_analysis.py`); chaves e contagem provider. |
| AC03 | Regra determinística evita IA e sugestão não altera cânone. | Dado campo resolvido por regra e outro desconhecido, quando worker processa, então campo resolvido não gera chamada; sugestão no desconhecido permanece consultiva até decisão humana. | `test_ai_runs_only_for_pending_suggestion_fields` (proposto em `tests/backend/opportunities/test_suggestions.py`); zero/uma chamada e snapshot canônico inalterado. |
| AC04 | Quota compartilhada preserva reserva interativa. | Dado worker no teto diário descontado da reserva, quando tenta sugestão/análise em background, então não consome reserva; chamada explicitamente interativa só usa quota segundo o guard compartilhado. | `test_background_ai_respects_interactive_reserve` (proposto); reservas antes/depois e zero HTTP indevido. |
| AC05 | `AI_ENABLED=false` desativa rede e mantém core determinístico. | Dada configuração desligada, quando collection, matching e busca textual são executados, então nenhum provider recebe HTTP e resultados não-IA mantêm score/veredito/conteúdo esperados. | `test_ai_disabled_preserves_deterministic_core` (proposto com fakes em testes matching/opportunities); contagem de HTTP zero e snapshot. |
| AC06 | Benefício/custo é reportado com denominadores reais. | Dado período baseline e piloto de mesma coorte, quando relatório compara tarefas, então mostra requests, tokens registrados, cache hits, resultado útil e ausências de telemetria em números absolutos sem percentual não suportado. | `test_ai_selective_metrics_include_denominators_and_gaps` (proposto em `tests/backend/platform/ai/test_metrics.py`); relatório por tarefa/versão. |

## Falhas, rollout e reversão

Provider indisponível, quota, cache obsoleto, conteúdo insuficiente ou telemetria ausente devem ser estados visíveis, não sucesso. Testes mutáveis usam banco `_test`; rede sempre fake. Rollout em shadow compara elegibilidade e cache sem bloquear pedidos explícitos; depois ativar background com teto existente e observar tarefa separadamente. Reverter seletor ou cache novo mantém registros e pode voltar ao fluxo anterior; nunca desativar determinismo nem consumir reserva interativa por fallback. Entregáveis: política dupla, chave versionada, uso de reserva, prova do modo sem IA e relatório de benefício/custo qualificado. Nenhum teste foi executado nesta tarefa documental.
