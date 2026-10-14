import { expect, test } from '@playwright/test'
import {
  evaluateOpportunity,
  ensureActiveProfile,
  getInboxItem,
  getOpportunity,
  request,
  runSource,
  seedEnabledGreenhouseSource,
  waitForInboxTotal,
} from '../support/api'
import { bearerHeader } from '../support/auth'

/**
 * API-level coverage with a fixture bearer (no browser): the business assertions of the
 * happy path (collect, search, evaluate) plus the authentication boundary. It proves the
 * production API contract the signed-in UI relies on; it does not prove the UI itself.
 */
const BASE_URL = process.env.E2E_BASE_URL ?? 'https://127.0.0.1:8443'

async function status(path: string, headers: Record<string, string> = {}): Promise<number> {
  const response = await fetch(new URL(`/api${path}`, BASE_URL), { headers })
  return response.status
}

test.describe('API with an offline bearer', () => {
  test('the boundary refuses anonymous and non-owner callers', async () => {
    expect(await status('/health/live')).toBe(200)
    expect(await status('/sources')).toBe(401)
    expect(await status('/sources', { Authorization: bearerHeader('non-owner') })).toBe(403)
    expect(await status('/sources', { Authorization: bearerHeader('owner') })).toBe(200)
  })

  test('collection, search, evaluation and analysis state work for the owner', async () => {
    await ensureActiveProfile()
    const source = await seedEnabledGreenhouseSource('API auth happy path')
    const run = await runSource(source.id)
    expect(run.status).toBe('SUCCEEDED')

    await waitForInboxTotal(source.searchTerm, (total) => total >= 1)
    const item = await getInboxItem(source.searchTerm)
    expect(item.company_name).toBe('Radar CI')

    const opportunity = await getOpportunity(String(item.opportunity_id))
    expect(String(opportunity.title)).toContain(source.boardToken)

    const match = await evaluateOpportunity(String(item.opportunity_id))
    const again = await evaluateOpportunity(String(item.opportunity_id))
    expect(again.id).toBe(match.id)

    const detail = (await request(`/matches/${match.id}`)) as { factors: unknown[] }
    expect(detail.factors.length).toBeGreaterThan(0)
  })
})
