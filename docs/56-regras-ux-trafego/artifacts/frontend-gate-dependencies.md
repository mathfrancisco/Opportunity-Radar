# Frontend gate — dependency recovery

Worktree: `C:\Users\mathf\Documents\GitHub\Opportunity-Radar\.worktrees\r56-rules-ux-traffic`

Node executable: `C:\Users\mathf\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`

Node version: `v24.19.0`

Before recovery, `node_modules/vitest/package.json`, `node_modules/@vitest/runner/package.json`,
`node_modules/@vitest/utils/package.json`, and `node_modules/jsdom/package.json` were absent.

The first sandboxed dependency install stopped with exit 1:

```text
npm error Exit handler never called!
npm error This is an error with npm itself. Please report this error at:
npm error   <https://github.com/npm/cli/issues>
```

The authorized retry outside the sandbox completed with exit 0:

```text
added 266 packages in 11s
```

Verification after the retry:

```text
vitest@5.0.1
jsdom@30.0.1
vitest@5.0.1 -> std-env@4.2.0
```

Focused command and result:

```text
> npm run test -- src/lib/queryClient.test.ts
Test Files  1 passed (1)
Tests  3 passed (3)
Duration  4.52s
exit 0
```

Partial gate results recorded before the coordinated full check:

```text
> npm run typecheck
> tsc -b --pretty false
exit 0
```

```text
> npm run lint
> eslint . --max-warnings=0
exit 1

apps/web/src/routes/InboxPage.tsx:467:19
react-hooks/set-state-in-effect

apps/web/src/test/requestBudgets.test.tsx:100:28
apps/web/src/test/requestBudgets.test.tsx:105:28
apps/web/src/test/requestBudgets.test.tsx:110:28
react-hooks/immutability
```

The three harness findings belong to the traffic-matrix executor. The Inbox finding was
fixed before the coordinated final gate. `InboxSearch` now owns the draft input and is keyed
by the canonical URL search value, avoiding an effect that sets state after render while
preserving submit, saved-search, and router back/forward synchronization.

Focused correction verification:

```text
> npm run test -- src/routes/InboxPage.test.tsx
Test Files  1 passed (1)
Tests  31 passed (31)
Duration  10.87s
exit 0
```

```text
> eslint src/routes/InboxPage.tsx --max-warnings=0
exit 0
```

Review follow-up: applying a saved search with no `search` parameter now increments a local
reset revision for `InboxSearch`. This clears an unsubmitted draft while ordinary filter changes
continue to preserve it. The focused regression test starts with an empty committed query, types
an unsubmitted draft, applies the saved search, and verifies `work_mode=REMOTE`, no `search`, and
an empty field.

```text
> npm run test -- src/routes/InboxPage.test.tsx
Test Files  1 passed (1)
Tests  31 passed (31)
Duration  10.87s
exit 0
```

```text
> eslint src/routes/InboxPage.tsx src/routes/InboxPage.test.tsx --max-warnings=0
exit 0
```

## Coordinated full gate — final retry

The prior captured run exited 1 during Vitest because jsdom attempted to create its environment
under the sandbox AppData temporary directory. Its literal terminal error was:

```text
Error: ENOENT: no such file or directory, open 'C:\\Users\\mathf\\AppData\\Local\\Packages\\sandbox.{22516cc0-adfc-4bab-b03d-4e3bd1ee51d6}\\AC\\Temp\\C--Eoo--8jtKSbqXI4UpK\\client\\e6e7afa0a9a5e93d5d0d8bcc26ca55807200bb93'
```

That attempt reached `47 failed | 1 passed` test files with 6 tests, all 47 affected suites
reporting zero collected tests. It was an environment failure rather than a result used for the
final gate. A separate pre-retry assertion in `RouteGuards.test.tsx` was corrected to require the
actual `AbortSignal` passed by the session query; the focused check then passed:

```text
> npm run test -- src/app/RouteGuards.test.tsx
Test Files  1 passed (1)
Tests  7 passed (7)
Duration  4.95s
exit 0
```

Final command, run from `apps/web` through the explicit Node 24.19.0 executable and persistent
terminal session (with `TEMP` and `TMP` set to native `apps/web/.tmp`):

```text
REQUEST_METRICS_MODE=final
REQUEST_METRICS_OUTPUT=C:\\Users\\mathf\\Documents\\GitHub\\Opportunity-Radar\\.worktrees\\r56-rules-ux-traffic\\docs\\56-regras-ux-trafego\\artifacts\\request-metrics-final.json
npm run check
```

Literal completion summary:

```text
> npm run lint
> eslint . --max-warnings=0
> npm run typecheck
> tsc -b --pretty false
> npm run test
> vitest run
Test Files  48 passed (48)
Tests  431 passed (431)
Duration  32.92s (environment 91%, tests 4%, import 3%, transform 2%, setup 1%)
> npm run build
> tsc -b && vite build
✓ built in 4.88s
exit 0
```

The build emitted its standard chunk-size warning for `index-C6W2zfph.js` (665.98 kB, gzip
191.09 kB); it did not change the exit status. Provenance: base `a7f62e302dc7633a005c5e7ada66402e0fa71435`;
SHA-256 `package.json` `C435C2195028B2CAB394504B79E6474D87A012A72FECE0962B5992037AA292AA`,
`package-lock.json` `3AF648B9E5AE71F17ECC55EE1927741EE33302BE95EA295070CAE8461CE90BCD`,
`RouteGuards.test.tsx` `BB99F24CA70FD6C62D4C17AE4D24032FB41B0F1D2E7FFD886E3F9C8D8F660419`.

### Métricas: snapshot do gate e artefato corrente

O hash `E680692F557086CEA6517F900CCC871BDC5D54C9CA09ECE54ED26F7B60AEA26C`
é o snapshot que este `npm run check` gerou. Não é o artefato corrente: o replay estreito
posterior, feito pela frente de tráfego, regenerou
[`request-metrics-final.json`](request-metrics-final.json) com SHA-256
`4AA64231...4EBE` e digest de fonte `a614db4f...b777`, acompanhado de proveniência completa
no artefato de tráfego. Este gate não foi reexecutado depois desse replay.

### Limpeza local de temporários

`apps/web/.tmp` foi confirmado como diretório nativo dentro desta worktree, sem `LinkType` ou
`Target`. Foi removido somente `frontend-gate-run-check.cmd`, o lançador de 583 bytes criado nesta
frente para a tentativa de captura anterior. Foram preservados os três logs
`frontend-gate-full-check.{stdout,stderr}.log` e `.exit`, pois registram a falha `ENOENT` que
justificou a repetição; também foram preservados os diretórios `check`, `vitest`,
`node-compile-cache`, `ifJvTFymRh-TSWLFE_nYi` e `YRlz920RjUSotnVw-s7ob`, cuja origem não foi
atribuída com segurança. Não houve remoção recursiva, junction ou limpeza de histórico.
