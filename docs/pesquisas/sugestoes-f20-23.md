# Precisão das sugestões de classificação (F20-23)

- **Status:** Medido offline com casos sintéticos/anonimizados; medição real no acervo é
  o próximo passo (worker continua desligado, `worker_suggest_enabled: bool = False`).
- **Card:** [F20-23](../44-roadmap-fase-20/fase-20/f20-23-classificacao-assistida.md)
- **SPEC:** [43-spec-llm-cloud-e-consolidacao.md](../43-spec-llm-cloud-e-consolidacao.md), §6, §6.1
- **Contexto:** baseline real do acervo (`opportunity-radar`, medição de 7 dias em
  andamento, não tocado por este card) tem `seniority = UNKNOWN` em 328 das 648
  oportunidades (50,62%); o alvo do card/F17-06 é reduzir isso a metade. Este card não
  toca o projeto `opportunity-radar` nem chama o Groq — a implementação usa
  `httpx`/`AIRouter` com um provedor fake em todos os testes.

## Por que a medição aqui é offline

O card exige medir precisão **antes** de ligar o job por padrão (critério de aceite:
"Precisão medida registrada antes de ligar por padrão"). Este worker não pode chamar o
Groq real (regra do PR) nem tocar o acervo do projeto `opportunity-radar` em execução.
A medição abaixo usa 12 vagas sintéticas, com texto e evidência inventados (nenhum dado
do acervo real), rodadas contra o `AIRouter` com um provedor fake que responde um script
fixo — a mesma técnica usada em `tests/backend/opportunities/test_suggestions.py`. Ela
prova a lógica de gatilho, o descarte por evidência e a idempotência; **não** é uma
medição de precisão do modelo real, porque um provedor fake não erra do jeito que o
`fast` model erraria.

## Medição sintética (gatilho, descarte, idempotência)

| Caso | Campo pendente | Resposta simulada | Resultado esperado |
| --- | --- | --- | --- |
| 1–3 | `seniority` | valor + evidência literal no texto | sugestão `PENDING` criada |
| 4–6 | `work_mode` | valor + evidência que não aparece no texto | descartada (sem sugestão) |
| 7–9 | `role_family` | valor `null` (modelo inseguro) | nenhuma sugestão criada |
| 10 | campo já resolvido pela regra | modelo responde mesmo assim | resposta ignorada, sem sugestão |
| 11–12 | mesma oportunidade, mesma versão, 2 chamadas | 2ª chamada não deveria acontecer | 2ª chamada não ocorre (idempotência) |

Todos os 12 casos passam com o comportamento esperado
(`tests/backend/opportunities/test_suggestions.py`, executado com
`RUN_DATABASE_INTEGRATION=1` contra o Postgres isolado do projeto `f20cls`).

## Passo restante (fora do escopo deste PR)

1. Selecionar, no acervo real (projeto `opportunity-radar`, sem interromper a medição de
   7 dias), uma amostra de ~30 vagas com `seniority`, `role_family` ou `work_mode`
   `UNKNOWN` (dentro das 328/648 atuais).
2. Rotular manualmente o valor correto de cada campo ambíguo.
3. Rodar `suggest_fields_pending` uma vez, isolado (projeto docker compose separado do
   `opportunity-radar`, ou um script pontual chamando `opportunity_radar.opportunities
   .suggestions.suggest_fields` linha a linha) com `AI_ENABLED=true` e a chave real do
   Groq, **fora** deste PR.
4. Comparar a sugestão do modelo com o rótulo manual: registrar precisão (sugestões
   aceitáveis / sugestões com evidência válida) e taxa de descarte por evidência.
5. Só então decidir `worker_suggest_enabled=true` em produção, e atualizar este arquivo
   com o número medido.
