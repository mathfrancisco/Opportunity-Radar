# F53-06 e F53-12 — projeção offline de orçamento Neon

Data: 2026-10-14

Estado: projeção local implementada; consumo real, evidência de storage,
compatibilidade e comportamento ocioso continuam pendentes. Nenhum critério de
aceite externo é marcado como cumprido aqui.

## Escopo

`scripts/project_neon_budget.py` (somente stdlib, sem rede, banco, subprocess
ou leitura de ambiente) e `tests/backend/test_neon_budget_projection.py`.
Limites: compute `<= 80` CU-h; storage `< 1 000 000 000` bytes. O runbook com
flags, unidades, suposições e códigos de saída está em
[`variaveis-e-runbooks.md`](../variaveis-e-runbooks.md).

## Saída executada (worktree `f53-neon-projection`)

```text
$ python scripts/project_neon_budget.py --active-hours-per-run 2 --runs-per-month 31 --cu 0.25
{
  "inputs": {
    "active_hours_per_run": "2",
    "runs_per_month": 31,
    "cu": "0.25",
    "additional_cu_hours": "0",
    "current_storage_bytes": null,
    "monthly_growth_bytes": null
  },
  "scheduled_cu_hours": "15.50",
  "additional_cu_hours": "0",
  "total_cu_hours": "15.50",
  "compute_limit_cu_hours": "80",
  "compute_status": "pass",
  "storage_projected_bytes": null,
  "storage_limit_bytes": 1000000000,
  "storage_status": "not_projected",
  "has_budget_breach": false
}
exit=0
$ python scripts/project_neon_budget.py --active-hours-per-run 24 --runs-per-month 31 --cu 0.25
{
  "inputs": {
    "active_hours_per_run": "24",
    "runs_per_month": 31,
    "cu": "0.25",
    "additional_cu_hours": "0",
    "current_storage_bytes": null,
    "monthly_growth_bytes": null
  },
  "scheduled_cu_hours": "186.00",
  "additional_cu_hours": "0",
  "total_cu_hours": "186.00",
  "compute_limit_cu_hours": "80",
  "compute_status": "fail",
  "storage_projected_bytes": null,
  "storage_limit_bytes": 1000000000,
  "storage_status": "not_projected",
  "has_budget_breach": true
}
exit=1
```

O horizonte de 744 h (0,25 CU × 24 h × 31 dias = 186 CU-h) excede 80 CU-h e
retorna exit 1, como mostra a segunda execução.

## Validação

Executada em contêiner `python:3.12-slim` com `requirements-dev.txt`:

```text
All checks passed!
Success: no issues found in 143 source files
46 passed in 0.82s
```

(`ruff check .`, `mypy` e `pytest tests/backend/test_neon_budget_projection.py`,
nesta ordem.) Mutação `<=` → `<` na comparação de compute: 3 testes falharam
(`test_tc03_exactly_at_limit_passes`, `test_tc03_cli_exit_0`,
`test_tc05_additional_at_limit_passes`); mutação revertida.

## Pendente

- Consumo real em Neon (nenhuma medição foi feita).
- Evidência de storage real (bytes lidos do painel Neon).
- Compatibilidade (`vector`/`unaccent`, PG 17, Alembic, restore) contra Neon real.
- Comportamento ocioso (conexões a zero, `pool_pre_ping` sem manter o banco acordado) na VM.
