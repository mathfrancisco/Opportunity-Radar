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
