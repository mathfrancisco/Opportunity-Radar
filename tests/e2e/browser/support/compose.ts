import { execFile } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { promisify } from 'node:util'

const run = promisify(execFile)

/**
 * The repository root, computed from this file's own location so the helper works no
 * matter what the test runner's current working directory is (`tests/e2e/browser` when run
 * standalone, the repo root when run from `.github/workflows/pipeline.yml`).
 */
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..')

/**
 * Which Compose project the stack under test is running as.
 *
 * CI (`pipeline.yml`) runs `docker compose` with no `-p`, so the project name is the
 * checkout directory's name. Local isolated runs pass `E2E_COMPOSE_PROJECT=f20e2e47` (see
 * the card's "Run locally" instructions) to target that project instead of guessing.
 */
function composeArgs(): string[] {
  const project = process.env.E2E_COMPOSE_PROJECT
  const args = project ? ['-p', project] : []
  return [...args, '-f', 'compose.yaml', '-f', 'compose.ci.yaml']
}

async function compose(...args: string[]): Promise<void> {
  await run('docker', ['compose', ...composeArgs(), ...args], { cwd: REPO_ROOT })
}

/**
 * Flips the fake Groq server's live failure mode (`ok` | `429` | `500` | `invalid`) without
 * restarting the container — a restart would drop the connection a browser test is mid-way
 * through. See `tests/e2e/fake_groq.py`'s `current_mode()`.
 */
export async function setGroqMode(mode: 'ok' | '429' | '500' | 'invalid'): Promise<void> {
  await compose('exec', '-T', 'groq', 'sh', '-c', `echo ${mode} > /tmp/fake_groq_mode`)
}

/**
 * Flips the fake job board's live failure mode (`ok` | `partial` | `304`). See
 * `tests/e2e/fake_job_board.py`'s `current_mode()`.
 */
export async function setBoardMode(mode: 'ok' | 'partial' | '304'): Promise<void> {
  await compose('exec', '-T', 'jobboard', 'sh', '-c', `echo ${mode} > /tmp/fake_board_mode`)
}

/** Restarts the worker mid-cycle, then waits for the API's readiness probe again. */
export async function restartWorkerMidCollection(): Promise<void> {
  await compose('restart', 'worker')
  await waitForReady()
}

async function waitForReady(): Promise<void> {
  const baseUrl = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3000'
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    try {
      const response = await fetch(new URL('/api/overview', baseUrl))
      if (response.ok) return
    } catch {
      // Not ready yet.
    }
    await new Promise((doneWaiting) => setTimeout(doneWaiting, 2_000))
  }
  throw new Error('worker did not become reachable again after restart')
}
