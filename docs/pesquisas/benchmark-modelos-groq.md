# Benchmark de modelos Groq — 120B × 20B × Qwen para `job_match`

Card [F20-22](../44-roadmap-fase-20/fase-20/f20-22-benchmark-de-modelos.md). Depende do
harness de [F20-21](../44-roadmap-fase-20/fase-20/f20-21-conjunto-de-avaliacao-no-groq.md)
(`scripts/eval_analysis.py`) e do baseline real já coletado:
`docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json`
(`openai/gpt-oss-120b`, `reasoning_effort=low`, 50 casos, `cases_digest` `1afa75cd3102a0d572fae7625cb3ae722815e9db5913df19508b077625bc2ba2`).

## Status desta sessão (2026-09-27)

Trabalho feito **sem nenhuma chamada real ao Groq**: harness, gerador de comparação e
roteamento por tarefa com testes de fake/`httpx.MockTransport`. As 5 rodadas que faltam
(120B×medium, 20B×low, 20B×medium, Qwen×low, Qwen×medium) ficam para os dias seguintes —
plano de execução na seção "Plano de rodadas" abaixo, escrito **antes** de rodar, para
que o critério de decisão não mude depois de ver os números.

## Critério de decisão (escrito antes de rodar; SPEC 43 §4)

Escolhe-se, entre as variantes cujo acerto de rótulo fica a até **2 pontos percentuais**
do melhor observado e cujo **JSON válido** (`completed_rate`, conjunto reservado) é **≥
98 %**, o **menor modelo** (menor contagem de parâmetros no nome, ex. `20b` < `27b` <
`120b`); empate de tamanho é resolvido pela menor latência p95. Se nenhuma variante
atinge os dois limiares, a rota atual (`openai/gpt-oss-120b`, `AI_REASONING_EFFORT=low`)
é mantida e a razão fica registrada.

"Acerto de rótulo" é a rubrica humana (`human_review[case].adherence`) — o que o
`score_case` não pode julgar sozinho — não um número que `scripts/eval_analysis.py`
calcula. Enquanto qualquer variante não tiver a rubrica preenchida, a decisão fica
pendente; `matching/benchmark.decide()` recusa a escolher um modelo nesse caso em vez de
estimar.

## Ferramental construído neste card

- `scripts/eval_analysis.py` (já existia, F20-21): `--model` fixa a cadeia de
  `job_match` a um único modelo e desliga fallback (`resolve_routes`); `AI_REASONING_EFFORT`
  no ambiente controla o esforço. Sem mudança de código: já cobre "rodar as mesmas 50
  casos por modelo, pinado, fallback desligado".
- `src/opportunity_radar/matching/benchmark.py` (novo) — funções puras sobre os JSON que
  `eval_analysis.py` já escreve: `variant_from_report` monta uma linha (modelo, esforço,
  acerto de rótulo, JSON válido, claims conferidos = fidelidade, latência p50/p95,
  tokens médios de entrada/saída); `decide` aplica o critério acima. Testado em
  `tests/backend/matching/test_benchmark.py` com relatórios fabricados (nenhuma chamada
  ao Groq).
- `scripts/benchmark_report.py` (novo) — lê vários JSON de `eval_analysis.py`, monta a
  tabela markdown e a decisão; nunca chama Groq nem recalcula uma pontuação.
- Roteamento por tarefa (F20-09) ganhou um ponto de extensão behind settings:
  `AI_REASONING_EFFORT_JOB_MATCH` / `_JOB_CLASSIFICATION` / `_JOB_EXTRACTION` em
  `platform/config.py`, lidos por `platform/ai/tasks.py::default_routes` via
  `_effort_for`. Todos `None` por padrão → cada tarefa cai em `AI_REASONING_EFFORT`,
  comportamento idêntico ao anterior. Isso é o que permite aplicar a decisão deste
  benchmark a `job_match` sem mexer nas outras tarefas, do jeito que o passo 5 do card
  pede — mas nada muda até a decisão sair do "pendente" (critério do card F20-22, "não
  mudar o critério depois de ver os números" e "não fazer chamada real ao Groq nos
  testes").

## Plano de rodadas (quota diária ~170.000 tokens; uma rodada de 50 casos ≈ 75.000)

A quota é da conta Groq inteira, compartilhada com a janela de 7 dias que já roda em
produção (projeto `opportunity-radar`, não tocado por este card). Duas rodadas de
benchmark no mesmo dia UTC (150k) cabem no teto só se a produção não tiver consumido
quase nada ainda naquele dia; o plano abaixo assume **uma rodada por dia**, a rodar tarde
o bastante para ver o consumo do dia (`platform.ai_quota_usage` / doctor) antes de gastar
mais 75k. Se a produção já tiver usado mais de ~90k no dia, adiar a rodada de benchmark
para o dia seguinte em vez de arriscar bloquear o worker real.

`openai/gpt-oss-120b` × `low` já está feito (baseline-pinned, 2026-09-27). Faltam 5:

`eval_analysis.py` agora é resumível: cada caso terminado vai para um checkpoint JSONL
(por padrão derivado de `--output`, sem a data, para sobreviver a um `--resume` no dia
seguinte) e uma parada por cota não perde o que já rodou. Re-rodar o mesmo comando com
`--resume` pula os casos já no checkpoint em vez de rodar os 50 de novo — é assim que
F20-18 (parou em 10/50) volta a andar sem descartar os 10 já feitos. `--max-tokens N`
para de forma limpa (checkpoint preservado, relatório marcado `partial`) ao atingir N
tokens acumulados na rodada; o pré-voo lê o consumo de hoje em
`platform.ai_quota_usage`, estima o custo da rodada e recusa rodar (`--allow-partial`
ignora essa recusa) se não couber no restante da cota diária.

| Dia (UTC) | Variante | Comando |
| --- | --- | --- |
| D+1 | `openai/gpt-oss-120b` × `medium` | `AI_REASONING_EFFORT=medium python scripts/eval_analysis.py --prompt v1 --model openai/gpt-oss-120b --label benchmark-medium --split reserved --baseline docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json --resume` |
| D+2 | `openai/gpt-oss-20b` × `low` | `AI_REASONING_EFFORT=low python scripts/eval_analysis.py --prompt v1 --model openai/gpt-oss-20b --label benchmark-low --split reserved --baseline docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json --resume` |
| D+3 | `openai/gpt-oss-20b` × `medium` | `AI_REASONING_EFFORT=medium python scripts/eval_analysis.py --prompt v1 --model openai/gpt-oss-20b --label benchmark-medium --split reserved --baseline docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json --resume` |
| D+4 | `qwen/qwen3.8-27b` × `low` | `AI_REASONING_EFFORT=low python scripts/eval_analysis.py --prompt v1 --model qwen/qwen3.8-27b --label benchmark-low --split reserved --baseline docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json --resume` |
| D+5 | `qwen/qwen3.8-27b` × `medium` | `AI_REASONING_EFFORT=medium python scripts/eval_analysis.py --prompt v1 --model qwen/qwen3.8-27b --label benchmark-medium --split reserved --baseline docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json --resume` |

`--split reserved` runs only the reserved cases; drop the flag to run all 50 in one shot
if the day's quota headroom allows it (`--split` merely filters `--cases`, the token
cost of the smaller run is proportionally smaller, not "reserved *and then* all"). Every
command writes `data/evals/<date>-v1-<model>-benchmark-<effort>.json` and `.md`
(`scripts/eval_analysis.py` names the file from `--model` and `--label`); `--resume` is
a no-op the first time a command runs and picks up where it stopped on any later run.

After D+5, fill each report's `human_review[case_id]` (`adherence`, `support`) by hand —
that is the "acerto de rótulo" the criterion needs — then compare all six in one table:

```bash
python scripts/benchmark_report.py \
  docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json \
  data/evals/<D+1 file>.json data/evals/<D+2 file>.json data/evals/<D+3 file>.json \
  data/evals/<D+4 file>.json data/evals/<D+5 file>.json \
  --split reserved \
  --output docs/pesquisas/benchmark-modelos-groq-decisao.md
```

Only after that report shows `decided: true` does step 5 of the card (updating
`default_routes`, `Settings` defaults and SPEC 43 §6) apply — and only to `job_match`,
via `AI_REASONING_EFFORT_JOB_MATCH` / `GROQ_REASONING_MODEL`, never to the eligibility,
score or verdict rules ("Não fazer" of this card).

## Resultado

**Pendente.** Nenhuma das 5 rodadas restantes foi executada nesta sessão (nenhuma
chamada ao Groq, por instrução deste card). A rota `job_match` permanece
`openai/gpt-oss-120b` @ `low` (baseline-pinned) até o relatório completo decidir o
contrário pelo critério acima.
