# CARD F20-02 — Curadoria manual de `skills-v2`

- **Status:** Parcial — feito na máquina de referência em 2026-09-26.
  `scripts/unmatched_skill_terms.py` rodado contra o acervo real (648 oportunidades, 630
  descrições), saída e decisão por termo em `docs/pesquisas/curadoria-skills-v2.md`. Três
  entradas novas na `SKILL_TAXONOMY` (`ai`, `cicd`, `observability`) com testes de
  regressão usando texto real. Cobertura de skills medida
  (48,46% → 90,74% das oportunidades com ≥1 skill), mas **não** pelo reprocessamento
  oficial do acervo — bump de `NORMALIZER_VERSION` fica fora da lista de arquivos deste
  card e dispararia reanálise de matching, que o card proíbe alterar. F17-06 segue "Em
  revisão", não `Done` — ver limitação no relatório de curadoria.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** A — Fechamento do que está em revisão
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-06](../../38-roadmap-ia-e-busca/fase-17/f17-06-normalizacao-mais-precisa.md)

## Resultado

As lacunas de skill encontradas por `scripts/unmatched_skill_terms.py` viram entradas revisadas de `skills-v2`, com aliases e desambiguação, e o F17-06 fecha.

## Contexto

O F17-06 entregou `seniority-v2`, `regions-v1`, reprocessamento e o script de lacunas (`c599c09`, `1f02ba3`, `23ca1de`). Falta a curadoria manual. O teste `tests/backend/test_unmatched_skill_terms.py` cobre o script.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `arquivo da taxonomia `skills-v2` (localizar com `grep -rn "skills-v2" src`)` | entradas novas e aliases |
| Criar | `docs/pesquisas/curadoria-skills-v2.md` | saída do script e decisão por termo |
| Alterar | `tests/backend/opportunities/ (arquivo de teste da taxonomia existente)` | casos de regressão |

## Passos

1. Rodar `python scripts/unmatched_skill_terms.py` no acervo real e salvar a saída em `curadoria-skills-v2.md`.
2. Para cada termo, decidir e anotar: `nova skill`, `alias de <skill>`, `ambíguo` (com a regra) ou `descartado`.
3. Aplicar as decisões na taxonomia e subir a versão (ex.: `skills-v2` → `skills-v3`) se o formato do projeto exigir versão nova por mudança.
4. Para cada entrada nova ou alias, adicionar um caso de teste com um texto real de vaga.
5. Rodar o reprocessamento retomável do F17-06 e anotar antes/depois da cobertura de skills no documento.
6. Marcar o F17-06 como `Done`.

## Não fazer

- Não mudar a regra de senioridade nem de regiões neste card.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Toda entrada nova tem teste de regressão.
- [ ] O reprocessamento não regride evidência existente. Não verificável ainda: o
      reprocessamento oficial (bump de `NORMALIZER_VERSION`) não foi executado nesta
      sessão — ver limitação em `docs/pesquisas/curadoria-skills-v2.md`.
- [ ] F17-06 marcado como Done com link para `curadoria-skills-v2.md`. F17-06 segue "Em
      revisão": a curadoria da taxonomia está feita, mas fechar o card exige o
      reprocessamento oficial do acervo, que fica fora do escopo de arquivos deste card.

## Testes

- Um caso por alias e por regra de desambiguação no arquivo de teste da taxonomia.

## Comando de verificação

```bash
docker compose -p f20-02 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/opportunities tests/backend/test_unmatched_skill_terms.py
docker compose -p f20-02 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-02 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
