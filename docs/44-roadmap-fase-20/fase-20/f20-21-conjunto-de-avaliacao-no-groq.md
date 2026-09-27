# CARD F20-21 — Conjunto de avaliação completo e baseline no Groq

- **Status:** Backlog
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
| Criar | `docs/pesquisas/eval-analysis-groq-baseline.md` | baseline |

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

- [ ] 50 casos rotulados versionados. **Parcial (2026-09-27):** os 41 casos reais foram
      revisados (`docs/44-roadmap-fase-20/rotulagem/f20-21-eval-cases.md`, todas as linhas
      `aceito`); os 6 casos do bucket `backend` marcados **Reclassificar** foram renomeados
      para `fora_de_area` (`01/02/03/04/06/08-fora_de_area-*`) com o risco de área
      adicionado a `must_mention_risks`; os 2 (`05`, `07`) marcados **Aceitar** ficaram como
      `backend`. `prompts/opportunity_analysis/eval/cases/` (50 arquivos, `git ls-files`
      confirma que não está mais ignorado) ainda não foi commitado nesta sessão — ver
      handback. Lacuna de composição (0 Java, 3 fullstack, 1 IA) fechada com 26 candidatos
      reais do acervo (10 Java, 7 fullstack, 9 IA, todos `role_family=SOFTWARE_ENGINEERING`,
      `work_mode=REMOTE`, com `match_assessment` real), exportados com a mesma
      anonimização de `export_eval_cases.py` para
      `prompts/opportunity_analysis/eval/drafts/gap-{java,fullstack,ai}-NN-review_required.json`
      — são recomendações, não casos: `must_mention_risks`/`must_not_claim` ficam vazios
      até um humano ler a vaga e decidir, como todo draft.
- [ ] Baseline versionada com validade de JSON, claims conferidos, acerto de rótulo, latência p50/p95 e tokens. **Não feito** — sem chamada real ao Groq nesta sessão (fora do escopo/orçamento), como o "Não fazer" exige.

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
