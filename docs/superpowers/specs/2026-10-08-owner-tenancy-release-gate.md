# Owner tenancy release gate for migration 0069

Migration `20261008_0069` adds mandatory `owner_sub` values to personal-data tables.
The application version before Package 3 does not scope those reads and writes by the
authenticated subject. Therefore, do not run migration 0069 against a database that an
older API image can reach, and do not deploy or cut over that database before Package 3
has passed its owner-isolation tests and independent review.

The existing `.github/workflows/pipeline.yml` image-publication job runs
`scripts/check_tenancy_release_gate.py` before publishing any image. It fails closed while
the repository Actions variable `TENANCY_OWNER_API_READY` is absent or not exactly `true`.
Set that variable only after Package 3 is integrated, the two-user authorization tests
pass, and the independent review accepts the evidence. The check blocks GHCR publication
through this workflow; it cannot technically stop a manual deployment or another pipeline
from using an older image. Any such path must remain operationally prohibited until the
same evidence exists.

Compose forwards `OWNER_SUB_BACKFILL` only to the one-shot `migrate` service. It has an
empty default, so Alembic 0069 fails closed when no explicit backfill subject is configured.
Use a private local env file or secret manager at the time of an authorized isolated
migration; do not put a real identity in this document, a checked-in example, logs, or an
image. The presence of this setting does not authorize a production migration.
