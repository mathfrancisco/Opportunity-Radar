# F51-09 — telemetria IA completa e sem dupla contagem

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** M
- **Risco:** médio — instrumentação em pontos de retorno pode duplicar fallback ou mascarar cobrança se tentativa HTTP e operação lógica usarem o mesmo contador.
- **Dependências:** F51-01

## Problema e evidência

**Fato:** `ProviderError` em sugestões pode retornar vazio sem `ai_call_record`; a auditoria também observou logs de quota com `failed=0`. Isso demonstra lacuna de telemetria, não um percentual global de dependência de IA. O erro pode nascer no preflight ou após uma requisição, portanto o teste deve distinguir os dois caminhos.
**Hipótese a validar:** registrar operação lógica e tentativa HTTP de provedor de forma distinta, inclusive provider_error, parse_error, preflight e cache; não gravar prompts brutos. Não houve teste de implementação nesta fase documental.

## Objetivo e não escopo

Objetivo: registrar operação lógica e tentativa HTTP de provedor de forma distinta, inclusive provider_error, parse_error, preflight e cache; não gravar prompts brutos.
Não escopo: provedores novos, embeddings, scrape indiscriminado ou mudança de decisão determinística.

## Arquivos e símbolos existentes

- [opportunities/suggestions.py](../../../src/opportunity_radar/opportunities/suggestions.py).
- [matching/groq.py](../../../src/opportunity_radar/matching/groq.py).
- [platform/ai/breaker.py](../../../src/opportunity_radar/platform/ai/breaker.py).
- [platform/config.py](../../../src/opportunity_radar/platform/config.py).
- [test_suggestions.py](../../../tests/backend/opportunities/test_suggestions.py).
- Arquivos/migrações novos são propostos somente após reutilização comprovadamente insuficiente.

## Tarefas detalhadas

1. Mapear cada retorno de `suggestions` e `matching/groq.py` para uma operação lógica correlacionada (`operation_id`), incluindo resultado determinístico de degradar sem sugestão.
2. Abrir uma tentativa HTTP (`attempt_id`) somente imediatamente antes do transporte e encerrá-la após resposta, timeout ou erro de transporte; fallback cria nova tentativa ligada à mesma operação, não nova operação.
3. Registrar breaker/preflight e cache como operação terminal sem tentativa HTTP, sem chamada gasta e sem atribuir tokens zero; `usage` só existe quando o provedor a informa.
4. Registrar `provider_error`, `parse_error`, quota e fallback com estado e latência por tentativa. Somar usage de toda tentativa que o reporte, inclusive HTTP falho; absence de usage permanece `unknown`.
5. Calcular completude por coorte de operações iniciadas na janela, com período de graça para in-flight e recuperação de crash; publicar separadamente terminais, pendentes, recuperadas e tentativas HTTP, sem prompt bruto ou PII.

## Contratos e invariantes

- Cache/preflight são operações lógicas sem chamada HTTP e sem tokens, nunca “chamada gasta” de custo zero.
- Fallback tem uma operação lógica e N tentativas HTTP, nunca N operações; uma tentativa abre somente após o transporte ser efetivamente iniciado.
- Toda operação recebe um único estado terminal ou permanece in-flight até expirar a graça/ser recuperada; tokens ausentes são `unknown`, nunca zero.
- Tentativa HTTP falha que traz `usage` contribui para tokens; tentativa sem `usage` é contabilizada como desconhecida.
- Nenhum evento contém PII ou prompt bruto.

## Critérios de aceite

| ID | Arranjo e ação | Assert e evidência |
| --- | --- | --- |
| AC01 | Em [test_suggestions.py](../../../tests/backend/opportunities/test_suggestions.py), fake transport registra que enviou a requisição e então lança erro de conexão. | Uma operação `provider_error`, uma tentativa HTTP falha com `transport_started=true`, `failed=1` no lote e correlação entre os dois registros; erro de preflight não satisfaz este AC. |
| AC02 | Fake provider responde HTTP 200 com corpo JSON inválido e sem campo `usage`. | Operação termina `parse_error`; tentativa guarda status 200, latência e tokens `unknown`, sem criar segunda operação. |
| AC03 | Breaker aberto e, em execução separada, cache válido são avaliados antes do fake transport. | Há operações `preflight` e `cache_hit`, zero tentativas HTTP, zero chamadas ao fake transport e nenhum token classificado como zero. |
| AC04 | Primário devolve HTTP 429 com `usage.total_tokens=12`; fallback devolve HTTP 200 com `usage.total_tokens=30`. | Uma operação contém duas tentativas ordenadas; o agregado soma 42 tokens reportados, não descarta a tentativa falha, e marca `unknown` somente onde usage faltar. |
| AC05 | Relatório recebe coorte iniciada na janela: uma terminal, uma in-flight dentro da graça e uma crashada que é recuperada para terminal. | Completude informa iniciadas=3, terminal=2, in_flight=1 durante a graça e depois terminal=3/recovered=1; não exige terminais iguais a iniciadas na mesma janela de início. |

## Falhas e casos negativos

- Preflight sem transporte não pode gerar tentativa HTTP; erro de transporte após envio não pode ser reclassificado como cache.
- Retry/fallback não pode criar duas operações lógicas nem ocultar usage de uma resposta falha.
- Teste de integração que altera dados usa banco isolado com sufixo `_test`.

## Rollout, rollback e entregáveis

Rollout inicia com escrita aditiva em uma coorte de sugestões, compara agregados antigos e novos por `operation_id` e mantém a retenção existente. Se houver cardinalidade duplicada, rollback desliga o novo agregador sem apagar eventos, preservando rastreio para reconciliação. Entregar mapa de eventos, consulta por coorte com período de graça e relatório de completude.
