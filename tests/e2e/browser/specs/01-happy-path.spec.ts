import { expect, test } from '@playwright/test'
import { seedEnabledGreenhouseSource, waitForInboxTotal } from '../support/api'

const SEARCH_TERM = 'Senior Python Engineer'
const SOURCE_NAME = 'F20-47 happy path board'

/**
 * Card F20-47: the full cycle profile -> preference -> collection -> search -> analysis ->
 * application, driven from the browser against the Compose CI stack, with no terminal step
 * inside the journey itself (seeding the source below is out-of-journey setup, exactly the
 * homologation flow `pipeline.yml`'s API-only steps already cover).
 */
test.describe('happy path', () => {
  test('profile, collection, search, analysis and application all complete without a terminal', async ({
    page,
  }) => {
    // 1. Profile: fill it from empty, in the browser.
    await page.goto('/profile')
    await expect(page.getByRole('heading', { name: 'Perfil e preferências' })).toBeVisible()
    const skillsInput = page.getByPlaceholder('python, react, postgresql')
    await skillsInput.fill('python, react')
    await page.getByPlaceholder('BR, PT').fill('BR')
    await page.getByRole('checkbox', { name: 'REMOTE' }).check()
    await page.getByRole('checkbox', { name: 'FULL_TIME' }).check()
    await page.getByRole('button', { name: 'Salvar como nova versão e ativar' }).click()
    await expect(page.getByText(/Versão \d+ ativa\./)).toBeVisible()

    // 2. Preference: edit it, in a second save that creates another version.
    await page.getByPlaceholder('backend engineer, engenheiro de software').fill('backend engineer')
    await page.getByRole('button', { name: 'Salvar como nova versão e ativar' }).click()
    await expect(page.getByText(/Versão \d+ ativa\./)).toBeVisible()

    // 3. Collection: trigger it from the Sources page against the local fake job board.
    const source = await seedEnabledGreenhouseSource(SOURCE_NAME)
    await page.goto('/sources')
    const sourceCard = page.locator('article', { hasText: source.name })
    await expect(sourceCard).toBeVisible()
    await sourceCard.getByRole('button', { name: 'Executar agora' }).click()
    await expect(sourceCard.getByText(/Execução SUCCEEDED/)).toBeVisible({ timeout: 30_000 })

    // Normalisation, matching and analysis happen on the worker's own schedule; give it
    // room, the same way pipeline.yml's autonomous-cycle step does.
    await waitForInboxTotal(SEARCH_TERM, (total) => total >= 1)

    // 4. Search: find it from the Inbox.
    await page.goto(`/inbox?search=${encodeURIComponent(SEARCH_TERM)}`)
    const itemLink = page.getByRole('link', { name: SEARCH_TERM })
    await expect(itemLink).toBeVisible({ timeout: 30_000 })

    // 5. Open the opportunity.
    await itemLink.click()
    await expect(page.getByRole('heading', { name: SEARCH_TERM })).toBeVisible()

    // 6. Evaluate (deterministic) then analyse (semantic) it.
    await page.getByRole('button', { name: 'Avaliar agora' }).click()
    await expect(page.getByRole('heading', { name: 'Filtros eliminatórios' })).toBeVisible({
      timeout: 30_000,
    })

    // The board's one fixed job also backs the failure-scenarios spec's opportunity (same
    // content, deduplicated to the same row), so the worker's own `analyze_pending` job can
    // be mid-analysis when this click lands — the API answers a concurrent claim with 409,
    // which is "retry", not a failure (see `analyzeAssessment` in `features/matching/api.ts`).
    const analysisSummary = page
      .getByText('Remote senior Python role that matches the active profile stack.')
      .or(page.getByText('Vaga sênior remota em Python compatível com o perfil ativo.'))
    const analyzeFailed = page.getByText('Não foi possível falar com a API. Tente novamente.')
    for (let attempt = 0; attempt < 6; attempt += 1) {
      await page.getByRole('button', { name: /Analisar (com IA|novamente)/ }).click()
      const outcome = await Promise.race([
        analysisSummary.waitFor({ timeout: 15_000 }).then(() => 'done' as const),
        analyzeFailed.waitFor({ timeout: 15_000 }).then(() => 'retry' as const),
      ]).catch(() => 'retry' as const)
      if (outcome === 'done') break
      await page.waitForTimeout(3_000)
    }
    await expect(analysisSummary).toBeVisible({ timeout: 15_000 })

    // 7. Create the application (candidatura).
    await page.getByRole('button', { name: 'Registrar interesse' }).click()
    // "Interesse" shows twice once the application exists (current stage and history
    // entry): .first() is the current-stage label, which is what proves it was created.
    await expect(page.getByText('Interesse').first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: 'Histórico' })).toBeVisible()
  })
})
