# Codex operating model

## Orchestration

- Sol and Astra coordinate and review read-only; they own scope, planning, assignments, integration decisions, verification assessment, and the final answer; they do not implement work, documentation, or configuration, and make no mutations themselves.
- Assign every mutation to one bounded Luna or Terra worker; use at most three workers only for independent scopes. Give each worker owned files or responsibility and acceptance criteria.
- The assigned executor role overrides inherited coordinator instructions and environment. Workers do not recursively delegate or orchestrate; receive a compact brief and return changed-file references, evidence, and uncertainty. Never claim unrun checks passed.
- For long tasks only, retain a compact durable checkpoint of decisions, completed work, pending work, and blockers before compaction.

## Validation

- Run local validation (tests, linters, type checks) when it verifies the change. Start with the narrowest target (one test file or module), then widen if needed.
- Keep repeatable validation in `.github/workflows/pipeline.yml`; add new checks there too.
- If CI reports a failure, inspect that failure and fix it.

## Review

Only three review routes. Do not use `/review`, `/code-review`, or `/security-review` unless requested by name.

| Request | Route |
| --- | --- |
| Excess code, bloat, or over-engineering | Primary Sol reviews directly for the smallest correct implementation |
| PR comments or feedback for another person | `/caveman-review` |
| Diff, branch, or file review for bugs | agent `cavecrew-reviewer` |

Architecture and threat modeling remain separate skills.

## Token discipline

- Keep command output bounded: search first, select relevant lines, and summarize large logs inside the shell.
- Do not load multiple overlapping skills for one task. Prefer the narrowest matching workflow.
- Start a new thread when the task or repository changes materially.
- Use RTK explicitly for supported simple git status/diff/log and package/test commands when checks are allowed. Do not double-prefix commands; use the RTK proxy for raw output when evidence requires it. Codex has no automatic RTK hook.

## Git identity

Identity is resolved by folder through `includeIf` in `~/.gitconfig`; there is no global identity.

- `Documents/GitHub/**` -> `mathfrancisco` / `math.francisco2@gmail.com`
- `Documents/Aura/**` -> `mathfrancisco-dev` / `matheus@auraveracity.com`

Outside those folders, set `user.email` locally instead of restoring a global identity.
