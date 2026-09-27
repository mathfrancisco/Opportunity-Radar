import { defineConfig } from '@playwright/test'

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
export default defineConfig({
  testDir: './specs',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'report' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3000',
    trace: 'retain-on-failure',
    // Always on, not just on failure: the card wants the happy path's own screenshots as
    // CI evidence, not only a failing run's.
    screenshot: 'on',
    video: 'retain-on-failure',
  },
  outputDir: 'test-results',
})
