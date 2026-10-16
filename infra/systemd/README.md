# Systemd Pipeline Contract

These files define a manual systemd installation for one finite Opportunity
Radar pipeline window. They are versioned artifacts only. Nothing is installed
or enabled by this repository.

## Timing Contract

R55-E5: the timer fires hourly (`OnCalendar=hourly UTC`, 24 windows per day) with a short
15-minute window. Windows never overlap: a oneshot unit cannot start while active, and the
pipeline `PostgresWindowClaim` advisory lock makes a second runner exit with `CLAIM_BUSY`.

| Value | Setting | Meaning |
| --- | --- | --- |
| 900 seconds | `DEFAULT_WINDOW_SECONDS` | Runner deadline passed as `--deadline-seconds` |
| 960 seconds | `TimeoutStartSec` | Maximum service start time |
| 120 seconds | `RandomizedDelaySec` | Schedule jitter |
| 3,480 seconds | Hourly schedule interval - 120 seconds | Minimum interval between hourly activation windows |

The enforced rule is `900 < 960 < 3,480`. Set
`PIPELINE_WINDOW_SECONDS` in the root-only environment file only when an
approved duration preserves this inequality.

## Future VM Installation

Install Docker, deploy the application at `/opt/opportunity-radar`, install the
wrapper at `/usr/local/sbin/run-opportunity-radar-window`, and copy the unit
files to `/etc/systemd/system/`. The service runs as `root` because the verified
Docker socket is owned by `root:docker` with mode `0660`; it does not create or
grant login access to a service account. Keep `/opt/opportunity-radar` owned by
`root:root` with mode `0755`.

Create `/etc/opportunity-radar/api.env`, `worker.env`, `proxy.env`, `images.env`,
and `pipeline.env`, each owned by `root:root` with mode `0600`. systemd reads
these files before launching the wrapper, so Compose receives its interpolation
inputs without relaxing their permissions. Keep secrets in those files, never in
a unit or log. Keep `/etc/opportunity-radar` owned by `root:root` with mode
`0700`. The service fails closed when any required file is absent.

```sh
sudo install -o root -g root -m 0644 opportunity-radar-pipeline.service /etc/systemd/system/
sudo install -o root -g root -m 0644 opportunity-radar-pipeline.timer /etc/systemd/system/
sudo install -o root -g root -m 0755 run-opportunity-radar-window /usr/local/sbin/
sudo systemctl daemon-reload
sudo systemctl enable --now opportunity-radar-pipeline.timer
systemctl list-timers opportunity-radar-pipeline.timer
systemctl status opportunity-radar-pipeline.timer
```

Before the first migration that reaches revision `0069`, create a temporary
root-owned `/etc/opportunity-radar/migrate.env` with mode `0600` containing the
approved `OWNER_SUB_BACKFILL`. Run the migration once as root with the normal
environment files plus that temporary file, then remove `migrate.env` only after
the command succeeds:

```sh
sudo docker compose \
  --env-file /etc/opportunity-radar/api.env \
  --env-file /etc/opportunity-radar/worker.env \
  --env-file /etc/opportunity-radar/proxy.env \
  --env-file /etc/opportunity-radar/images.env \
  --env-file /etc/opportunity-radar/pipeline.env \
  --env-file /etc/opportunity-radar/migrate.env \
  -f /opt/opportunity-radar/compose.cloud.yaml \
  run --rm migrate \
  && sudo rm /etc/opportunity-radar/migrate.env
```

After revision `0069` is at head, the finite worker may still start the migration
service, but that revision no longer executes and its backfill value is absent.
If a database still needs `0069`, its migration fails closed without the
temporary value. This is a development-pilot installation contract for the
selected workers.dev and Clerk development configuration; it does not release a
production deployment.

The wrapper creates a UTC timestamp plus random suffix `RUN_ID`, calculates
`DEADLINE_UTC` at activation time, logs one redacted structured start line, and
executes the cloud Compose worker exactly once:

```sh
docker compose --project-name opportunity-radar \
  -f /opt/opportunity-radar/compose.cloud.yaml \
  run --rm -e RUN_ID -e DEADLINE_UTC worker
```

It exports `PIPELINE_DEADLINE_SECONDS` with the approved window duration. Set
`PIPELINE_COMPOSE_BIN` only for an approved command wrapper or test stub.

`Persistent=false` is intentional. A reboot or missed window must not trigger
automatic catch-up or an avalanche of overdue runs. The next scheduled UTC
window is the only automatic activation.

## Safe Stop

```sh
sudo systemctl disable --now opportunity-radar-pipeline.timer
systemctl is-active opportunity-radar-pipeline.timer
systemctl is-active opportunity-radar-pipeline.service
```

Allow the service to stop at its deadline. Use SIGTERM through systemd. Do not
use `kill -9`.

## External Proof

AC01-AC05 remain external acceptance checks. They require a real VM to prove a
complete window, reboot behavior, timeout, idle Neon connections, and missed
window alerting. These local artifacts and tests do not claim VM proof.
