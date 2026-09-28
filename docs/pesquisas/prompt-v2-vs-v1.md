# Prompt `v2` × `v1` — vaga e experiências no payload, pt-BR com evidência

Card [F20-18](../44-roadmap-fase-20/fase-20/f20-18-prompt-v2-com-a-vaga.md). Depende do
baseline real de F20-21
(`docs/44-roadmap-fase-20/evidencias/baseline-groq-f20-21-2026-09-27.md`).

## Status desta sessão (2026-09-27)

O `GROQ_API_KEY` já esbarrou no teto diário de tokens (~170.000/dia, ver o baseline
acima) na mesma rodada UTC de hoje que produziu o baseline de F20-21. **Nenhuma chamada
real ao Groq foi feita nesta sessão** — trabalho todo offline: artefato de prompt,
schema, payload builder e testes com provedor fake/`httpx.MockTransport`. A comparação
real `v1` × `v2` com o conjunto de avaliação de 50 casos (F20-21) fica para amanhã,
quando o teto diário virar.

## O que existe agora

- `prompts/opportunity_analysis/v2/` — `system.md` (pt-BR, regra de evidência: cada
  força/risco cita um trecho literal de `posting` ou `profile`, ou vira inferência),
  `user.md.j2` (inclui `{{ posting }}` e `{{ profile_history }}` além dos placeholders
  de `v1`), `metadata.yaml` (`schema_version: analysis-v2`, `profile_history: true`),
  `output.schema.json` (gerado de `OUTPUT_SCHEMAS["analysis-v2"]`), `examples.json` (2
  exemplos, um com evidência conferível, um em que a falta de trecho literal vira
  inferência em vez de risco inventado).
- `GroqAnalysisAdapter` (`src/opportunity_radar/matching/groq.py`) passou a expor
  `profile_history` como bloco próprio no payload, além de continuar mesclando-o em
  `profile` (assim o texto da experiência permanece citável como evidência: o schema só
  conhece as fontes `"posting"` e `"profile"`, `CLAIM_SOURCES` em `matching/analysis.py`,
  não alterado por este card). `requires` já ligava `posting`/`profile_history` quando o
  prompt pede (infraestrutura do F16-07); nada mudou nesse contrato.
- `parse_analysis` (não alterado): uma citação que não existe literalmente no bloco que
  o `source` nomeia é descartada com `AnalysisFailureCode.SCHEMA_MISMATCH` — comportamento
  coberto por
  `tests/backend/matching/test_prompts.py::test_v2_claim_with_evidence_absent_from_the_source_is_rejected`.

## Validação feita hoje (offline, sem Groq)

```bash
docker compose -p f20v2 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q \
  tests/backend/matching/test_prompts.py tests/backend/matching/test_groq_adapter.py
docker compose -p f20v2 -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q
docker compose -p f20v2 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20v2 -f compose.yaml -f compose.dev.yaml run --rm api mypy
docker compose -p f20v2 -f compose.yaml -f compose.dev.yaml run --rm api python scripts/export_prompt_schema.py --check
```

Resultado: 41/41 testes visados (`test_prompts.py` + `test_groq_adapter.py`) verdes;
suíte completa 924 passed, 10 skipped (pré-existentes, não relacionados); `ruff` e
`mypy` sem apontamentos (118 arquivos); `--check` confirma `v1` e `v2` batendo com o
validador. Projeto Docker isolado `-p f20v2` (nunca `opportunity-radar`), removido com
`docker compose -p f20v2 ... down -v` ao final.

## O que falta: a comparação real (amanhã)

Rodar o conjunto de avaliação de F20-21 (os mesmos 50 casos versionados) com `v2`,
comparando contra o baseline já commitado de `v1`
(`docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json`).
Comando exato, com `--model` pinado (mesma lição do baseline de F20-21: sem `--model`, o
fallback liga e mistura modelos na amostra) e `--quota-wait-seconds` para absorver o
Quota Guard de minuto sem parar a rodada inteira:

```bash
docker compose -p f20v2eval -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd):/workspace" api python scripts/eval_analysis.py \
  --cases /workspace/prompts/opportunity_analysis/eval/cases \
  --output /workspace/data/evals --prompt v2 \
  --model openai/gpt-oss-120b --label v2-vs-v1-baseline \
  --baseline /workspace/docs/44-roadmap-fase-20/evidencias/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json \
  --quota-wait-seconds 65
```

Projeto Docker isolado `-p f20v2eval` (nunca `opportunity-radar`); rodar só depois que o
teto diário de tokens virar (UTC), com o mesmo `GROQ_API_KEY` do `.env` local; sem
segredo logado, impresso ou commitado.

### Regra de decisão (card, passo 7)

- Se `v2` **não piora nenhum critério** da tabela (`completed_rate`, `coverage`,
  `inventions`, `portuguese`, e agora `fidelity`/`grounded`, que só existem a partir do
  schema `v2`) no conjunto `reserved`, trocar `ai_analysis_prompt` para `"v2"` em
  `Settings` (`src/opportunity_radar/platform/config.py`) e em `.env.example`.
- Senão, manter `v1` como padrão e registrar aqui o motivo (qual critério piorou e por
  quanto), sem tocar em elegibilidade, score, veredito ou fatores do matching.

**Esta sessão não decide**: nem o `Settings.ai_analysis_prompt` nem o `.env.example`
foram alterados. `v1` continua o padrão até a rodada real de amanhã.

## Rodada real (2026-09-28, UTC) — parcial, orçamento estourado

Executado o comando exato acima em stack isolada `-p f20v2eval` (nunca
`opportunity-radar`). A janela diária (UTC) já tinha virado (baseline de ontem esbarrou
no teto ainda em 2026-09-27; esta rodada é 2026-09-28 01:5x UTC). Resultado gravado em
`data/evals/2026-09-28-v2-openai_gpt-oss-120b-v2-vs-v1-baseline.{json,md}`, copiado para
`docs/44-roadmap-fase-20/evidencias/2026-09-28-v2-openai_gpt-oss-120b-v2-vs-v1-baseline.{json,md}`
(sem segredo: conferido com `grep` por `gsk_` antes de copiar).

**A rodada não completou os 50 casos.** Parou em 10 processados (12 tentados: 2
`QUOTA_BLOCKED` descartados da amostra) porque o TPM (tokens por minuto) do modelo
pinado se mostrou muito mais apertado do que o card assumia: cada chamada de `v2` real
consumiu **~3.4k tokens** (entrada+saída) contra os ~1.5k que o orçamento do card supunha
(75k/50 casos) — `v2` inclui `posting` e `profile_history` inteiros no payload, então
custa 2-3× mais que `v1` por chamada (ver `prompt_tokens`/`output_tokens` na tabela
abaixo). No caso 12 (`12-ai-11-review_required`) o guard esperou os 65s de
`--quota-wait-seconds` e ainda assim viu o teto exaurido de novo, e o script para a
rodada inteira nesse ponto (comportamento esperado do script, não um bug desta sessão).
Não houve outra tentativa: rodar os 50 casos de novo custaria perto do orçamento diário
inteiro (~170k) sozinho, sem sobrar nada para F20-24 no mesmo dia, e a chave é
compartilhada com os workers de F20-22/F20-23 em paralelo — daí os vários "quota
exhausted; waiting 65s" já nas primeiras chamadas.

| Critério | Reservado | Ajuste | Todos | Baseline (reservado) | Comparação |
| --- | ---: | ---: | ---: | ---: | --- |
| completed_rate | 0.500 | 0.500 | 0.500 | 1.000 | piora |
| fidelity | 0.000 | 0.500 | 0.400 | — | não comparável |
| grounded | — | 0.667 | 0.667 | — | sem dado |
| coverage | 0.000 | 0.000 | 0.000 | 0.000 | empate |
| inventions | 0.000 | 0.000 | 0.000 | 0.000 | empate |
| portuguese | 1.000 | 0.991 | 0.993 | 0.123 | melhora |
| prompt_tokens | 2162 | 2749 | 2602 | 890 | piora |
| output_tokens | 580 | 703 | 673 | 451 | piora |
| total_ms | 1690 | 1982 | 1909 | 1663 | piora |

Amostra do `reserved` (a que decide) tem só 2 casos (`08-fora_de_area-32`,
`11-fullstack-37`), um deles `AI_FAILED (SCHEMA_MISMATCH)` — não é estatisticamente
sólido, mas já mostra `completed_rate` **piorando** (0.500 vs 1.000 no baseline) e custo
de token bem acima do `v1`, o suficiente para não passar na regra de troca do passo 7.

### Decisão

**Manter `v1` como padrão.** `Settings.ai_analysis_prompt` e `.env.example` não foram
alterados. Motivo: no `reserved`, `completed_rate` piorou (0.500 vs 1.000) e
`prompt_tokens`/`output_tokens`/`total_ms` pioraram também; a regra de troca exige que
`v2` não piore nenhum critério do `reserved`, e aqui piorou vários — mesmo com a amostra
pequena, isso já basta para não trocar. Além disso, o custo real por chamada (~3.4k
tokens) inviabiliza rodar os 50 casos completos no orçamento diário compartilhado sem
sacrificar F20-24 no mesmo dia; uma rodada completa fica pendente para uma janela sem
concorrência de outros workers no `GROQ_API_KEY`.
