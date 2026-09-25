# CARD F20-23 — Classificação e extração assistidas para campos ambíguos

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-22, F20-02, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §6, §6.1

## Resultado

Quando a regra deixa área, senioridade ou modo de trabalho como desconhecido, o modelo `fast` sugere um valor com trecho de evidência; a sugestão fica separada e só vale após confirmação do operador.

## Contexto

`role-family-v1` (`opportunities/role_family.py`), `seniority-v2` e `regions-v1` decidem a maioria dos casos e gravam evidência. Não existe tabela de sugestões. O F18-06 (agora F20-24) exige que sugestão fique separada do valor canônico.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `migrations/versions/20260926_0032_field_suggestion.py` | tabela `opportunities.field_suggestion` |
| Criar | `src/opportunity_radar/opportunities/suggestions.py` | gatilho, chamada, gravação, confirmação |
| Criar | `prompts/job_classification/v1/` | system, user, schema, metadata |
| Alterar | `src/opportunity_radar/worker.py` | job `suggest-fields` (desligado por padrão) |
| Alterar | `src/opportunity_radar/platform/config.py` | `worker_suggest_enabled: bool = False`, `worker_suggest_batch_size: int = 20` |
| Alterar | `src/opportunity_radar/presentation/http/opportunities.py` | `GET` sugestões, `POST` aceitar/rejeitar |
| Criar | `tests/backend/opportunities/test_suggestions.py` | testes |

## Interfaces

```python
-- opportunities.field_suggestion
id uuid pk; opportunity_id uuid fk; opportunity_version int; field varchar(32)
  -- 'role_family' | 'seniority' | 'work_mode'
value varchar(64); evidence text; model varchar(128); prompt_version varchar(32)
status varchar(16)  -- 'PENDING' | 'ACCEPTED' | 'REJECTED'
decided_at timestamptz null; created_at timestamptz
unique (opportunity_id, opportunity_version, field)

# saída do modelo (schema estrito)
{"role_family": {"value": "backend" | ... | null, "evidence": "<trecho literal>" | null},
 "seniority":   {"value": "junior" | "mid" | "senior" | null, "evidence": ... },
 "work_mode":   {"value": "remote" | "hybrid" | "onsite" | null, "evidence": ... }}
```

## Passos

1. Gatilho: selecionar oportunidades cujo campo canônico é desconhecido **depois** das regras e sem sugestão para a versão atual.
2. Enviar só os campos desconhecidos + título + descrição limpa (Token Guard da tarefa `job_classification`).
3. Descartar sugestão cujo `evidence` não aparece literalmente no texto enviado.
4. Aceitar grava o valor canônico com `source=llm_confirmed` e evidência; rejeitar só muda o status.
5. Filtros da Inbox continuam lendo só o valor canônico.
6. Ligar o job apenas depois de medir a precisão num conjunto de 30 vagas ambíguas rotuladas; registrar em `docs/pesquisas/sugestoes-f20-23.md`.

## Não fazer

- Não gravar sugestão no campo canônico sem confirmação.
- Não chamar o modelo para campo já resolvido pela regra.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Nenhuma chamada para campo resolvido por regra.
- [ ] Sugestão sem trecho literal é descartada.
- [ ] Precisão medida registrada antes de ligar por padrão.

## Testes

- `tests/backend/opportunities/test_suggestions.py`: gatilho só `unknown`, descarte sem evidência, aceitar/rejeitar, idempotência por versão.

## Comando de verificação

```bash
docker compose -p f20-23 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/opportunities/test_suggestions.py
docker compose -p f20-23 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-23 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
