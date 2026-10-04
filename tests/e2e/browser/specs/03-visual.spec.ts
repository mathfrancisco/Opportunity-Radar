import { expect, test, type Page } from '@playwright/test'

/**
 * Card F46-10 (SPEC 46, 11): every migrated screen fits a 320px viewport without page-level
 * horizontal scroll, and is captured at 1280 and 375 for the human visual review. Runs after
 * the happy path (`01-`) and failure scenarios (`02-`) so the Inbox, Sources and detail
 * pages already hold real data. No pixel baseline (D9): screenshots are evidence only, saved
 * under `test-results/` and uploaded with the rest of the journey's artifacts.
 */
const SCREENS = [
  { name: 'visao-geral', path: '/' },
  { name: 'inbox', path: '/inbox' },
  { name: 'candidaturas', path: '/applications' },
  { name: 'empresas', path: '/companies' },
  { name: 'fontes', path: '/sources' },
  { name: 'fila-homologacao', path: '/sources/homologation-queue' },
  { name: 'perfil', path: '/profile' },
  { name: 'status', path: '/status' },
] as const

async function settle(page: Page) {
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => document.fonts.ready)
}

async function overflow(page: Page) {
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }))
}

async function firstHref(page: Page, listPath: string, pattern: RegExp): Promise<string> {
  await page.goto(listPath)
  await settle(page)
  const hrefs = await page
    .locator('a[href]')
    .evaluateAll((links) => links.map((link) => link.getAttribute('href') ?? ''))
  const found = hrefs.find((href) => pattern.test(href))
  expect(found, `no link matching ${pattern} on ${listPath}`).toBeTruthy()
  return found as string
}

test.describe('visual evidence and responsiveness', () => {
  for (const screen of SCREENS) {
    test(`${screen.name}: no horizontal scroll at 320px, screenshots at 1280 and 375`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1280, height: 800 })
      await page.goto(screen.path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await settle(page)
      await page.screenshot({ path: `test-results/visual/${screen.name}-1280.png`, fullPage: true })

      await page.setViewportSize({ width: 375, height: 800 })
      await settle(page)
      await page.screenshot({ path: `test-results/visual/${screen.name}-375.png`, fullPage: true })

      await page.setViewportSize({ width: 320, height: 800 })
      await settle(page)
      const { scrollWidth, innerWidth } = await overflow(page)
      expect(scrollWidth, `${screen.path} scrollWidth vs innerWidth`).toBeLessThanOrEqual(innerWidth)
    })
  }

  test('detail screens: no horizontal scroll at 320px, screenshots at 1280 and 375', async ({
    page,
  }) => {
    const details = [
      { name: 'vaga', href: await firstHref(page, '/inbox', /^\/opportunities\/[^/]+$/) },
      { name: 'empresa', href: await firstHref(page, '/companies', /^\/companies\/[^/]+$/) },
    ]
    for (const detail of details) {
      await page.setViewportSize({ width: 1280, height: 800 })
      await page.goto(detail.href)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await settle(page)
      await page.screenshot({ path: `test-results/visual/${detail.name}-1280.png`, fullPage: true })
      await page.setViewportSize({ width: 375, height: 800 })
      await settle(page)
      await page.screenshot({ path: `test-results/visual/${detail.name}-375.png`, fullPage: true })
      await page.setViewportSize({ width: 320, height: 800 })
      await settle(page)
      const { scrollWidth, innerWidth } = await overflow(page)
      expect(scrollWidth, `${detail.href} scrollWidth vs innerWidth`).toBeLessThanOrEqual(innerWidth)
    }
  })
})

/** Focus must be visible: a real outline (or ring) at least 2px wide, never `none`. */
async function focusIndicator(page: Page) {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null
    if (!element) return null
    // A focus-within wrapper (FilterPill) carries the ring instead of its native select.
    const candidates = [element, element.parentElement].filter(Boolean) as HTMLElement[]
    return candidates
      .map((node) => {
        const style = getComputedStyle(node)
        return {
          tag: node.tagName,
          style: style.outlineStyle,
          width: parseFloat(style.outlineWidth),
        }
      })
      .find((entry) => entry.style !== 'none' && entry.width >= 2) ?? null
  })
}

test.describe('keyboard and focus', () => {
  test('skip link is the first tab stop, shows a focus ring and lands on the content', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto('/inbox')
    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: 'Pular para o conteúdo' })
    await expect(skip).toBeFocused()
    await expect(skip).toBeVisible()
    expect(await focusIndicator(page)).not.toBeNull()
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/#conteudo$/)
  })

  test('sidebar links take focus in order and show a focus ring', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto('/')
    const nav = page.getByRole('navigation').first()
    const links = nav.getByRole('link')
    const count = await links.count()
    expect(count).toBeGreaterThan(3)
    await links.first().focus()
    expect(await focusIndicator(page)).not.toBeNull()
    for (let index = 1; index < count; index += 1) {
      await page.keyboard.press('Tab')
      await expect(links.nth(index)).toBeFocused()
    }
  })

  test('mobile drawer opens by button, Escape closes and returns focus', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    await page.goto('/')
    const menu = page.getByRole('button', { name: 'Menu' })
    await expect(menu).toHaveAttribute('aria-expanded', 'false')
    await menu.click()
    await expect(menu).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByRole('navigation').first()).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveAttribute('aria-expanded', 'false')
    await expect(menu).toBeFocused()
  })

  test('filter pills are keyboard reachable with a visible focus ring', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto('/inbox')
    await settle(page)
    const selects = page.locator('select')
    expect(await selects.count()).toBeGreaterThan(0)
    await selects.first().focus()
    expect(await focusIndicator(page)).not.toBeNull()
  })

  test('pagination controls are real buttons or links with names, current page marked', async ({
    page,
  }) => {
    await page.route('**/api/companies*', async (route) => {
      const url = new URL(route.request().url())
      const pageNumber = Number(url.searchParams.get('page') ?? '1')
      const pageSize = Number(url.searchParams.get('page_size') ?? '25')
      const total = 26
      const first = (pageNumber - 1) * pageSize
      const items = Array.from({ length: Math.max(0, Math.min(pageSize, total - first)) }, (_, index) => ({
        id: `visual-company-${first + index + 1}`,
        name: `Empresa visual ${first + index + 1}`,
        domain: null,
        priority: 'normal',
        status: 'active',
        verification_state: 'unverified',
        sources: [],
      }))
      await route.fulfill({ json: { items, page: pageNumber, page_size: pageSize, total } })
    })
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto('/companies')
    await settle(page)
    const pagination = page.getByRole('navigation', { name: /pagina/i })
    await expect(pagination).toBeVisible()
    await expect(pagination.getByRole('button', { name: 'Página anterior' })).toBeDisabled()
    await expect(pagination.locator('[aria-current="page"]')).toHaveCount(1)
    const next = pagination.getByRole('button', { name: 'Próxima página' })
    await next.focus()
    expect(await focusIndicator(page)).not.toBeNull()
  })
})
