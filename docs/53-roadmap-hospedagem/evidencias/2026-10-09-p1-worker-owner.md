# P1 worker operational-owner validation — 2026-10-09

Scope validated: worker collection, suggestion selection, acquisition host passes, and soak
bootstrap use an explicit operational owner. The isolated Compose database/network used the
existing `f53-recovery-20261008` resources. The historical override containing a
`currency-head` bind mount was not used for these commands.

The temporary `.tmp/worker-owner-test.env` file was removed by its exact, authorized path.

## Commands and literal results

```text
docker run --rm --network f53-recovery-20261008_app_net --env-file .tmp\f53-recovery-20261008.env -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 -v "${PWD}:/app" -w /app f53-recovery-20261008-api:latest pytest -q tests/backend/test_worker.py
...............................                                          [100%]
31 passed in 4.06s
```

```text
docker run --rm --network f53-recovery-20261008_app_net --env-file .tmp\f53-recovery-20261008.env -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 -v "${PWD}:/app" -w /app f53-recovery-20261008-api:latest pytest -q tests/backend/opportunities/test_suggestions.py
............................................                             [100%]
44 passed in 9.16s
```

```text
docker run --rm --network f53-recovery-20261008_app_net --env-file .tmp\f53-recovery-20261008.env -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 -v "${PWD}:/app" -w /app f53-recovery-20261008-api:latest pytest -q tests/backend/acquisition/test_collectable_sources.py
..                                                                       [100%]
2 passed in 9.56s
```

```text
docker run --rm --network f53-recovery-20261008_app_net --env-file .tmp\f53-recovery-20261008.env -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 -v "${PWD}:/app" -w /app f53-recovery-20261008-api:latest pytest -q tests/backend/acquisition/test_collection_host_concurrency.py tests/backend/acquisition/test_collection_job.py tests/backend/acquisition/test_concurrent_pass_database.py
..............ssssssss..                                                 [100%]
16 passed, 8 skipped in 7.26s
```

```text
docker run -d --name f53-p1-soak-validation --network f53-recovery-20261008_app_net --env-file .tmp\f53-recovery-20261008.env -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 -v "${PWD}:/app" -w /app f53-recovery-20261008-api:latest pytest -q tests/backend/operations/test_soak.py
docker inspect -f "{{.State.Status}} {{.State.ExitCode}} {{.State.Error}}" f53-p1-soak-validation
exited 0
docker logs f53-p1-soak-validation --tail 100
..                                                                       [100%]
2 passed in 60.08s (0:01:00)
docker rm f53-p1-soak-validation
f53-p1-soak-validation
```

```text
rtk proxy .\.venv\Scripts\python.exe -m ruff check src\opportunity_radar\acquisition\service.py src\opportunity_radar\matching\currency.py src\opportunity_radar\operations\soak.py src\opportunity_radar\opportunities\suggestions.py src\opportunity_radar\worker.py tests\backend\acquisition\test_collectable_sources.py tests\backend\acquisition\test_collection_host_concurrency.py tests\backend\acquisition\test_collection_job.py tests\backend\acquisition\test_concurrent_pass_database.py tests\backend\operations\test_soak.py tests\backend\opportunities\test_suggestions.py tests\backend\test_worker.py
All checks passed!
```

```text
rtk git diff --check
exit 0; no output
```
