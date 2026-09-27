import { expect, test } from '@playwright/test'
import {
  ensureActiveProfile,
  evaluateOpportunity,
  getInboxItem,
  getOpportunity,
  runSource,
  seedEnabledGreenhouseSource,
  waitForInboxTotal,
} from '../support/api'
import { restartWorkerMidCollection, setBoardMode, setGroqMode } from '../support/compose'

const SOURCE_NAME = 'F20-47 failure scenarios board'

/**
 * Card F20-47: every injected-failure scenario the card lists, run one at a time (see
 * `playwright.config.ts`'s `workers: 1`) against a single seeded source so each scenario
 * proves the same three things the card asks for: no duplicate opportunity, no active
 * opportunity wrongly marked closed, and - for a Groq failure - the Inbox showing the
 * opportunity with no AI comment rather than hiding it or crashing.
 */
test.describe.serial('injected failures', () => {
  let sourceId: string
  let sourceName: string
  let searchTerm: string
  let opportunityId: string

  test.beforeAll(async () => {
    await ensureActiveProfile()
    // Own one-off board (unique token per call): this spec's opportunity title cannot
    // collide with one an earlier pipeline.yml step, or the other spec file, already
    // created - see seedEnabledGreenhouseSource's docstring for the regression this fixed.
    const source = await seedEnabledGreenhouseSource(SOURCE_NAME)
    sourceId = source.id
    sourceName = source.name
    searchTerm = source.searchTerm
    await runSource(sourceId)
    await waitForInboxTotal(searchTerm, (total) => total >= 1)
    const item = await getInboxItem(searchTerm)
    opportunityId = item.opportunity_id as string
    await evaluateOpportunity(opportunityId)
  })

  test.afterEach(async () => {
    await setGroqMode('ok')
    await setBoardMode('ok')
  })

  for (const mode of ['429', '500', 'invalid'] as const) {
    test(`Groq ${mode} degrades the analysis without touching the deterministic decision`, async ({
      page,
    }) => {
      await setGroqMode(mode)

      await page.goto(`/opportunities/${opportunityId}`)
      await expect(page.getByRole('heading', { name: searchTerm })).toBeVisible()

      // The worker's own `analyze_pending` job can hold the same assessment (it is also
      // hitting the failing stub right now), which answers this click's request with 409 -
      // "retry", not a failure (see `analyzeAssessment` in `features/matching/api.ts`).
      const degraded = page.getByText(/Camada semântica degradada/)
      const retryNeeded = page.getByText('Não foi possível falar com a API. Tente novamente.')
      for (let attempt = 0; attempt < 6; attempt += 1) {
        await page.getByRole('button', { name: /Analisar (com IA|novamente)/ }).click()
        const outcome = await Promise.race([
          degraded.waitFor({ timeout: 15_000 }).then(() => 'done' as const),
          retryNeeded.waitFor({ timeout: 15_000 }).then(() => 'retry' as const),
        ]).catch(() => 'retry' as const)
        if (outcome === 'done') break
        await page.waitForTimeout(3_000)
      }

      // The AI comment fails visibly instead of silently: a degraded banner, not the
      // analysis summary text.
      await expect(degraded).toBeVisible({ timeout: 15_000 })
      await expect(
        page.getByText('Vaga sênior remota em Python compatível com o perfil ativo.'),
      ).toHaveCount(0)

      // The deterministic decision is untouched by the AI failure.
      await expect(page.getByRole('heading', { name: 'Filtros eliminatórios' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Fatores do score' })).toBeVisible()

      // No duplicate, and the opportunity is not wrongly marked closed. The Inbox item
      // still shows up with no AI comment rather than disappearing.
      await page.goto(`/inbox?search=${encodeURIComponent(searchTerm)}`)
      await expect(page.getByText(/^1 oportunidade encontrada\.$/)).toBeVisible()
      await expect(page.getByRole('link', { name: searchTerm })).toBeVisible()
      await expect(page.getByText(/Análise semântica indisponível/)).toBeVisible()

      const opportunity = await getOpportunity(opportunityId)
      expect(opportunity.lifecycle_status).not.toBe('CLOSED')
    })
  }

  test('a job board manifest that overstates its page (partial pagination) creates no duplicate', async ({
    page,
  }) => {
    await setBoardMode('partial')

    await page.goto('/sources')
    const sourceCard = page.locator('article', { hasText: sourceName })
    await sourceCard.getByRole('button', { name: 'Executar agora' }).click()
    await expect(sourceCard.getByText(/Execução SUCCEEDED/)).toBeVisible({ timeout: 30_000 })

    await page.goto(`/inbox?search=${encodeURIComponent(searchTerm)}`)
    await expect(page.getByText(/^1 oportunidade encontrada\.$/)).toBeVisible({
      timeout: 30_000,
    })

    const opportunity = await getOpportunity(opportunityId)
    expect(opportunity.lifecycle_status).not.toBe('CLOSED')
  })

  test('a 304 Not Modified reply creates no duplicate and closes nothing', async ({ page }) => {
    await setBoardMode('304')

    await page.goto('/sources')
    const sourceCard = page.locator('article', { hasText: sourceName })
    await sourceCard.getByRole('button', { name: 'Executar agora' }).click()
    await expect(sourceCard.getByText(/Execução SUCCEEDED/)).toBeVisible({ timeout: 30_000 })

    await page.goto(`/inbox?search=${encodeURIComponent(searchTerm)}`)
    await expect(page.getByText(/^1 oportunidade encontrada\.$/)).toBeVisible({
      timeout: 30_000,
    })

    const opportunity = await getOpportunity(opportunityId)
    expect(opportunity.lifecycle_status).not.toBe('CLOSED')
  })

  test('restarting the worker mid-collection loses no data and creates no duplicate', async ({
    page,
  }) => {
    await page.goto('/sources')
    const sourceCard = page.locator('article', { hasText: sourceName })
    const run = sourceCard.getByRole('button', { name: 'Executar agora' }).click()
    await restartWorkerMidCollection()
    await run

    await page.goto(`/inbox?search=${encodeURIComponent(searchTerm)}`)
    await expect(page.getByText(/^1 oportunidade encontrada\.$/)).toBeVisible({
      timeout: 60_000,
    })

    const opportunity = await getOpportunity(opportunityId)
    expect(opportunity.lifecycle_status).not.toBe('CLOSED')
  })
})
