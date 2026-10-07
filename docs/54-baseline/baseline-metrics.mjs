/**
 * One-off metrics companion for the SPEC 54 local baseline.
 * Reuses recorded screenshots, timings and requests; only the two 31 s polling
 * observations launch pages. Network requests stay on the static loopback server.
 */
import { createServer } from 'node:http'
import { readFile, readdir, writeFile } from 'node:fs/promises'
import { dirname, extname, relative, resolve, sep } from 'node:path'
import { createHash } from 'node:crypto'
import { gzipSync } from 'node:zlib'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import playwright from '../../tests/e2e/browser/node_modules/playwright/index.js'
import { fixtures, unmatchedFixtureBody } from './fixtures.mjs'

const { chromium } = playwright
const scriptDirectory = resolve(fileURLToPath(new URL('.', import.meta.url)))
const repoRoot = resolve(scriptDirectory, '../..')
const dist = resolve(repoRoot, 'apps/web/dist')
const output = resolve(repoRoot, 'docs/54-baseline/artifacts')
const resultPath = resolve(output, 'result.json')
const result = JSON.parse(await readFile(resultPath, 'utf8'))
if (result.records.some((record) => record.route.includes('__f54primitives'))) {
  throw new Error('Refusing to mix primitive-spike routes into the baseline')
}

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

const distFiles = await listFiles(dist)
const byRelativePath = new Map(distFiles.map((path) => [
  `/${relative(dist, path).split(sep).join('/')}`,
  path,
]))

function capturedAssetIdentity(path) {
  return `/${relative(dist, path).split(sep).join('/')}`
}

const currentRepoSha = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8', cwd: repoRoot }).trim()
const currentBuildIdentity = {
  repoSha: currentRepoSha,
  index: {
    path: '/index.html',
    sha256: sha256(await readFile(resolve(dist, 'index.html'))),
  },
  assets: await Promise.all(distFiles
    .filter((path) => capturedAssetIdentity(path).startsWith('/assets/'))
    .map(async (path) => ({
      path: capturedAssetIdentity(path),
      sha256: sha256(await readFile(path)),
    }))),
}
const sortIdentityAssets = (identity) => identity?.assets
  ?.slice()
  .sort((left, right) => left.path.localeCompare(right.path))
if (!result.buildIdentity) {
  throw new Error('Capture result has no buildIdentity; rerun the isolated baseline harness')
}
const normalizedCapturedIdentity = {
  ...result.buildIdentity,
  assets: sortIdentityAssets(result.buildIdentity),
}
const normalizedCurrentIdentity = {
  ...currentBuildIdentity,
  assets: sortIdentityAssets(currentBuildIdentity),
}
if (JSON.stringify(normalizedCapturedIdentity) !== JSON.stringify(normalizedCurrentIdentity)) {
  throw new Error('Captured build identity does not match current repo SHA, dist index, and complete assets set')
}

const requestedAssets = [...new Set(result.records.flatMap((record) => record.requests)
  .map((request) => request.path)
  .filter((path) => path.startsWith('/assets/')))]
const missingRequestedAssets = requestedAssets.filter((path) => !byRelativePath.has(path))
if (missingRequestedAssets.length) {
  throw new Error(`Capture assets do not match current dist: ${missingRequestedAssets.join(', ')}`)
}

function assetPaths(records) {
  return [...new Set(records.flatMap((record) => record.requests)
    .map((request) => request.path)
    .filter((path) => byRelativePath.has(path)))]
}

async function measureAssets(paths) {
  const files = []
  for (const assetPath of paths) {
    const bytes = await readFile(byRelativePath.get(assetPath))
    const extension = extname(assetPath).toLowerCase()
    const type = extension === '.js' || extension === '.mjs'
      ? 'js'
      : extension === '.css'
        ? 'css'
        : ['.woff', '.woff2', '.ttf', '.otf'].includes(extension)
          ? 'font'
          : 'other'
    files.push({
      path: assetPath,
      type,
      bytes: bytes.byteLength,
      gzipBytes: gzipSync(bytes).byteLength,
      sha256: sha256(bytes),
    })
  }
  return {
    files,
    totals: Object.fromEntries(['js', 'css', 'font', 'other'].map((type) => [
      type,
      files.filter((file) => file.type === type).reduce((total, file) => ({
        bytes: total.bytes + file.bytes,
        gzipBytes: total.gzipBytes + file.gzipBytes,
      }), { bytes: 0, gzipBytes: 0 }),
    ])),
  }
}

const initialRecord = result.records.find((record) => record.width === 1280 && record.route === '/')
if (!initialRecord) throw new Error('Missing initial 1280 px root capture in result.json')
const initialAssets = await measureAssets(assetPaths([initialRecord]))
const totalAssets = await measureAssets(assetPaths(result.records))
const indexBytes = await readFile(resolve(dist, 'index.html'))
const buildIdentity = {
  capture: result.buildIdentity,
  currentDistVerifiedAgainstCapture: true,
  indexSha256: sha256(indexBytes),
  requestedAssets: await measureAssets(requestedAssets),
}

const server = createServer(async (request, response) => {
  const pathname = new URL(request.url, 'http://loopback').pathname
  const file = pathname === '/' ? '/index.html' : pathname
  try {
    const body = await readFile(resolve(dist, `.${file}`))
    const extension = extname(file)
    const contentType = extension === '.js'
      ? 'text/javascript'
      : extension === '.css'
        ? 'text/css'
        : extension === '.woff2'
          ? 'font/woff2'
          : 'text/html'
    response.writeHead(200, { 'content-type': contentType })
    response.end(body)
  } catch {
    response.writeHead(200, { 'content-type': 'text/html' })
    response.end(await readFile(resolve(dist, 'index.html')))
  }
})

await new Promise((done) => server.listen(0, '127.0.0.1', done))
const port = server.address().port
const browser = await chromium.launch({ headless: true })
const browserVersion = browser.version()
const polling = []

async function observePolling(name, route, endpoint) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  const startedAt = Date.now()
  const getRequests = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (request.method() === 'GET' && url.pathname === endpoint) {
      getRequests.push({ at: new Date().toISOString(), elapsedMs: Date.now() - startedAt })
    }
  })
  page.on('pageerror', (error) => getRequests.push({ pageError: error.message }))
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
      return request.fulfill({ contentType: 'application/json', body: JSON.stringify(fixtures[pathname]) })
    }
    return request.fulfill({ status: 404, contentType: 'text/plain', body: unmatchedFixtureBody })
  })

  await page.goto(`http://127.0.0.1:${port}${route}`, { waitUntil: 'networkidle' })
  await new Promise((done) => setTimeout(done, 32_000))
  polling.push({
    name,
    route,
    endpoint,
    observedForMs: Date.now() - startedAt,
    gets: getRequests,
    targetElapsedSeconds: [0, 15, 30].map((target) => ({
      target,
      nearestGet: getRequests
        .filter((request) => typeof request.elapsedMs === 'number')
        .sort((left, right) => Math.abs(left.elapsedMs - target * 1000) - Math.abs(right.elapsedMs - target * 1000))[0] ?? null,
    })),
  })
  await page.close()
}

try {
  await observePolling('Inbox', '/inbox', '/api/inbox')
  await observePolling('Opportunity detail assessment', '/opportunities/opportunity-1', '/api/matches')
} finally {
  await browser.close()
  await new Promise((done) => server.close(done))
}

const npmCommand = resolve(dirname(process.execPath), 'npm.cmd')
const npmVersion = execFileSync('cmd', ['/c', `${npmCommand} --version`], { encoding: 'utf8', cwd: repoRoot }).trim()
const gitSha = currentRepoSha
const metrics = {
  isolated: true,
  generatedAt: new Date().toISOString(),
  gitSha,
  runtime: {
    node: process.version,
    npm: npmVersion,
    platform: `${process.platform}-${process.arch}`,
    osRelease: execFileSync('cmd', ['/c', 'ver'], { encoding: 'utf8' }).trim(),
    playwrightChromium: browserVersion,
  },
  preservedCaptureEvidence: {
    resultPath: 'result.json',
    resultSha256: sha256(await readFile(resultPath)),
    captureCount: result.records.length,
    unmatchedApiRequests: result.unmatchedApiRequests,
    records: result.records.map(({ width, route, dom, errors, consoleErrors, requests }) => ({
      width, route, dom, errors, consoleErrors, requests,
    })),
  },
  assets: {
    initialCapture: { width: initialRecord.width, route: initialRecord.route, ...initialAssets },
    allCapturesUniqueAssets: totalAssets,
    distIndex: {
      path: 'apps/web/dist/index.html',
      bytes: indexBytes.byteLength,
      gzipBytes: gzipSync(indexBytes).byteLength,
      sha256: sha256(indexBytes),
    },
    buildIdentity,
  },
  polling,
}

await writeFile(resolve(output, 'baseline-metrics.json'), JSON.stringify(metrics, null, 2))
process.stdout.write(JSON.stringify({
  gitSha,
  node: metrics.runtime.node,
  npm: metrics.runtime.npm,
  browser: metrics.runtime.playwrightChromium,
  captures: metrics.preservedCaptureEvidence.captureCount,
  polling: polling.map(({ name, observedForMs, gets }) => ({ name, observedForMs, gets })),
  metricsPath: resolve(output, 'baseline-metrics.json'),
}, null, 2) + '\n')
