# HTTP tenancy A/B — 2026-10-09

## Scope

- The protected production `create_app` factory is exercised with fixture-generated
  RS256 JWTs and an offline JWKS transport.  Authentication is not bypassed; only
  `get_session` is replaced with sessions for the isolated test database.
- Two synthetic identities prove that a foreign saved search cannot be listed,
  patched, deleted, or have its new-count read.  The owner still sees the original
  saved search.
- A foreign profile version is rejected for publish, activate, application creation,
  and match evaluation.  A foreign application cannot be listed, read, transitioned,
  or have its next action changed; its history and follow-up remain behind that
  application boundary.
- A member overview omits operational source fields and has no other identity's
  active application; the configured owner receives the operational overview while
  still receiving only that owner's application count.
- A foreign match is absent from the list and returns HTTP 404 by ID.  A member is
  forbidden from executing a source.  Missing and malformed bearer credentials fail
  closed with HTTP 401.

## Isolated validation

The project and environment below use the pre-existing `f53_recovery_test` database.
The obsolete currency snapshot override was intentionally not mounted.

```text
rtk docker compose -p f53-recovery-20261008 --env-file .tmp\f53-recovery-20261008.env -f compose.yaml -f compose.dev.yaml run --rm --no-deps -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 api pytest -q tests/backend/http/test_auth_tenancy_integration.py
.......                                                                  [100%]
7 passed, 3 warnings in 6.53s

rtk docker compose -p f53-recovery-20261008 --env-file .tmp\f53-recovery-20261008.env -f compose.yaml -f compose.dev.yaml run --rm --no-deps -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 api pytest -q tests/backend/migrations/test_owner_sub_tenancy.py
..                                                                       [100%]
2 passed, 1 warning in 20.32s

rtk proxy .\.venv\Scripts\python.exe -m ruff check tests\backend\http\test_auth_tenancy_integration.py
All checks passed!

rtk git diff --check
exit 0
```

The migration tests exercise revision 0069's explicit backfill of pre-existing rows,
null-owner audit, ownership invariants, and downgrade refusal before any schema change.
Warnings are the existing Starlette/httpx deprecations and pytest cache permissions
inside the disposable API container.
