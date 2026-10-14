import { defineConfig, type Project } from '@playwright/test'

/**
 * F20-47: the browser journey against the Compose CI stack (`compose.yaml` +
 * `compose.ci.yaml`), already up and healthy before this project runs — see
 * `.github/workflows/pipeline.yml`'s `e2e` job and this directory's README-equivalent in
 * the card at `docs/44-roadmap-fase-20/fase-20/f20-47-percurso-e2e-e-falhas-injetadas.md`.
 *
 * Failure injection (`support/compose.ts`) shells out to `docker compose exec`, so the
 * scenarios run one at a time against the one stack instead of in parallel workers that
 * would race each other's failure mode.
 *
 * File order matters here, hence the `01-`/`02-` prefixes: the AI router's circuit
 * breaker (`platform/ai/breaker.py`) is in-process state that outlives any one test — once
 * a Groq 429/500 scenario trips it, real analysis calls answer `QUOTA_EXHAUSTED` for its
 * ~120s cooldown regardless of the fake server's mode. The happy path's own, genuine
 * analysis call has to land before any failure scenario ever opens that breaker.
 */
/**
 * Projects are named so nobody can mistake offline coverage for full browser acceptance.
 *
 * CI runs only the first two. Signed-in browser journeys need a real Clerk session, which
 * is an external gate: no fake signed-in bundle is allowed, so those specs are kept (not
 * deleted, not passed) in a project that exists only when E2E_REAL_CLERK_SESSION=1 and a
 * Clerk-issued storage state is supplied.
 */
const projects: Project[] = [
  {
    name: 'offline-no-clerk-config',
    testMatch: '00-offline-auth.spec.ts',
    // The browser does not trust the run's ephemeral CI CA (served on loopback), and this
    // project signs nothing in. Scoped here so a real-Clerk project never inherits it.
    use: { ignoreHTTPSErrors: true },
  },
  {
    name: 'api-authenticated',
    testMatch: '04-api-auth.spec.ts',
    // Node-side requests only; keep any bearer out of traces and videos.
    use: { trace: 'off', video: 'off', screenshot: 'off' },
  },
]

if (process.env.E2E_REAL_CLERK_SESSION === '1') {
  const storageState = process.env.E2E_CLERK_STORAGE_STATE
  if (!storageState) {
    throw new Error('requires-real-clerk-session-external-gate needs E2E_CLERK_STORAGE_STATE')
  }
  projects.push({
    name: 'requires-real-clerk-session-external-gate',
    testMatch: ['01-happy-path.spec.ts', '02-failure-scenarios.spec.ts', '03-visual.spec.ts'],
    use: { storageState },
  })
}

export default defineConfig({
  testDir: './specs',
  // Specs are assigned to projects below; no spec runs outside a named project.
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'report' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'https://127.0.0.1:8443',
    trace: 'retain-on-failure',
    // Always on, not just on failure: the card wants the happy path's own screenshots as
    // CI evidence, not only a failing run's.
    screenshot: 'on',
    video: 'retain-on-failure',
  },
  outputDir: 'test-results',
  projects,
})
