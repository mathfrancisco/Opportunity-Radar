import { expect, test } from '@playwright/test'

/**
 * OFFLINE fail-closed rendering only. This is NOT browser acceptance of the signed-in
 * product: that needs a real Clerk session (an external gate) and lives in the project
 * `requires-real-clerk-session-external-gate`, which CI does not run.
 *
 * The frontend image is built without VITE_CLERK_PUBLISHABLE_KEY, so it must show the
 * controlled configuration alert, render no private page or data, and attempt neither a
 * private API request nor any Clerk request.
 */
const PRIVATE_PATHS = ['/', '/inbox', '/sources', '/profile', '/applications']

test.describe('offline: no Clerk configuration', () => {
  for (const path of PRIVATE_PATHS) {
    test(`direct navigation to ${path} stays fail-closed`, async ({ page }) => {
      const requests: string[] = []
      page.on('request', (request) => requests.push(request.url()))

      await page.goto(path)
      const alert = page.getByRole('alert')
      await expect(alert).toBeVisible()
      await expect(alert).toContainText('VITE_CLERK_PUBLISHABLE_KEY')
      await expect(alert).toContainText('A autenticação não foi iniciada')

      // No application shell, navigation or page content next to the alert.
      await expect(page.getByRole('navigation')).toHaveCount(0)
      await expect(page.getByRole('table')).toHaveCount(0)
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)

      await page.waitForLoadState('networkidle')
      const origin = new URL(page.url()).origin
      expect(requests.filter((url) => new URL(url).pathname.startsWith('/api/'))).toEqual([])
      expect(requests.filter((url) => new URL(url).origin !== origin)).toEqual([])
      expect(requests.filter((url) => /clerk/i.test(url))).toEqual([])
    })
  }
})
