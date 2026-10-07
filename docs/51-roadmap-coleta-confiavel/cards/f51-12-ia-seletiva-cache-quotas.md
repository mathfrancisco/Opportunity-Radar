# F51-12 — IA seletiva por conteúdo, cache e quotas

- **Status:** Parcial — filtros de entrada e chave sem versão de regra em `main` (PR #52); teto diário e política de sugestão no PR #58, aberto
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

## Causa do consumo sem registro (2026-10-06, quarta sessão)

Não é vazamento de reserva. Todo o consumo de `ai_quota_usage` sem linha em
`ai_call_record` em 2026-10-06 aconteceu antes de 03h31min11s UTC, horário da primeira
linha de `ai_operation_record`. Até ali o worker rodava a versão de `suggestions.py` do
commit `0bec250`, que fazia chamadas reais de `job_classification` e não gravava registro
de chamada (`record_calls` não aparece nesse arquivo antes do commit `1832f81`). A partir de
03h32 UTC, `tokenharbor:mimo-v2.6-flash:free` fecha: 72 requisições na quota e 72 registros
de chamada. Os tokens diferem em 4.757 (67.928 contra 63.171): três tentativas com falha têm
uso desconhecido e ficam pelo valor estimado. `openai/gpt-oss-120b` (`job_match`) fecha em
165.577 tokens dos dois lados.

As hipóteses do achado ficam assim: script fora do worker usando o `QuotaGuard`, descartada
(o único `reserve` fora do roteador é a sonda do worker, que libera em seguida); reserva
liquidada pelo estimado depois de erro, verdadeira só para tentativa com uso desconhecido, o
que explica a diferença de 4.757 tokens e não o consumo sem registro.

O PR #54 acrescenta um teste de invariante sobre o `AIRouter` e o `QuotaGuard` reais (144
casos com provedor falso e com os adaptadores de produção): depois de `run`, o contador de
cada modelo é explicado por uma tentativa. Ele achou dois caminhos latentes, corrigidos: erro
de tipo `CANCELLED` sem liberar a reserva (nada em `src` o levanta hoje) e cancelamento
durante a reserva. Nenhum dos dois explica os números acima.

## Implementação (2026-10-06 e 2026-10-07)

- **PR #52, em `main`:** a fila automática de análise deixa de fora vaga fechada e vaga com
  descrição nula ou de até 200 caracteres; o pedido explícito não é afetado. `rules_version`
  e `taxonomy_version` saem de `analysis_key` e do resumo reutilizável do payload
  (`ANALYSIS_KEY_VERSION` = `analysis-key-v5`); veredito, conteúdo, perfil, prompt, modelo e
  rota continuam na chave. Análises gravadas com a chave anterior viram falta de cache uma
  vez. Testes: AC01 (metade da análise) e AC02.
- **PR #58, aberto:** teto diário do job automático em 80% do teto de tokens
  (`worker_analyze_daily_cap_fraction`), sem gravar `AI_FAILED`, tentativa nem cooldown; com
  a estimativa do adaptador (5.900 tokens) são cerca de 77 análises por dia por modelo.
  Sugestão de campo só para vaga com campo `UNKNOWN` e veredito de topo no perfil ativo; o
  job de sugestão não cria operação quando nenhum modelo da rota tem saldo no dia. Testes de
  AC01 (metade da sugestão), AC03, AC04, AC05 e AC06.
- **Aberto:** o AC06 recebe "resultado útil" do chamador ou o lista como lacuna; a
  definição é humana e não está nos cards. O efeito na base de dev não foi medido: a stack
  de dev não foi reconstruída com este código.

## Trechos relevantes e modelo local (item 5): não será feito nesta SPEC (2026-10-07)

Decisão do agente, com a autorização do dono de decidir o que o card deixa em aberto. O item
5 é uma proposta da medição de partida; não é critério de aceite do card.

- **Não há o que medir sem escrever código da SPEC 51.** Não existe recorte de trechos nem
  provedor Ollama em `src` (nenhuma ocorrência de `ollama`), e `scripts/eval_analysis.py` só
  fala com o Groq. Um recorte atrás de flag é mudança de código da SPEC 51 e reabre a janela
  de sete dias do F51-18.
- **Não há quota para a comparação.** Uma rodada do `eval_analysis.py` tem 50 casos e gasta
  cerca de 100 mil tokens; a comparação pede duas (com e sem recorte). Em 2026-10-07, 14h10
  UTC, o modelo principal (`openai/gpt-oss-120b`) tinha 130.762 tokens gastos no dia, de um
  teto de 170.000; em 2026-10-06 os cinco modelos da rota fecharam entre 165.577 e 169.499.
- **O modelo local não é comparável.** O Docker tem 4.106.457.088 bytes de memória (3,8 GiB)
  e o único modelo local é o `llama3.2:3b`; medir a qualidade dele contra o `openai/gpt-oss-120b`
  não diria nada sobre trocar o padrão.
- **O ganho maior já entrou.** Os PRs #52 e #58 cortaram a entrada (vaga fechada ou sem
  descrição), a repetição por versão de regra e o teto diário, que eram os custos medidos.

O padrão não muda. Reabrir se, com a fila seletiva em produção por uma janela inteira, o
teto diário de tokens ainda for o limite: aí o recorte entra como card próprio, com flag
desligada por padrão e a medição feita num dia com 200 mil tokens livres no modelo principal.

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
