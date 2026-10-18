# Saved-search SQL benchmark — 2026-10-18

Executed from the worktree with the existing API image and an ephemeral PostgreSQL
database named `opportunity_radar_test`. The environment set
`RUN_DATABASE_INTEGRATION=1` and `DATABASE_INTEGRATION_ISOLATED=1`; no operational
database was used.

Provenance: measured from the dirty R56 worktree based on `abd3fbe05f7ed0e382407d51323cfdf3f10d4981`, using the mounted current script and source tree.

Reproduce:

```powershell
docker run --rm --network r56-sql-verify-net -v ${PWD}:/app -w /app `
  -e DATABASE_URL=<isolated *_test URL> `
  -e RUN_DATABASE_INTEGRATION=1 -e DATABASE_INTEGRATION_ISOLATED=1 `
  r56-sql-batch-static-api python scripts/benchmark_saved_search_summaries.py
```

The script creates 1,000 synthetic `DATA` vacancies for one synthetic company. It
compares the legacy per-search read with `list_saved_search_summaries`, asserts equal
counts, and counts executed SQL statements. It also measures profile fallback after
scoping it to that same synthetic company.

| Scenario | Searches | Legacy SQL | Summary SQL | Legacy s | Summary s | Count/search |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `all_areas` | 0 | 1 | 1 | 0.006469 | 0.001170 | 0 |
| `all_areas` | 1 | 2 | 2 | 0.090146 | 0.034459 | 1000 |
| `all_areas` | 20 | 21 | 2 | 0.563383 | 0.059544 | 1000 |
| active-profile fallback | 1 | n/a | 4 | n/a | 0.047866 | 1000 |
| active-profile fallback | 20 | n/a | 4 | n/a | 0.063347 | 1000 |
| varied term/area/seniority/cutoff | 20 | 21 | 2 | 0.713900 | 0.092617 | mixed |

The wall-clock values are one local run, not a performance threshold. The stable
acceptance result is the statement budget: `all_areas` is `1/2/2` for `0/1/20`
searches, and profile fallback remains four statements from one to twenty searches.
The varied set has five existing terms, fifteen absent terms, explicit `DATA` area on
seven searches, seniority on ten, and a `last_opened_at` cutoff on four.
