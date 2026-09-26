# CARD F20-15 — PII sanitizer e perfil mínimo

- **Status:** Parcial — `sanitize_for_llm` e `PII_KEYS` implementados em `platform/ai/sanitizer.py`, com `tests/backend/platform/ai/test_sanitizer.py` (16 testes) cobrindo cada padrão, chave aninhada em lista, imutabilidade do original e preservação de evidência profissional; runbook atualizado ("Dados enviados ao Groq"). Falta o primeiro critério de aceite: ele exige o adapter Groq do F20-17 (ainda não existe nesta base) chamando `sanitize_for_llm` sobre o payload real antes do `MockTransport` capturar o corpo HTTP. Este card entrega a função pronta para esse adapter usar; o card só pode ir para "Feito" depois que F20-17 existir e o teste de integração passar.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-07, F20-40
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §8.3

## Resultado

Nenhum dado pessoal ou segredo chega ao corpo HTTP enviado ao Groq; o modelo recebe só o perfil profissional mínimo.

## Contexto

`AnalysisRequest` leva `profile_snapshot` e `profile_history` ("sem dados de contato", segundo o comentário em `matching/analysis.py`). Não existe verificação automática disso. O perfil vive no contexto `profile/`.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/platform/ai/sanitizer.py` | `sanitize_for_llm`, `PII_KEYS`, padrões |
| Criar | `tests/backend/platform/ai/test_sanitizer.py` | testes unitários |
| Alterar | `docs/30-runbook.md` | seção "Dados enviados ao Groq" |

## Interfaces

```python
# platform/ai/sanitizer.py
PII_KEYS = frozenset({"name", "full_name", "email", "phone", "address", "cpf",
                      "document", "linkedin_url", "github_url", "website", "birth_date"})

def sanitize_for_llm(value: Any) -> Any:
    """Recursivo sobre dict/list/str. Remove chaves de PII_KEYS; em strings troca:
    e-mail -> [email], telefone BR/intl -> [telefone], CPF -> [documento],
    URL de linkedin.com/github.com -> [url-pessoal], padrões de chave
    (gsk_..., sk-..., tvly-..., 'Bearer ...') -> [segredo]. Não altera o original."""
```

## Passos

1. Implementar `sanitize_for_llm` com regex compiladas no módulo.
2. Padrões mínimos: e-mail `[\w.+-]+@[\w-]+\.[\w.]+`; CPF `\d{3}\.?\d{3}\.?\d{3}-?\d{2}`; telefone `(\+?\d{2}\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}`; chaves `gsk_[A-Za-z0-9]{20,}`, `sk-[A-Za-z0-9]{20,}`, `tvly-[A-Za-z0-9]{20,}`, `Bearer\s+\S+`.
3. O adapter Groq (F20-17) aplica `sanitize_for_llm` ao payload inteiro **antes** de renderizar o prompt e antes de calcular `payload_hash`.
4. Garantir que evidência profissional (cargo, skills, descrição de projeto) passa intacta.
5. Escrever no runbook: o que é enviado, o que é removido, e que o Free Plan pode reter dados; a IA só liga com `AI_ENABLED=true`.

## Não fazer

- Não remover o texto da vaga: ele é público e é o objeto da análise (mas e-mails e telefones dentro dela também são mascarados).
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Com um perfil de teste cheio de PII, nenhum desses valores aparece no corpo HTTP capturado pelo `MockTransport` (teste no F20-17 — card ainda não implementado nesta base; `sanitize_for_llm` está pronta para o adapter chamar).
- [x] Skills, cargos e evidências continuam no payload (`test_pii_key_nested_in_a_list_is_removed`, `test_professional_evidence_is_preserved`).

## Testes

- `tests/backend/platform/ai/test_sanitizer.py`: um teste por padrão, chave de PII aninhada em lista, original não modificado, evidência preservada.

## Comando de verificação

```bash
docker compose -p f20-15 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_sanitizer.py
docker compose -p f20-15 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-15 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
