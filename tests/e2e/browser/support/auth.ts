import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Node-side bearer for the Compose CI stack (test-only). The header file is minted from the
 * run's ephemeral key by `tests/e2e/auth/auth-curl.sh --refresh`, the same single path the
 * workflow's curl calls use, and re-minted when under a minute of validity remains. The
 * token is only ever put in a request header: never logged, never in a trace or artifact.
 *
 * Trust: Node must run with NODE_EXTRA_CA_CERTS pointing at `$CI_AUTH_DIR/public/ca.pem`.
 */
const SCRIPT = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  '..',
  'auth',
  'auth-curl.sh',
)

function authDir(): string {
  const directory = process.env.CI_AUTH_DIR
  if (!directory) throw new Error('CI_AUTH_DIR is required for authenticated API requests')
  return directory
}

export function bearerHeader(persona: 'owner' | 'non-owner' = 'owner'): string {
  const header = join(authDir(), 'tokens', `${persona}.header`)
  const expiry = join(authDir(), 'tokens', `${persona}.exp`)
  let remaining = -1
  try {
    remaining = Number(readFileSync(expiry, 'utf8').trim()) - Date.now() / 1000
  } catch {
    // Not minted yet.
  }
  if (!(remaining > 60)) {
    execFileSync('bash', [SCRIPT, '--refresh'], {
      env: { ...process.env, AUTH_PERSONA: persona },
      stdio: 'ignore',
    })
  }
  return readFileSync(header, 'utf8').replace(/^Authorization:\s*/i, '').trim()
}
