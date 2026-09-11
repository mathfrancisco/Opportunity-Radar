# Codex operating model

## Orchestration

- The primary `gpt-5.6-sol`/high agent owns scope, decisions, integration, validation, and the final answer.
- For implementation that divides cleanly, delegate bounded slices to at most three subagents. Use `explorer` for cheap read-only discovery and `worker` for code changes.
- Give every worker explicit file/responsibility ownership and acceptance criteria. Workers are not alone in the codebase and must not revert other edits.
- After workers finish, the primary agent inspects the combined diff and decides whether more work is needed.
- Keep trivial or tightly coupled work in the primary thread; delegation must save context or wall time.

## Validation

- Do not run unit tests, integration tests, E2E tests, linters, type checks, builds, audits, or equivalent local validation unless the user explicitly asks for that run.
- Put repeatable validation in `.github/workflows/pipeline.yml` and rely on CI feedback by default.
- Read-only inspection and edits needed to implement the requested change remain allowed.
- If CI reports a failure, inspect that failure and fix it without repeating unrelated validation locally.

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
- RTK is applied automatically only to simple supported commands. Use `rtk gain` for its savings report.

## Git identity

Identity is resolved by folder through `includeIf` in `~/.gitconfig`; there is no global identity.

- `Documents/GitHub/**` -> `mathfrancisco` / `math.francisco2@gmail.com`
- `Documents/Aura/**` -> `mathfrancisco-dev` / `matheus@auraveracity.com`

Outside those folders, set `user.email` locally instead of restoring a global identity.
