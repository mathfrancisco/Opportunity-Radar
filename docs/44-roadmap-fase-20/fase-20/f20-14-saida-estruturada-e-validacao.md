# CARD F20-14 — Saída estruturada: JSON Schema estrito e validação

- **Status:** Feito — `strict_compatible` e `make_validator` em `platform/ai/schema.py`; `tests/backend/platform/ai/test_schema.py` (11 testes) e o comando de verificação abaixo passam (75 testes, `ruff check .`, `mypy` limpos); `export_prompt_schema.py --check` confirma que `OUTPUT_SCHEMAS` já era estrito-compatível (não precisou de mudança em `analysis.py`, que continua com `additionalProperties: false` e todos os campos em `required`).
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-07
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §4.2, §8.1

## Resultado

O schema de saída vai no `response_format` em modo estrito, e toda resposta passa por `parse_analysis` antes de ser usada; resposta inválida nunca é gravada.

## Contexto

`matching/analysis.py` já tem `OUTPUT_SCHEMAS` (`analysis-v1` e `analysis-v2`) e `parse_analysis` (linha 335), que valida o JSON e confere as evidências de `analysis-v2`. `scripts/export_prompt_schema.py --check` roda no CI e garante que `prompts/opportunity_analysis/<v>/output.schema.json` bate com o código. Os três modelos Groq aceitam `strict: true`; em modo estrito o schema precisa de `additionalProperties: false` e todos os campos em `required`.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/matching/analysis.py` | garantir que `OUTPUT_SCHEMAS` é aceito em modo estrito |
| Alterar | `prompts/opportunity_analysis/v1/output.schema.json` | regerar com `scripts/export_prompt_schema.py` |
| Criar | `src/opportunity_radar/platform/ai/schema.py` | `strict_compatible`, `make_validator` |
| Criar | `tests/backend/platform/ai/test_schema.py` | testes |

## Interfaces

```python
# platform/ai/schema.py
def strict_compatible(schema: Mapping[str, Any]) -> list[str]:
    """Lista de problemas para strict mode: objeto sem additionalProperties:false,
    propriedade fora de required. Lista vazia = compatível."""

def make_validator(parse: Callable[[Any], object]) -> Callable[[str], None]:
    """Devolve função que faz json.loads + parse; qualquer erro vira
    ProviderError(INVALID_OUTPUT, <mensagem curta>). Usada pelo router (F20-10)."""
```

## Passos

1. Implementar `strict_compatible` percorrendo o schema recursivamente (inclui `items` e `$defs`).
2. Rodar `strict_compatible` para cada entrada de `OUTPUT_SCHEMAS`; corrigir o schema no código até a lista ficar vazia (campos opcionais viram `"type": ["string", "null"]` e continuam em `required`).
3. Conferir que `parse_analysis` continua aceitando `null` nos campos que passaram a ser anuláveis.
4. Rodar `python scripts/export_prompt_schema.py` para regerar o artefato e depois `--check`.
5. Implementar `make_validator`. O adapter (F20-17) passa `make_validator(lambda obj: parse_analysis(obj, ...))` ao router.
6. Adicionar ao `pipeline.yml`, no job de lint, um passo `python -c` ou teste que falha se `strict_compatible` achar problema (ou cobrir via teste unitário, que já roda no CI).

## Não fazer

- Não trocar `parse_analysis` por Pydantic: ele já valida e confere evidências; duplicar criaria duas verdades.
- Não mudar `ANALYSIS_SCHEMA_VERSION` se o conteúdo aceito não mudou.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] `strict_compatible(OUTPUT_SCHEMAS[v]) == []` para todas as versões.
- [x] `scripts/export_prompt_schema.py --check` passa.
- [x] Resposta fora do schema vira `INVALID_OUTPUT` e nunca é persistida.

## Testes

- `tests/backend/platform/ai/test_schema.py`: schema compatível, objeto sem `additionalProperties`, campo fora de `required`, `make_validator` com JSON quebrado, campo faltando, tipo errado.
- `tests/backend/matching/test_analysis.py`: `parse_analysis` com campos `null`.

## Comando de verificação

```bash
docker compose -p f20-14 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_schema.py tests/backend/matching/test_analysis.py tests/backend/matching/test_prompts.py
docker compose -p f20-14 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-14 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
