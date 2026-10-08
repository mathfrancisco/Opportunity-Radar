/**
 * One-off harness contract for the post-gate baseline. Keep it outside app/ and CI.
 * It must serve dist itself; never invoke Vite, its /api proxy, Docker, or a backend.
 *
 * The static server and browser are isolated from backend services. API responses
 * are synthetic and matched by exact pathname; unmatched API requests are recorded.
 */
import { createServer } from 'node:http'
import { readFile, mkdir, writeFile, readdir } from 'node:fs/promises'
import { resolve, extname, relative, sep } from 'node:path'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import playwright from '../../tests/e2e/browser/node_modules/playwright/index.js'
import { fixtures, unmatchedFixtureBody } from './fixtures.mjs'
const { chromium } = playwright

const scriptDirectory = resolve(fileURLToPath(new URL('.', import.meta.url)))
const repoRoot = resolve(scriptDirectory, '../..')
const dist = resolve(repoRoot, 'apps/web/dist')
const output = resolve(repoRoot, 'docs/54-baseline/artifacts')

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex')
}

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(entries.map(async (entry) => {
    const path = resolve(directory, entry.name)
    return entry.isDirectory() ? listFiles(path) : [path]
  }))
  return nested.flat()
}

const repoSha = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8', cwd: repoRoot }).trim()
const buildFiles = await listFiles(dist)
const buildIdentity = {
  repoSha,
  index: {
    path: '/index.html',
    sha256: sha256(await readFile(resolve(dist, 'index.html'))),
  },
  assets: await Promise.all(buildFiles
    .filter((path) => relative(dist, path).split(sep).join('/').startsWith('assets/'))
    .map(async (path) => ({
      path: `/${relative(dist, path).split(sep).join('/')}`,
      sha256: sha256(await readFile(path)),
    }))),
}
const server = createServer(async (req, res) => {
  const pathname = new URL(req.url, 'http://x').pathname
  const file = pathname === '/' ? '/index.html' : pathname
  try {
    const body = await readFile(resolve(dist, `.${file}`))
    const extension = extname(file)
    const contentType = extension === '.js'
      ? 'text/javascript'
      : extension === '.css'
        ? 'text/css'
        : 'text/html'
    res.writeHead(200, { 'content-type': contentType })
    res.end(body)
  } catch {
    res.end(await readFile(resolve(dist, 'index.html')))
  }
})

await mkdir(output, { recursive: true })
await new Promise((done) => server.listen(0, '127.0.0.1', done))
const port = server.address().port
const browser = await chromium.launch({ headless: true })
const records = []
const unmatched = []
const routes = [
  '/', '/inbox', '/opportunities/opportunity-1', '/applications', '/companies',
  '/companies/company-1', '/sources', '/sources/homologation-queue', '/profile',
  '/status', '/missing',
]

for (const width of [320, 360, 768, 1280, 1440]) {
  for (const route of routes) {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    const errors = []
    const consoleErrors = []
    const fixtureResponses = []
    const requests = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })
    page.on('response', (response) => {
      const url = new URL(response.url())
      if (url.pathname.startsWith('/api/')) {
        fixtureResponses.push({ status: response.status(), path: url.pathname })
      }
    })
    page.on('request', (request) => requests.push({
      timestamp: Date.now(),
      method: request.method(),
      path: new URL(request.url()).pathname,
    }))

    await page.route('**/*', (request) => {
      const url = new URL(request.request().url())
      if (url.origin !== `http://127.0.0.1:${port}`) return request.abort()
      if (!url.pathname.startsWith('/api/')) return request.continue()

      const pathname = url.pathname.slice('/api'.length)
      const isClosedApplicationsPage = pathname === '/applications'
        && url.searchParams.get('application_status') === 'CLOSED'
      if (request.request().method() === 'GET' && isClosedApplicationsPage) {
        return request.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 12 }),
        })
      }
      const isProposedSourcesPage = pathname === '/source-health'
        && url.searchParams.get('status') === 'proposed'
      if (request.request().method() === 'GET' && isProposedSourcesPage) {
        return request.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ items: [], total: 0, failing: 0 }),
        })
      }
      if (request.request().method() === 'GET' && Object.hasOwn(fixtures, pathname)) {
        return request.fulfill({
          contentType: 'application/json',
          body: JSON.stringify(fixtures[pathname]),
        })
      }

      unmatched.push({ method: request.request().method(), path: pathname, search: url.search, width, route })
      return request.fulfill({ status: 404, contentType: 'text/plain', body: unmatchedFixtureBody })
    })

    await page.goto(`http://127.0.0.1:${port}${route}`, { waitUntil: 'networkidle' })
    const dom = await page.evaluate(() => ({
      domContentLoaded: performance.getEntriesByType('navigation')[0]?.domContentLoadedEventEnd,
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      text: document.body.innerText.slice(0, 4000),
    }))
    await page.screenshot({
      path: resolve(output, `${width}-${route === '/' ? 'root' : route.slice(1).replaceAll('/', '_')}.png`),
      fullPage: true,
    })
    records.push({ width, route, dom, errors, consoleErrors, fixtureResponses, requests })
    await page.close()
  }
}

await writeFile(resolve(output, 'result.json'), JSON.stringify({ isolated: true, buildIdentity, unmatchedApiRequests: unmatched, records }, null, 2))
await browser.close()
server.close()
