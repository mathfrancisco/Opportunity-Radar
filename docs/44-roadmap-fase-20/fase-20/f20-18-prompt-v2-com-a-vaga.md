# CARD F20-18 — Prompt `v2`: vaga e experiências no payload, pt-BR com evidência

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-17, F20-21
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F16-07](../../38-roadmap-ia-e-busca/fase-16/f16-07-vaga-no-payload-e-prompt-v2.md)

## Resultado

Existe `prompts/opportunity_analysis/v2/`, que lê a vaga e as experiências, responde em pt-BR com evidência conferida; vira padrão só se o conjunto de avaliação mostrar que não piora.

## Contexto

A infraestrutura do F16-07 já está no código: `AnalysisRequest.posting` e `profile_history`, `ANALYSIS_SCHEMA_V2 = "analysis-v2"`, `Claim` com evidência, `evidence_sources` e a conferência em `parse_analysis`. O que falta é o artefato de prompt `v2` (só existe `prompts/opportunity_analysis/v1/`) e a comparação. `requires` do adapter liga `posting`/`profile_history` quando o prompt pede.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `prompts/opportunity_analysis/v2/system.md` | instruções em pt-BR |
| Criar | `prompts/opportunity_analysis/v2/user.md.j2` | placeholders incluindo `{{ posting }}` e `{{ profile_history }}` |
| Criar | `prompts/opportunity_analysis/v2/output.schema.json` | gerado por `scripts/export_prompt_schema.py` para `analysis-v2` |
| Criar | `prompts/opportunity_analysis/v2/metadata.yaml` | `schema_version: analysis-v2`, `temperature` |
| Criar | `prompts/opportunity_analysis/v2/examples.json` | 2 exemplos com evidência |
| Criar | `docs/pesquisas/prompt-v2-vs-v1.md` | relatório da comparação |
| Alterar | `tests/backend/matching/test_prompts.py` | carregar `v2` |

## Passos

1. Copiar a pasta `v1` para `v2` e ler `matching/prompts.py` para saber quais chaves `metadata.yaml` aceita (inclusive a que liga `reads_profile_history`).
2. Reescrever `system.md` em pt-BR: papel, regras (não inventar experiência; cada força/risco com trecho literal copiado do bloco `posting` ou `profile`; sem trecho → `evidence` e `source` nulos e o item vai para inferência), formato de saída.
3. Em `user.md.j2`, incluir `{{ posting }}` e `{{ profile_history }}` além dos placeholders do `v1`.
4. Setar `schema_version: analysis-v2` no `metadata.yaml` e regerar `output.schema.json`.
5. Rodar `python scripts/export_prompt_schema.py --check`.
6. Rodar o conjunto de avaliação (F20-21) com `AI_ANALYSIS_PROMPT=v1` e `=v2`; colar a tabela no relatório.
7. Se `v2` não piora nenhum critério, trocar o padrão `ai_analysis_prompt` para `"v2"` em `Settings` e no `.env.example`; senão, manter `v1` e registrar o motivo.

## Não fazer

- Não alterar o `v1` (ele é histórico e baseline).
- Não mudar `parse_analysis`.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] `load_prompt("v2")` carrega sem erro e `--check` passa.
- [ ] Relatório `prompt-v2-vs-v1.md` versionado com a decisão.
- [ ] Claim com trecho inexistente é descartado e contado (comportamento atual de `parse_analysis`).

## Testes

- `tests/backend/matching/test_prompts.py`: `v2` carrega, variáveis `posting` e `profile_history` presentes, schema bate com `OUTPUT_SCHEMAS["analysis-v2"]`.
- `tests/backend/matching/test_groq_adapter.py`: com `v2`, `requires` contém `posting` e `profile_history`.

## Comando de verificação

```bash
docker compose -p f20-18 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/matching/test_prompts.py tests/backend/matching/test_groq_adapter.py
docker compose -p f20-18 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-18 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
