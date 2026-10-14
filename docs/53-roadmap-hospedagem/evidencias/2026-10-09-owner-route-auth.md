# Owner identity in operational routes — 2026-10-09

## Scope

- `POST /sources/{source_id}/runs` passes the subject of the JWT already validated by
  the private router to `active_profile_target_role_families`.
- `GET /funnel-metrics` uses that same subject to read the active profile.
- Neither endpoint accepts an owner subject from a request body or query parameter.

## Focused validation

```text
rtk docker compose -p f53-recovery-20261008 --env-file .tmp\f53-recovery-20261008.env -f compose.yaml -f compose.dev.yaml -f .tmp\f53-recovery-20261008.override.yaml run --rm --no-deps -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 api pytest -q tests/backend/http/test_auth.py
........................                                                 [100%]
24 passed, 3 warnings in 5.82s
```

The two new parameterized HTTP regressions use `create_app` (the protected production
factory) and fixture-generated RS256 JWT/JWKS data.  They configure distinct synthetic
owner subjects and assert each handler forwards that authenticated subject, while the
route returns 201 or 200 instead of 500.  Database access is replaced only at the
`get_session` dependency because these tests prove identity propagation rather than
persistence; no authentication dependency is bypassed.

```text
rtk .\.venv\Scripts\python.exe -m ruff check src\opportunity_radar\presentation\http\acquisition.py src\opportunity_radar\presentation\http\dashboard.py tests\backend\http\test_auth.py
All checks passed!

rtk git diff --check
exit 0
```
