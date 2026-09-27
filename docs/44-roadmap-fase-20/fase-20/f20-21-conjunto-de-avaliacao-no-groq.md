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
