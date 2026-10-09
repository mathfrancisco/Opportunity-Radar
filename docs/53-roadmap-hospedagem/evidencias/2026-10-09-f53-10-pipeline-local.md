# F53-10 — runner finito local

Data: 2026-10-09

Escopo local executado: núcleo de uma janela única em
`src/opportunity_radar/platform/pipeline.py` e CLI
`scripts/run_pipeline_once.py`. Não houve timer, deploy, credencial, conexão
externa, execução de banco, criação de recurso ou uso de dado real.

Contrato implementado:

- owner operacional explícito e não vazio é recusado antes de relógio, claim,
  sessão ou observação de job;
- ordem única e fixa: `collect_enabled_sources`,
  `normalize_opportunities`, `evaluate_pending`;
- deadline é monotônico; claim é advisory lock PostgreSQL por conexão;
- SIGINT/SIGTERM impede novos estágios; relatório estruturado não inclui
  mensagens de exceções e contém `correlation_id`, duração total e duração e
  contagens reais de cada estágio;
- `--dry-run` só descreve a janela, sem engine, banco, rede ou claim;
- análise e retenção aparecem bloqueadas, não são chamadas;
- não há retry ou loop residente. A coleta reutiliza o deadline de pass e as
  claims/fencing existentes; o card F53-11 continua necessário para um timer
  externo e sua observação.

Validação executada:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m pytest -q tests\backend\test_pipeline_runner.py tests\backend\test_worker.py tests\backend\test_worker_evaluate_batch_size.py
```

Saída literal:

```text
42 passed, 1 skipped in 1.73s
```

O único skip é a prova
de disputa real do advisory lock: ela é coletada apenas quando
`RUN_DATABASE_INTEGRATION=1`, `DATABASE_INTEGRATION_ISOLATED=1` e um
`DATABASE_URL` terminado em `_test` já estiverem presentes. Nesta execução
local esses guards não estavam habilitados; portanto essa prova de PostgreSQL
não foi alegada como executada.

Também executados:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m ruff check src\opportunity_radar\platform\pipeline.py scripts\run_pipeline_once.py tests\backend\test_pipeline_runner.py
rtk git diff --check
```

Resultado literal de Ruff: `All checks passed!`.

Limite de evidência: esta é uma prova unitária offline do orquestrador e dos
contratos imediatos do worker. A retomada com uma coleta real, disputa de
claim PostgreSQL em banco isolado e medições de conexões ainda exigem execução
de integração com os três guards de banco `_test`; não foram inferidos por
esta execução.
