# Baseline real no Groq — F20-21 (2026-09-27)

Card [F20-21](../fase-20/f20-21-conjunto-de-avaliacao-no-groq.md). Rodada real contra a
API do Groq (não mockada), usando `GROQ_API_KEY` do `.env` local, sobre os 50 casos
versionados em `prompts/opportunity_analysis/eval/cases/` (10 Java, 10 fullstack, 10 IA,
10 fora de área, 10 inelegíveis).

## Como foi rodado

```bash
docker compose -p f20groq -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd):/workspace" api python scripts/eval_analysis.py \
  --cases /workspace/prompts/opportunity_analysis/eval/cases \
  --output /workspace/data/evals --prompt v1 \
  --model openai/gpt-oss-120b --label baseline-pinned --quota-wait-seconds 65
```

- Projeto Docker Compose isolado `-p f20groq` (nunca `opportunity-radar`); Postgres e
  migrações próprios, sem tocar no ambiente de desenvolvimento.
- `--model openai/gpt-oss-120b` fixa a rota `job_match` num único modelo e desliga o
  fallback (comportamento documentado no docstring de `scripts/eval_analysis.py`) — uma
  primeira tentativa sem `--model` deixou o fallback ligado e ~29% das chamadas (20 de
  69) foram silenciosamente respondidas por `qwen/qwen3.8-27b` em vez do modelo pinado;
  esse relatório foi descartado e a rodada foi refeita com `--model` para produzir uma
  baseline de um único modelo, como o card pede.
- `--quota-wait-seconds 65`: espera e tenta de novo uma vez ao esbarrar no Quota Guard
  (F20-12/F20-13), em vez de parar a avaliação inteira por um limite de minuto.
- Apenas o conteúdo já anonimizado dos casos (F20-15) foi enviado; nenhum perfil real.
- Nada rodou no CI; a chave nunca foi logada, impressa ou commitada.

### Correção no harness durante a execução

A primeira tentativa (sem `--model`) parou depois de 5 casos com
`quota exhausted; waiting 36081s before one retry` — uma espera de ~10h. Investigação:
`QuotaGuard.next_available_at` (`src/opportunity_radar/platform/ai/quota.py`) checa se a
janela de minuto ou de dia já **armazena** um total que alcançou o teto; quando o
`reserve()` que falhou foi rejeitado por sua própria estimativa ultrapassar o teto da
janela de minuto (ex.: 5693 tokens já usados + 5000 estimados > 7999 de teto, mas 5693
por si só não "parece" esgotado), a função caía no ramo de "corrida concorrente" e
chutava o limite do dia (`day_start + timedelta(days=1)`) em vez do próximo minuto. Isso
transforma um estouro transitório de janela de minuto (que se resolve em até 60s) numa
espera de horas.

Correção mínima aplicada (dentro do escopo do card — "harness precisa de algo que falta,
implemente com teste"): o chute de fallback em `next_available_at` passou de
`day_start + timedelta(days=1)` para `minute_start + timedelta(minutes=1)`, com o
comentário explicando o porquê. Teste novo:
`tests/backend/test_ai_quota_integration.py::test_next_available_at_guesses_the_minute_boundary_on_a_token_near_miss`
reproduz o quase-esgotamento (8 + 5 > 10 tokens/minuto) e confere que a espera sugerida é
o próximo minuto, não o próximo dia. Suítes `test_ai_quota_integration.py`,
`test_quota.py` e `test_eval_scoring.py` (41 testes) verdes; `ruff check .` e `mypy`
sem apontamentos.

## Resultado

- **Modelo:** `openai/gpt-oss-120b` (único; fallback desligado). Cadeia reportada pelo
  servidor: `groq → openai/gpt-oss-120b`.
- **Prompt:** `v1` (`opportunity_analysis/v1`), `prompt_digest`
  `264e6f770284a58e882dc03e459a9de2b96be6525c503e2d7f66874fa2c971f2`.
- **Conjunto:** 50 casos, `cases_digest` `1afa75cd3102a0d572fae7625cb3ae722815e9db5913df19508b077625bc2ba2`.
- **Status:** 50/50 `AI_COMPLETED`. Nenhuma falha, nenhum caso bloqueado por quota
  (`quota_blocked_case: null`). Nenhum caso é `critical` no conjunto atual, então
  `--repeat` (3) não se aplicou — cada caso rodou uma vez.
- **Requisições reais no Groq:** 50 (uma por caso; sem repetição, sem fallback). A
  execução esbarrou no Quota Guard de minuto 6 vezes ao longo da rodada e esperou 65s
  cada vez antes de retomar — nenhuma perda de caso.
- **Tokens:** 51.541 de entrada + 23.004 de saída = **74.545 tokens** no total dos 50
  casos (médias: 1.031 entrada / 460 saída por caso). Ambas as rodadas do dia (a
  descartada + a válida) somaram ~169.798 tokens no dia UTC 2026-09-27 dos ~170.000 do
  teto diário configurado (`AI_DAILY_TOKENS_SOFT_LIMIT`) — não rodar de novo no mesmo
  dia sem esperar a virada.
- **Latência (`total_ms`, 50 casos):** p50 = 1.613 ms, p95 = 2.580 ms, mínimo 1.179 ms,
  máximo 3.613 ms.

### Métricas por critério (`CRITERIA`, conjunto reservado vs. todos)

| Critério | Reservado (5 casos) | Todos (50 casos) |
| --- | ---: | ---: |
| completed_rate | 1.000 | 1.000 |
| fidelity | — (schema v1 não tem evidência) | — |
| grounded | — (idem) | — |
| coverage | 0.000 | 0.000 |
| inventions | 0.000 | 0.000 |
| portuguese | 0.123 | 0.113 |
| prompt_tokens (média) | 890 | 1.031 |
| output_tokens (média) | 451 | 460 |
| total_ms (média) | 1.663 | 1.723 |

Splits do conjunto: 45 `tuning`, 5 `reserved` — a decisão de troca de prompt/modelo usa
sempre o `reserved` (regra já implementada em `matching/evaluation.py`, não alterada
aqui).

### Leitura honesta dos números (achados, não correções)

- **`coverage = 0` nos 50 casos**: nenhuma resposta do modelo cobriu, por
  correspondência de termos (`matching.evaluation.coverage`, não alterada), nenhum dos
  riscos esperados (`must_mention_risks`) de nenhum caso. Isso é consistente e chama
  atenção — mas se é o modelo de fato não citando o risco, ou o prompt `v1` não pedindo
  isso explicitamente, ou a extração de "riscos" da resposta não bater com a redação do
  rótulo, exige revisão humana (rubrica "Aderência"/"Sustentação" no `.md`, deixada em
  branco de propósito) e não deve ser decidido aqui — não fazer do card veda mudar
  critério de pontuação ou o matching junto com a baseline.
- **`inventions = 0`**: nenhuma afirmação proibida (`must_not_claim`) apareceu em nenhum
  caso — sinal positivo, sem invenção detectada pelo comparador literal.
- **`portuguese ≈ 0.11–0.12`**: das palavras reconhecidas (stopwords PT/EN), só ~11-12%
  são PT — sinal de que a resposta mistura bastante inglês. É uma proporção sobre uma
  lista fixa de stopwords (`_PORTUGUESE_WORDS`/`_ENGLISH_WORDS`), não uma medida de
  idioma completa; registrado como achado para o card F20-18 (prompt `v2`, pt-BR com
  evidência), que depende deste baseline — não é alterado aqui.
- **`fidelity`/`grounded` em branco**: o schema `v1` não carrega evidência citada, então
  essas colunas ficam `None` por design (ver `matching/evaluation.py::fidelity`); a
  rubrica humana (aderência ao veredito, sustentação de cada trecho citado) também fica
  em branco no `.md` para o operador preencher — não preenchida nesta sessão porque exige
  leitura humana das 50 respostas contra o gabarito, fora do que a chamada ao Groq por si
  só prova.

## Arquivos

- `data/evals/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json` — saída bruta do
  harness (não versionado; `data/evals/` está no `.gitignore`), reproduzível pelo comando
  acima. Sem `GROQ_API_KEY` nem qualquer segredo (conferido).
- `data/evals/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.md` — tabela por caso
  gerada pelo mesmo harness.
- Cópia comprometida do JSON e do MD (para rastreabilidade sem depender de `data/evals/`
  local): ver `2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json` e `.md` neste
  mesmo diretório de evidências.

## Verificação

```bash
docker compose -p f20groq -f compose.yaml -f compose.dev.yaml run --rm api pytest -q \
  tests/backend/matching/test_eval_scoring.py
docker compose -p f20groq -f compose.yaml -f compose.dev.yaml run --rm \
  -e RUN_DATABASE_INTEGRATION=1 api pytest -q \
  tests/backend/test_ai_quota_integration.py tests/backend/platform/ai/test_quota.py
docker compose -p f20groq -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20groq -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

41 testes relevantes (22 + 9 + 10) verdes; `ruff` e `mypy` sem apontamentos (118 arquivos
Python).

## Próximo

- Critério de aceite "Baseline versionada" de F20-21 pode ser marcado feito: JSON/`.md`
  com validade (50/50 `AI_COMPLETED`), claims conferidos (`inventions = 0`), acerto de
  rótulo pendente de leitura humana (rubrica em branco por design), latência p50/p95 e
  tokens — todos presentes acima.
- F20-18 e F20-22 dependiam só deste baseline (checar `README.md`/cards) — agora
  desbloqueados para implementação (não implementados nesta sessão).
- F20-23 continua bloqueado: depende de F20-22 (ainda não feito), não diretamente de
  F20-21.
- F20-24 e F20-12 não dependem deste baseline (F20-12 já está "Implementado"; F20-24
  depende de F20-39/F20-17/F20-16/F20-12, sem F20-21 na lista).
