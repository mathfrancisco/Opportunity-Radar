# CARD F20-21 — Conjunto de avaliação completo e baseline no Groq

- **Status:** Feito
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-17
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F16-06](../../38-roadmap-ia-e-busca/fase-16/f16-06-conjunto-de-avaliacao.md)

## Resultado

Existe uma baseline do prompt atual no Groq, sobre 50 vagas rotuladas, que toda troca de prompt ou modelo passa a usar.

## Contexto

O harness está em `scripts/eval_analysis.py` e `matching/evaluation.py` (funções puras), com teste em `tests/backend/matching/test_eval_scoring.py`. `make eval-analysis` e `make export-eval-cases` existem. Faltam casos e a baseline.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `arquivo de casos usado por `scripts/eval_analysis.py` (ver o argumento padrão do script)` | completar até 50 casos |
| Alterar | `scripts/eval_analysis.py` | flag `--model` para sobrescrever `groq_reasoning_model`; respeitar o Quota Guard |
| Criar | `docs/44-roadmap-fase-20/evidencias/baseline-groq-f20-21-2026-09-27.md` (evidência real; caminho decidido na execução, não `docs/pesquisas/`) | baseline |

## Passos

1. Rodar `make export-eval-cases` para exportar candidatos do acervo.
2. Rotular até 50 casos: pelo menos 10 Java, 10 fullstack, 10 IA, 10 fora de área, 10 inelegíveis.
3. Adicionar `--model` ao `eval_analysis.py` (sobrescreve o primeiro modelo da rota `job_match`, com fallback desligado).
4. Com `GROQ_API_KEY` no `.env`, rodar `make eval-analysis` e salvar a saída em `eval-analysis-groq-baseline.md` com data, modelo, prompt e custo em tokens.
5. Conferir que o número de requisições cabe na quota do dia antes de rodar (50 casos ≈ 50–150 chamadas).

## Não fazer

- Não rodar no CI.
- Não mudar critérios de pontuação de `matching/evaluation.py` junto com a baseline.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] 50 casos rotulados versionados. **Feito (2026-09-27):** os 26 drafts de lacuna
      (`gap-{java,fullstack,ai}-NN-review_required.json`, 10 Java + 7 fullstack + 9 IA)
      foram revisados — `must_mention_risks`/`must_not_claim` preenchidos seguindo a
      convenção dos 50 casos já rotulados (risco de remuneração ausente, países ausentes,
      skill exigida fora do perfil ou skills não extraídas) — e promovidos para
      `prompts/opportunity_analysis/eval/cases/` (decisão do usuário: aceito
      pré-autorizado; tabela completa em
      `docs/44-roadmap-fase-20/rotulagem/f20-21-eval-cases.md` e `.json`). 1 PII
      encontrado e corrigido (primeiro nome da recrutadora em `gap-java-01`). Para caber
      exatamente em 50 na composição pedida (10/10/10/10/10), os 2 casos `backend`
      (`05`, `07`), o excedente de `fora_de_area` (`17`–`31`, 15 arquivos) e os 9 casos
      `synthetic-*` foram movidos (`git mv`, preservando histórico, não deletados) para
      `prompts/opportunity_analysis/eval/cases-secondary/` — ver justificativa na seção
      "Rebalanceamento" da rotulagem. `eval/cases/` tem 50 arquivos: 10 Java, 10
      fullstack, 10 IA, 10 fora de área, 10 inelegíveis.
      `tests/backend/matching/test_eval_scoring.py` verde (22 passed) com o novo
      conjunto.
- [x] Baseline versionada com validade de JSON, claims conferidos, acerto de rótulo, latência p50/p95 e tokens. **Feito (2026-09-27):** rodada real no Groq sobre os 50 casos
      versionados, `--model openai/gpt-oss-120b` (fallback desligado, pinado a um único
      modelo, como o docstring do harness pede), Quota Guard e backoff (F20-12/F20-13)
      respeitados, projeto Compose isolado `-p f20groq`. Resultado: 50/50
      `AI_COMPLETED`, 0 falhas, `inventions = 0` (nenhuma claim proibida), `coverage = 0`
      em todos os casos (achado registrado, não corrigido — não é o objetivo desta
      baseline mudar critério de pontuação nem o matching), latência p50 1.613 ms / p95
      2.580 ms, 74.545 tokens no total (51.541 entrada + 23.004 saída). Acerto de rótulo
      (aderência/sustentação) fica em branco por design — rubrica humana, não
      automática. Evidência completa, inclusive o achado sobre a primeira tentativa sem
      `--model` (fallback silencioso para `qwen/qwen3.8-27b` em ~29% das chamadas,
      descartada) e a correção mínima aplicada a
      `QuotaGuard.next_available_at` (`src/opportunity_radar/platform/ai/quota.py`, um
      quase-esgotamento de janela de minuto chutava 10h de espera em vez de 60s), em
      [`docs/44-roadmap-fase-20/evidencias/baseline-groq-f20-21-2026-09-27.md`](../evidencias/baseline-groq-f20-21-2026-09-27.md).
      JSON/`.md` brutos do harness copiados para o mesmo diretório de evidências (sem
      segredos, conferido). Teste novo
      `tests/backend/test_ai_quota_integration.py::test_next_available_at_guesses_the_minute_boundary_on_a_token_near_miss`;
      41 testes relevantes verdes, `ruff` e `mypy` sem apontamentos.

## Testes

- `tests/backend/matching/test_eval_scoring.py` continua verde; adicionar caso para `--model`.

## Comando de verificação

```bash
docker compose -p f20-21 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/matching/test_eval_scoring.py
docker compose -p f20-21 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-21 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
