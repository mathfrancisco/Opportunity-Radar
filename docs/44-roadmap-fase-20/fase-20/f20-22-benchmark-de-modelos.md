# CARD F20-22 — Benchmark 120B × 20B × Qwen e escolha por tarefa

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-21
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §4; [F16-12](../../38-roadmap-ia-e-busca/fase-16/f16-12-confirmacao-de-modelo-e-quantizacao.md)

## Resultado

A escolha de modelo e `reasoning_effort` para `job_match` é decidida por medição e registrada.

## Contexto

Com o harness do F20-21 e a flag `--model`, comparar variantes é rodar o mesmo conjunto várias vezes. Cada rodada gasta quota do modelo testado.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `docs/pesquisas/benchmark-modelos-groq.md` | critério, resultados, decisão |
| Alterar | `docs/43-spec-llm-cloud-e-consolidacao.md` | §6 com a rota decidida, se mudar |

## Passos

1. Escrever no relatório, **antes** de rodar, o critério de decisão (ex.: escolher o menor modelo que fica a até 2 pontos percentuais do melhor em acerto de rótulo e com JSON válido ≥ 98 %).
2. Rodar o conjunto com `--model openai/gpt-oss-120b`, `--model openai/gpt-oss-20b`, `--model qwen/qwen3.8-27b`, cada um com `AI_REASONING_EFFORT=low` e `=medium` (6 rodadas, em dias diferentes se a quota exigir).
3. Tabela: acerto de rótulo, JSON válido, claims conferidos, latência p50/p95, tokens médios de entrada/saída.
4. Aplicar o critério e registrar a decisão.
5. Se a rota padrão mudar, atualizar `default_routes` (F20-09), os padrões de `Settings` e a SPEC §6.

## Não fazer

- Não mudar o critério depois de ver os números.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Relatório com 6 variantes e a decisão aplicada ao código ou justificativa para manter.

## Testes

- Se a rota mudar: `tests/backend/platform/ai/test_router.py` atualizado para os novos padrões.

## Comando de verificação

```bash
docker compose -p f20-22 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_router.py
docker compose -p f20-22 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-22 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
