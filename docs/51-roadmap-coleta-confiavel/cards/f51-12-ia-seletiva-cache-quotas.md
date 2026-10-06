# F51-12 — IA seletiva por conteúdo, cache e quotas

- **Status:** Parcial — medição de partida feita em 2026-10-06; política ainda não implementada
- **Prioridade:** P1
- **Esforço estimado:** M
- **Risco:** alto para bloquear análises solicitadas ou consumir quota interativa; elegibilidade do worker não pode invalidar uma solicitação explícita do usuário.
- **Dependências:** F51-09 (telemetria IA completa); F51-10 (fila justa e defer).

## Medição de partida (2026-10-06, base de dev, somente leitura)

Perfil ativo `b0ad7958`. Configuração do worker: `WORKER_ANALYZE_VERDICTS=HIGH_PRIORITY,
RECOMMENDED`, lote de 3, `AI_DAILY_TOKENS_SOFT_LIMIT=170000`, `AI_DAILY_REQUESTS_SOFT_LIMIT=850`,
reserva interativa de 100, `WORKER_SUGGEST_ENABLED=true`.

**Fila de análise hoje.** 520 avaliações atuais de topo (17 `HIGH_PRIORITY`, 503
`RECOMMENDED`), 516 delas sem análise concluída para a avaliação atual. A
fila já filtra por veredito e por área-alvo. Não filtra:

| Condição | Vagas de topo |
| --- | ---: |
| Sem descrição (nula ou até 200 caracteres) | 225 |
| Fechada (`lifecycle_status = CLOSED`) | 54 |
| Fora das áreas-alvo (a fila já exclui) | 19 |
| Duplicata (`duplicate_of`) | 0 |

`WATCHLIST` tem 8.857 avaliações e hoje não entra sozinha. Com o `matching-v5` completo, o
topo deve cair para perto das vagas `JUNIOR`/`MID` (200 hoje), porque `UNKNOWN` para em
`WATCHLIST`.

**Análise repetida.** 699 análises concluídas cobrem 248 vagas: 2,8 por vaga, e 197 vagas
foram analisadas mais de uma vez (126 delas três vezes). São 679 chaves de cache distintas.
`rules_version` e `taxonomy_version` entram em `analysis_key`, e o `payload_hash` inclui o
veredito; cada troca de versão de regra refaz a análise da mesma vaga.

**O que a análise muda.** Veredito e pontuação: nada, por contrato (a análise é consultiva).
`recommended_review` veio `true` em 699 de 699: o campo não separa nada. Sugestão de campo:
37 criadas (34 `seniority`, 3 `role_family`), nenhuma aceita nem rejeitada. Não há medida de
"análise lida pelo usuário"; não existe telemetria para isso.

**Tokens.** Média por análise concluída: 1.114 de entrada e 561 de saída, 1.675 no total.
Com o teto de 170.000 tokens por dia por modelo, cabem cerca de 100 análises por dia por
modelo; o teto de requisições (850) nunca é o limite. Por dia, em `ai_call_record`:

| Dia | Provedor | Chamadas | Com sucesso | Tokens |
| --- | --- | ---: | ---: | ---: |
| 2026-10-06 | groq | 108 | 107 | 165.577 |
| 2026-10-06 | tokenharbor | 78 | 75 | 68.575 |
| 2026-10-05 | groq | 97 | 96 | 169.299 |
| 2026-10-04 | groq | 28 | 28 | 48.871 |
| 2026-09-29 | groq | 193 | 150 | 254.002 |

Em 2026-10-06 os cinco modelos chegaram ao teto diário de tokens em `ai_quota_usage`.
Falhas por quota gravadas como `AI_FAILED / QUOTA_EXHAUSTED`: 2.217, contra 699 concluídas.
Operações de sugestão em 2026-10-06: 74 com sucesso, 1.399 `preflight / quota` e 386
`deferred / quota`.

**Achado a investigar (F51-09).** Em 2026-10-06, `ai_quota_usage` registra consumo sem
chamada correspondente em `ai_call_record`: `openai/gpt-oss-20b` 145 requisições e 169.372
tokens, `tokenharbor:deepseek-v4.1-flash:free` 148 e 169.499, `qwen/qwen3.8-27b` 191 e
168.732, todos com zero chamadas gravadas no dia; `tokenharbor:mimo-v2.6-flash:free` 182
requisições contra 78 chamadas. Causa não determinada. Hipóteses: script fora do worker
usando o `QuotaGuard` sem telemetria, ou reserva liquidada pelo valor estimado depois de
erro. Enquanto não for explicado, a quota do dia é gasta por algo que a telemetria não vê.

**O que a medição diz sobre os itens propostos:**

- Reduzir a entrada (sem descrição, fechada): corta até 279 das 520 de hoje (as duas condições se sobrepõem em 21 vagas: 258 distintas). Implementar.
- Cache sem `rules_version` e `taxonomy_version`: é a maior repetição medida (2,8 análises
  por vaga). Implementar; o veredito continua na chave.
- Teto diário por provedor com fila por pontuação: o teto de tokens já existe; falta a
  estimativa de "cabe com folga de 20%" (cerca de 80 análises por dia por modelo).
- Grupo de vagas iguais em locais diferentes: não medido.
- Trocar IA por regra (item 4): bloqueado, nenhuma regra por descrição passou no portão do
  F51-11.
- Trechos relevantes e modelo local (item 5): não medidos.

Nada disso foi implementado nesta sessão; ACs 01 a 06 seguem abertos.

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
