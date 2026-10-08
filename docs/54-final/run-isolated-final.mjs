/**
 * Final local visual evidence for SPEC 54.
 *
 * It serves the already-built web dist over loopback, supplies every API response
 * from the read-only baseline fixtures, and never starts Vite, Docker, or a backend.
 */
import { createServer } from 'node:http'
import { readFile, mkdir, writeFile, readdir } from 'node:fs/promises'
import { resolve, extname, relative, sep } from 'node:path'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import playwright from '../../tests/e2e/browser/node_modules/playwright/index.js'
import { fixtures, unmatchedFixtureBody } from '../54-baseline/fixtures.mjs'

const { chromium } = playwright
const scriptDirectory = resolve(fileURLToPath(new URL('.', import.meta.url)))
const repoRoot = resolve(scriptDirectory, '../..')
const dist = resolve(repoRoot, 'apps/web/dist')
const output = resolve(scriptDirectory, 'screenshots')
const resultPath = resolve(scriptDirectory, 'result.json')
const routes = [
  '/', '/inbox', '/opportunities/opportunity-1', '/applications', '/companies',
  '/companies/company-1', '/sources', '/sources/homologation-queue', '/profile',
  '/status', '/missing',
]
const expectedRouteContent = {
  '/': 'O que move sua busca esta semana?',
  '/inbox': 'Quais vagas merecem sua atenção agora?',
  '/opportunities/opportunity-1': 'A análise de IA é apoio, não decide por você.',
  '/applications': 'Organize a próxima ação em cada etapa da sua busca.',
  '/companies': 'Consulte as empresas monitoradas e as fontes associadas a cada uma.',
  '/companies/company-1': 'Registre ou corrija o ATS da empresa e proponha a fonte a partir dele.',
  '/sources': 'O que cada fonte produziu na última execução, e o que fazer quando ela falha.',
  '/sources/homologation-queue': 'Teste, revise os termos e habilite as propostas em sequência, sem abrir fonte por fonte.',
  '/profile': 'O que o matching considera ao avaliar uma vaga.',
  '/status': 'A base local está conectada. O catálogo de empresas já pode ser importado e consultado no dashboard.',
  '/missing': 'O que move sua busca esta semana?',
}
const widths = [320, 360, 768, 1280, 1440]

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

function screenshotName(width, route) {
  return `${width}-${route === '/' ? 'root' : route.slice(1).replaceAll('/', '_')}.png`
}

async function staticBody(pathname) {
  const file = pathname === '/' ? '/index.html' : pathname
  try {
    return { body: await readFile(resolve(dist, `.${file}`)), extension: extname(file) }
  } catch {
    return { body: await readFile(resolve(dist, 'index.html')), extension: '.html' }
  }
}

const repoSha = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8', cwd: repoRoot }).trim()
const distFiles = await listFiles(dist)
const buildIdentity = {
  repoSha,
  index: {
    path: '/index.html',
    sha256: sha256(await readFile(resolve(dist, 'index.html'))),
  },
  assets: await Promise.all(distFiles
    .filter((path) => relative(dist, path).split(sep).join('/').startsWith('assets/'))
    .map(async (path) => ({
      path: `/${relative(dist, path).split(sep).join('/')}`,
      sha256: sha256(await readFile(path)),
    }))),
}

await mkdir(output, { recursive: true })
const server = createServer(async (request, response) => {
  const { body, extension } = await staticBody(new URL(request.url, 'http://loopback').pathname)
  const contentType = extension === '.js'
    ? 'text/javascript'
    : extension === '.css'
      ? 'text/css'
      : extension === '.woff2'
        ? 'font/woff2'
        : 'text/html'
  response.writeHead(200, { 'content-type': contentType })
  response.end(body)
})

await new Promise((done) => server.listen(0, '127.0.0.1', done))
const port = server.address().port
const origin = `http://127.0.0.1:${port}`
const browser = await chromium.launch({ headless: true })
const unmatchedApiRequests = []
const records = []

try {
  for (const width of widths) {
    for (const route of routes) {
      const page = await browser.newPage({ viewport: { width, height: 900 } })
      const pageErrors = []
      const consoleErrors = []
      const apiResponses = []
      const externalRequests = []
      page.on('pageerror', (error) => pageErrors.push(error.message))
      page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
      })
      page.on('response', (response) => {
        const responseUrl = new URL(response.url())
        if (responseUrl.pathname.startsWith('/api/')) {
          apiResponses.push({ path: responseUrl.pathname, status: response.status() })
        }
      })
      await page.route('**/*', (intercepted) => {
        const requestUrl = new URL(intercepted.request().url())
        if (requestUrl.origin !== origin) {
          externalRequests.push(requestUrl.toString())
          return intercepted.abort()
        }
        if (!requestUrl.pathname.startsWith('/api/')) return intercepted.continue()

        const pathname = requestUrl.pathname.slice('/api'.length)
        const isClosedApplications = pathname === '/applications'
          && requestUrl.searchParams.get('application_status') === 'CLOSED'
        if (intercepted.request().method() === 'GET' && isClosedApplications) {
          return intercepted.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 12 }) })
        }
        const isProposedSources = pathname === '/source-health'
          && requestUrl.searchParams.get('status') === 'proposed'
        if (intercepted.request().method() === 'GET' && isProposedSources) {
          return intercepted.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [], total: 0, failing: 0 }) })
        }
        if (intercepted.request().method() === 'GET' && Object.hasOwn(fixtures, pathname)) {
          return intercepted.fulfill({ contentType: 'application/json', body: JSON.stringify(fixtures[pathname]) })
        }
        unmatchedApiRequests.push({ width, route, method: intercepted.request().method(), path: pathname, search: requestUrl.search })
        return intercepted.fulfill({ status: 404, contentType: 'text/plain', body: unmatchedFixtureBody })
      })

      const navigation = await page.goto(`${origin}${route}`, { waitUntil: 'networkidle' })
      const dom = await page.evaluate(() => ({
        path: window.location.pathname,
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        text: document.body.innerText.slice(0, 4000),
      }))
      const expectedText = expectedRouteContent[route]
      const routeContentAssertion = {
        name: `routeContent:${route}`,
        expectedText,
        passed: dom.text.includes(expectedText),
      }
      await page.screenshot({ path: resolve(output, screenshotName(width, route)), fullPage: true })
      records.push({
        width,
        route,
        directUrl: `${origin}${route}`,
        navigationStatus: navigation?.status() ?? null,
        dom,
        routeContentAssertion,
        pageErrors,
        consoleErrors,
        apiResponses,
        externalRequests,
      })
      await page.close()
    }
  }
} finally {
  await browser.close()
  await new Promise((done) => server.close(done))
}

const assertions = {
  expectedCaptures: routes.length * widths.length,
  captures: records.length,
  directUrls: records.every((record) => record.navigationStatus === 200 && record.dom.path === record.route),
  routeContentFailures: records
    .filter((record) => !record.routeContentAssertion.passed)
    .map(({ width, route, routeContentAssertion }) => ({ width, route, ...routeContentAssertion })),
  horizontalOverflow: records.filter((record) => record.dom.overflow).map(({ width, route }) => ({ width, route })),
  pageErrors: records.flatMap(({ width, route, pageErrors }) => pageErrors.map((message) => ({ width, route, message }))),
  consoleErrors: records.flatMap(({ width, route, consoleErrors }) => consoleErrors.map((message) => ({ width, route, message }))),
  externalRequests: records.flatMap(({ width, route, externalRequests }) => externalRequests.map((url) => ({ width, route, url }))),
  unmatchedApiRequests,
  non2xxFixtureResponses: records.flatMap(({ width, route, apiResponses }) => apiResponses
    .filter((response) => response.status < 200 || response.status >= 300)
    .map((response) => ({ width, route, ...response }))),
}
const failedAssertions = [
  assertions.captures !== assertions.expectedCaptures && `expected ${assertions.expectedCaptures} captures, got ${assertions.captures}`,
  !assertions.directUrls && 'a direct URL did not load with status 200 and its requested pathname',
  assertions.routeContentFailures.length && 'route-specific visible content assertions failed',
  assertions.horizontalOverflow.length && 'horizontal overflow detected',
  assertions.pageErrors.length && 'page errors detected',
  assertions.consoleErrors.length && 'console errors detected',
  assertions.externalRequests.length && 'external requests detected',
  assertions.unmatchedApiRequests.length && 'unmatched API requests detected',
  assertions.non2xxFixtureResponses.length && 'non-2xx fixture responses detected',
].filter(Boolean)

const result = {
  isolated: true,
  generatedAt: new Date().toISOString(),
  buildIdentity,
  routes,
  expectedRouteContent,
  widths,
  assertions,
  failedAssertions,
  records,
}
await writeFile(resultPath, JSON.stringify(result, null, 2))
if (failedAssertions.length) throw new Error(`Final visual evidence failed: ${failedAssertions.join('; ')}`)
process.stdout.write(JSON.stringify({
  resultPath: relative(repoRoot, resultPath).split(sep).join('/'),
  buildIdentity,
  assertions,
}, null, 2) + '\n')
