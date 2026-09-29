/**
 * Setup and polling helpers that talk to the API directly (the same public API the UI
 * calls), so the browser journey itself starts from a known state instead of first
 * clicking through homologation - a separate, already-covered flow - for a source that
 * only needs to exist and be enabled before the test opens the browser.
 */

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3000'

function apiUrl(path: string): URL {
  return new URL(`/api${path}`, BASE_URL)
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`${init?.method ?? 'GET'} ${path} -> ${response.status}: ${body}`)
  }
  return response.status === 204 ? null : response.json()
}

/**
 * Creates an already-homologated, enabled Greenhouse source pointed at a fresh, one-off
 * board on the local `fake_job_board.py` stub (`board_token: e2e-<random>`, wired through
 * `GREENHOUSE_BASE_URL` in `compose.ci.yaml`). Mirrors how `pipeline.yml`'s "Verify the
 * autonomous cycle" step seeds a source in one call.
 *
 * The board token is unique per call, not just the source name: `pipeline.yml`'s earlier
 * steps (manual acquisition, the autonomous-cycle gate) already create their own
 * opportunities titled "Senior Python Engineer" against fixed boards before this suite ever
 * runs. A fixed board token here would dedupe into, or collide on title with, one of those -
 * which is exactly the regression this fixed: two "Senior Python Engineer" links on the
 * same Inbox page, `getByRole('link', ...)` matching either one. `fake_job_board.py` answers
 * any `e2e-*` board with a job titled after that token, so the search term this returns is
 * guaranteed to match this call's own opportunity and nothing another step created.
 */
export async function seedEnabledGreenhouseSource(namePrefix: string): Promise<{
  id: string
  name: string
  boardToken: string
  searchTerm: string
}> {
  // Unique per run: a re-run against the same stack (a retried CI job, a local rerun while
  // debugging, another spec file in the same CI job) must not collide with a source or an
  // opportunity title a previous run already created.
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const name = `${namePrefix} ${unique}`
  const boardToken = `e2e-${unique}`
  const searchTerm = `Senior Python Engineer (${boardToken})`
  const source = (await request('/sources', {
    method: 'POST',
    body: JSON.stringify({
      source_type: 'greenhouse',
      name,
      enabled: true,
      evidence_status: 'confirmed',
      terms_reviewed: true,
      collector_local_tested: true,
      reviewed_at: '2026-09-01T00:00:00Z',
      configuration: { board_token: boardToken, company_name: 'Radar CI' },
    }),
  })) as { id: string }
  return { id: source.id, name, boardToken, searchTerm }
}

interface InboxTotal {
  total: number
}

/** Polls the public Inbox search until at least one matching item shows up, or times out. */
export async function waitForInboxTotal(
  search: string,
  predicate: (total: number) => boolean,
  { timeoutMs = 90_000, intervalMs = 2_000 } = {},
): Promise<number> {
  const deadline = Date.now() + timeoutMs
  let lastTotal = -1
  while (Date.now() < deadline) {
    const body = (await request(`/inbox?search=${encodeURIComponent(search)}`)) as InboxTotal
    lastTotal = body.total
    if (predicate(lastTotal)) return lastTotal
    await new Promise((doneWaiting) => setTimeout(doneWaiting, intervalMs))
  }
  throw new Error(`inbox total for "${search}" never satisfied the predicate (last: ${lastTotal})`)
}

export async function getInboxItem(search: string): Promise<Record<string, unknown>> {
  const body = (await request(`/inbox?search=${encodeURIComponent(search)}`)) as {
    items: Record<string, unknown>[]
  }
  if (body.items.length === 0) throw new Error(`no inbox item for "${search}"`)
  return body.items[0]
}

export async function getOpportunity(opportunityId: string): Promise<Record<string, unknown>> {
  return (await request(`/opportunities/${opportunityId}`)) as Record<string, unknown>
}

export async function runSource(sourceId: string): Promise<Record<string, unknown>> {
  return (await request(`/sources/${sourceId}/runs`, {
    method: 'POST',
    body: JSON.stringify({ correlation_id: `e2e-browser-${Date.now()}` }),
  })) as Record<string, unknown>
}

/**
 * Ensures an active profile exists with the skills and preferences the seeded job matches,
 * the same way `pipeline.yml`'s own steps do (draft -> publish -> activate). The failure
 * scenarios need a profile to evaluate against but do not exercise editing one - that is
 * `01-happy-path.spec.ts`'s job, and the two spec files run independently of each other.
 */
export async function ensureActiveProfile(): Promise<void> {
  const profile = (await request('/profile').catch(() => null)) as { status: string } | null
  if (profile?.status === 'ACTIVE') return

  const draft = (await request('/profile/versions', {
    method: 'POST',
    body: JSON.stringify({
      expected_profile_version: 0,
      skills: [{ canonical_name: 'python' }, { canonical_name: 'react' }],
      preferences: {
        work_modes: ['REMOTE'],
        contracts: ['FULL_TIME'],
        countries: ['BR'],
      },
    }),
  })) as { id: string; profile_lock_version: number }
  const published = (await request(`/profile/versions/${draft.id}/publish`, {
    method: 'POST',
    body: JSON.stringify({ expected_profile_version: draft.profile_lock_version }),
  })) as { profile_lock_version: number }
  await request(`/profile/versions/${draft.id}/activate`, {
    method: 'POST',
    body: JSON.stringify({ expected_profile_version: published.profile_lock_version }),
  })
}

export async function evaluateOpportunity(opportunityId: string): Promise<{ id: string }> {
  return (await request('/matches/evaluate', {
    method: 'POST',
    body: JSON.stringify({ opportunity_id: opportunityId }),
  })) as { id: string }
}
