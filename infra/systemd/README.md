# Systemd Pipeline Contract

These files define a manual systemd installation for one finite Opportunity
Radar pipeline window. They are versioned artifacts only. Nothing is installed
or enabled by this repository.

## Timing Contract

| Value | Setting | Meaning |
| --- | --- | --- |
| 3,600 seconds | `DEFAULT_WINDOW_SECONDS` | Runner deadline passed as `--deadline-seconds` |
| 3,900 seconds | `TimeoutStartSec` | Maximum service start time |
| 300 seconds | `RandomizedDelaySec` | Schedule jitter |
| 86,100 seconds | 24 hours - 300 seconds | Minimum interval between daily activation windows |

The enforced rule is `3,600 < 3,900 < 86,100`. Set
`PIPELINE_WINDOW_SECONDS` in the root-only environment file only when an
approved duration preserves this inequality.

## Future VM Installation

An operator must create the `opportunity-radar` non-login user, deploy the
application at `/opt/opportunity-radar`, install the wrapper at
`/usr/local/sbin/run-opportunity-radar-window`, and copy the unit files to
`/etc/systemd/system/`. Create `/etc/opportunity-radar/pipeline.env` with mode
`0600`. Keep secrets in that file, never in a unit or log.

```sh
sudo install -o root -g root -m 0644 opportunity-radar-pipeline.service /etc/systemd/system/
sudo install -o root -g root -m 0644 opportunity-radar-pipeline.timer /etc/systemd/system/
sudo install -o root -g root -m 0755 run-opportunity-radar-window /usr/local/sbin/
sudo systemctl daemon-reload
sudo systemctl enable --now opportunity-radar-pipeline.timer
systemctl list-timers opportunity-radar-pipeline.timer
systemctl status opportunity-radar-pipeline.timer
```

The wrapper creates a UTC timestamp plus random suffix `RUN_ID`, calculates
`DEADLINE_UTC` at activation time, logs one redacted structured start line, and
executes the finite runner exactly once. The current runner accepts the
duration as `--deadline-seconds`; `RUN_ID` and `DEADLINE_UTC` are exported for
correlation by the runner and its child processes.

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
