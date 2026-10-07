const fs = require('fs');
const path = require('path');
const http = require('http');
const net = require('net');
const { spawn } = require('child_process');
const { chromium } = require('../../tests/e2e/browser/node_modules/playwright');

const HOST = '127.0.0.1';
const PORT = 54154;
const ORIGIN = `http://${HOST}:${PORT}`;
const PAGES = ['inbox', 'detail', 'pipeline', 'overview'];
const STATES = ['loading', 'empty', 'error', 'partial'];

const failures = [];
const fail = (message) => failures.push(message);
const check = (condition, message) => { if (!condition) fail(message); return Boolean(condition); };

const portInUse = () => new Promise((resolve) => {
  const socket = net.connect({ host: HOST, port: PORT });
  socket.once('connect', () => { socket.destroy(); resolve(true); });
  socket.once('error', () => resolve(false));
});

const probe = () => new Promise((resolve) => {
  const request = http.get(`${ORIGIN}/inbox.html`, (response) => { response.resume(); resolve(response.statusCode === 200); });
  request.once('error', () => resolve(false));
  request.setTimeout(1000, () => { request.destroy(); resolve(false); });
});

// The runner owns its server so it never depends on a stale or external process.
async function startServer() {
  if (await portInUse()) throw new Error(`Port ${PORT} is already in use; stop the other process so the runner can serve the current files.`);
  const child = spawn(process.execPath, [path.join(__dirname, 'serve-local.mjs')], { env: { ...process.env, PORT: String(PORT) }, stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  let exited = false;
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  child.once('exit', () => { exited = true; });
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    if (exited) throw new Error(`Local server exited before becoming ready: ${stderr.trim()}`);
    if (await probe()) return child;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  child.kill();
  throw new Error('Local server did not respond on loopback within 10s.');
}

(async () => {
  const root = __dirname;
  const out = path.join(root, 'screenshots');
  fs.mkdirSync(out, { recursive: true });
  const server = await startServer();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const report = [];
    const errors = [];
    const blockedRequests = [];
    const newPage = async (width, height) => {
      const context = await browser.newContext({ viewport: { width, height } });
      // Registered before any navigation: anything outside the loopback origin is blocked and recorded.
      await context.route('**/*', (route) => {
        const url = route.request().url();
        if (url.startsWith(`${ORIGIN}/`)) return route.continue();
        blockedRequests.push(url);
        return route.abort();
      });
      const page = await context.newPage();
      page.on('pageerror', (error) => errors.push({ type: 'pageerror', message: error.message }));
      page.on('console', (message) => { if (message.type() === 'error') errors.push({ type: 'console', message: message.text() }); });
      return page;
    };
    const measure = (page) => page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
    const open = async (page, pageName) => {
      await page.goto(`${ORIGIN}/${pageName}.html`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-state]', { timeout: 5000 });
      await page.evaluate(() => document.fonts.ready);
    };

    const stateChecks = [];
    const tableChecks = [];
    const pipelineChecks = [];
    const detailChecks = [];

    for (const pageName of PAGES) {
      const viewports = [['1440', 1440, 1100], ['768', 768, 1100], ['360', 360, 900]];
      if (pageName === 'pipeline') viewports.splice(1, 0, ['1280', 1280, 1000]);
      for (const [label, width, height] of viewports) {
        const page = await newPage(width, height);
        await open(page, pageName);
        const dimensions = await measure(page);
        await page.screenshot({ path: path.join(out, `${pageName}-${label}.png`), fullPage: true });
        const overflow = dimensions.scrollWidth > dimensions.clientWidth;
        check(!overflow, `Horizontal overflow on ${pageName} at ${label}: ${dimensions.scrollWidth} > ${dimensions.clientWidth}`);
        report.push({ page: pageName, viewport: label, overflow, ...dimensions });
        if (pageName === 'inbox' && label !== '1440') {
          const columnHeaders = await page.getByRole('columnheader').count();
          const rows = await page.getByRole('row').count();
          const cells = await page.getByRole('cell').count();
          const result = { viewport: label, columnHeaders, rows, cells };
          tableChecks.push(result);
          check(columnHeaders === 5, `Inbox at ${label}: expected 5 columnheader roles, found ${columnHeaders}`);
          check(rows === 4, `Inbox at ${label}: expected 4 row roles (header + 3), found ${rows}`);
          check(cells === 15, `Inbox at ${label}: expected 15 cell roles, found ${cells}`);
        }
        if (pageName === 'pipeline' && ['1440', '1280'].includes(label)) {
          const board = await page.evaluate(() => {
            const el = document.querySelector('.pipeline-board');
            const headings = [...el.querySelectorAll('.stage h2')].map((h) => { const r = h.getBoundingClientRect(); const style = getComputedStyle(h); return { text: h.textContent.replace(/s+/g, ' ').trim(), left: r.left, right: r.right, visible: r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' }; });
            return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth, headings };
          });
          const result = { viewport: label, ...board };
          pipelineChecks.push(result);
          check(board.scrollWidth <= board.clientWidth, `Pipeline at ${label}: board has internal horizontal overflow (${board.scrollWidth} > ${board.clientWidth})`);
          check(board.headings.length === 7 && board.headings.every((h) => h.visible && h.left >= 0 && h.right <= width), `Pipeline at ${label}: all 7 stage headings must be visible within ${width}px: ${JSON.stringify(board.headings)}`);
        }
        if (pageName === 'detail' && label !== '1440') {
          const order = await page.evaluate(() => {
            const title = document.querySelector('.detail-title').getBoundingClientRect();
            const decisionEl = document.querySelector('aside.decision');
            const decision = decisionEl.getBoundingClientRect();
            const sectionEl = [...document.querySelectorAll('.detail-main .section')].find((el) => el.querySelector('h2') && el.querySelector('h2').textContent.trim() === 'O que a vaga pede');
            const section = sectionEl.getBoundingClientRect();
            return { titleBottom: title.bottom, decisionTop: decision.top, sectionTop: section.top, domPrecedes: Boolean(decisionEl.compareDocumentPosition(sectionEl) & Node.DOCUMENT_POSITION_FOLLOWING) };
          });
          detailChecks.push({ viewport: label, ...order });
          check(order.decisionTop >= order.titleBottom - 1 && order.decisionTop < order.sectionTop, `Detail at ${label}: decision panel must sit below the title block and above 'O que a vaga pede' (${JSON.stringify(order)})`);
          check(order.domPrecedes, `Detail at ${label}: decision panel must precede 'O que a vaga pede' in DOM order`);
        }
        await page.context().close();
      }
    }

    for (const pageName of PAGES) {
      for (const state of STATES) {
        for (const [label, width, height] of [['1440', 1440, 1100], ['360', 360, 900]]) {
          const page = await newPage(width, height);
          await open(page, pageName);
          await page.selectOption('[data-state]', state);
          const dimensions = await measure(page);
          await page.screenshot({ path: path.join(out, `${pageName}-${state}-${label}.png`), fullPage: true });
          const overflow = dimensions.scrollWidth > dimensions.clientWidth;
          check(!overflow, `Horizontal overflow on ${pageName}/${state} at ${label}: ${dimensions.scrollWidth} > ${dimensions.clientWidth}`);
          report.push({ page: pageName, viewport: label, state, overflow, ...dimensions });
          const panel = page.locator('[data-state-panel]');
          const panelVisible = await panel.isVisible();
          const heading = (await panel.locator('h2').first().textContent({ timeout: 2000 }).catch(() => '')) || '';
          const result = { page: pageName, viewport: label, state, panelVisible, heading: heading.trim() };
          if (!check(panelVisible && heading.trim() !== '', `State ${state} on ${pageName} at ${label}: panel visible=${panelVisible}, heading="${heading.trim()}"`)) { stateChecks.push(result); await page.context().close(); continue; }
          if (pageName === 'detail' && state === 'partial') {
            const warningVisible = await page.locator('[data-ai-warning]').isVisible();
            result.aiWarningVisible = warningVisible;
            check(warningVisible, `Detail partial at ${label}: AI warning notice must be visible`);
          }
          if (state === 'error') {
            const retry = page.getByRole('button', { name: 'Tentar novamente' });
            result.retryButtons = await retry.count();
            if (check(result.retryButtons === 1, `State error on ${pageName} at ${label}: expected 1 "Tentar novamente" button, found ${result.retryButtons}`)) {
              await retry.click();
              result.panelHiddenAfterRetry = !(await panel.isVisible());
              result.selectValueAfterRetry = await page.locator('[data-state]').inputValue();
              result.contentVisibleAfterRetry = await page.locator('main h1, .page-head h1, .detail-title h1').first().isVisible();
              check(result.panelHiddenAfterRetry && result.selectValueAfterRetry === 'default' && result.contentVisibleAfterRetry,
                `State error retry on ${pageName} at ${label}: did not return to default (panelHidden=${result.panelHiddenAfterRetry}, select=${result.selectValueAfterRetry}, contentVisible=${result.contentVisibleAfterRetry})`);
            }
          }
          stateChecks.push(result);
          await page.context().close();
        }
      }
    }

    const interactionPage = await newPage(360, 900);
    await open(interactionPage, 'inbox');
    const menuButton = interactionPage.locator('[data-menu]');
    const drawer = interactionPage.locator('#mobile-drawer');
    await menuButton.click();
    const afterClick = { drawerVisible: await drawer.isVisible(), expanded: await menuButton.getAttribute('aria-expanded') };
    await interactionPage.keyboard.press('Escape');
    const afterEscape = {
      drawerHidden: await drawer.isHidden(),
      expanded: await menuButton.getAttribute('aria-expanded'),
      focusReturned: await interactionPage.evaluate(() => document.activeElement === document.querySelector('[data-menu]')),
    };
    check(afterClick.drawerVisible && afterClick.expanded === 'true', `Mobile menu after click: ${JSON.stringify(afterClick)}`);
    check(afterEscape.drawerHidden && afterEscape.expanded === 'false' && afterEscape.focusReturned, `Mobile menu after Escape: ${JSON.stringify(afterEscape)}`);

    // Non-assertion: CSS "zoom: 2" on body is not real browser zoom and does not validate WCAG reflow.
    const cssZoom2Measurement = await interactionPage.evaluate(() => {
      document.body.style.zoom = '2';
      const result = { scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth };
      document.body.style.zoom = '';
      return { ...result, overflow: result.scrollWidth > result.clientWidth };
    });
    await interactionPage.context().close();

    check(blockedRequests.length === 0, `Requests outside ${ORIGIN} were attempted: ${blockedRequests.join(', ')}`);
    check(errors.length === 0, `JavaScript/console errors: ${JSON.stringify(errors)}`);

    fs.writeFileSync(path.join(out, 'capture-report.json'), JSON.stringify(report, null, 2));
    fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify({
      passed: failures.length === 0,
      failures,
      captures: report.length,
      javascriptErrors: errors,
      blockedExternalRequests: blockedRequests,
      keyboardMenu: { afterClick, afterEscape },
      inboxTableRoles: tableChecks,
      pipelineBoardChecks: pipelineChecks,
      detailDecisionOrderChecks: detailChecks,
      stateChecks,
      cssZoom2MeasurementNonAssertion: { note: 'CSS body zoom:2 is NOT real browser zoom; recorded for information only and not asserted.', ...cssZoom2Measurement },
    }, null, 2));
    console.log(`captures: ${report.length}; state checks: ${stateChecks.length}; inbox table role checks: ${JSON.stringify(tableChecks)}; pipeline board checks: ${pipelineChecks.map((c) => c.viewport + ':' + c.scrollWidth + '/' + c.clientWidth).join(',')}; detail decision order checks: ${detailChecks.length}`);
    if (failures.length) {
      console.error(`FAILED: ${failures.length} assertion(s) violated`);
      failures.forEach((message) => console.error(` - ${message}`));
      process.exitCode = 1;
    } else {
      console.log('PASSED: all assertions satisfied');
    }
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
