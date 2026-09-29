# CARD F48-06 — Funil e north-star no `doctor` (§1, §2)

- **Status:** Implementado (2026-09-29).
- **Spec:** [`../48-spec-mais-vagas.md`](../48-spec-mais-vagas.md) §1, §2, §5.

## Resultado

- `src/opportunity_radar/dashboard/funnel.py` (`funnel_report`): as etapas do §2.1
  (fontes habilitadas, com execução agendada, `raw_item`, normalizados, oportunidades,
  abertas, sem repetir empresa+título, filtro padrão, avaliadas, veredito útil, análise de IA
  concluída), cada uma com a perda contra a etapa que estreita.
- North-star: estoque útil visível e novas em 24 h, com a pilha cumulativa (abertas,
  recência, não `INELIGIBLE`, país `BR`/desconhecido/`ANY`, área, uma por empresa+título).
  Sem `target_role_families` no perfil ativo usa o proxy técnico `SOFTWARE_ENGINEERING, DATA,
  INFRASTRUCTURE, SECURITY`; com áreas, usa as do perfil.
- Guardas do §1.2 computáveis do banco: fontes no prazo (2x cadência), `FAILED` na
  normalização / itens, repetição na lista padrão, `UNKNOWN` de senioridade, modo de trabalho
  e país, vereditos úteis / avaliadas, `AI_FAILED` por quota / tentativas, hosts proibidos
  tocados. Não computáveis (`not_measured`): fontes avaliadas por passada e falsos
  fechamentos.
- `scripts/doctor.py`: check `funnel` (uma linha por etapa, north-star e guarda); `WARN` se
  houver referência a host proibido.
- `GET /funnel-metrics` (dashboard) devolve o mesmo relatório.

## Contexto

O doc 48 mediu o funil à mão por `SELECT`. Sem o relatório no `doctor`, a linha de base de
"vagas úteis novas por dia" e as guardas do §1.2 não têm como ser repetidas antes e depois
das mudanças de ranking.

## Escopo

`dashboard/funnel.py` (novo; `metrics.py` importa `queries.py` de volta, então um módulo
próprio evita o ciclo), `scripts/doctor.py`, `presentation/http/dashboard.py`.

## Critérios de aceite

- [x] Saída com as etapas do §2 e com a north-star (estoque útil e novas/24 h) usando o
  proxy técnico enquanto o perfil não tiver áreas
  (`tests/backend/dashboard/test_funnel.py`, contagens exatas por diferença de relatórios
  numa transação semeada e descartada; `tests/backend/test_doctor_funnel.py`).
- [x] Guardas do §1.2 no mesmo relatório (as duas não computáveis vêm marcadas em
  `not_measured`, não como zero).

## Verificação

```
docker compose -p f48w3 -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q
1210 passed, 11 skipped (suíte completa; ver card F48-07)
ruff check src scripts tests/backend -> All checks passed
```
