const fs = require('fs');
const path = require('path');
const { chromium } = require('../../tests/e2e/browser/node_modules/playwright');

(async () => {
  const root = __dirname;
  const out = path.join(root, 'screenshots');
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const report = [];
  const errors = [];
  const attachErrorCollection = (page) => {
    page.on('pageerror', (error) => errors.push({ type: 'pageerror', message: error.message }));
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push({ type: 'console', message: message.text() });
    });
  };
  for (const pageName of ['inbox', 'detail', 'pipeline', 'overview']) {
    for (const [label, width, height] of [['1440', 1440, 1100], ['768', 768, 1100], ['360', 360, 900]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      attachErrorCollection(page);
      await page.goto(`http://127.0.0.1:54154/${pageName}.html`, { waitUntil: 'domcontentloaded' });
      await page.evaluate(() => document.fonts.ready);
      const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
      await page.screenshot({ path: path.join(out, `${pageName}-${label}.png`), fullPage: true });
      report.push({ page: pageName, viewport: label, overflow: dimensions.scrollWidth > dimensions.clientWidth, ...dimensions });
      await page.close();
    }
  }
  for (const pageName of ['inbox', 'detail', 'pipeline', 'overview']) {
    for (const state of ['loading', 'empty', 'error', 'partial']) {
      for (const [label, width, height] of [['1440', 1440, 1100], ['360', 360, 900]]) {
        const page = await browser.newPage({ viewport: { width, height } });
        attachErrorCollection(page);
        await page.goto(`http://127.0.0.1:54154/${pageName}.html`, { waitUntil: 'domcontentloaded' });
        await page.selectOption('[data-state]', state);
        const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
        await page.screenshot({ path: path.join(out, `${pageName}-${state}-${label}.png`), fullPage: true });
        report.push({ page: pageName, viewport: label, state, overflow: dimensions.scrollWidth > dimensions.clientWidth, ...dimensions });
        await page.close();
      }
    }
  }
  const interactionPage = await browser.newPage({ viewport: { width: 360, height: 900 } });
  attachErrorCollection(interactionPage);
  await interactionPage.goto('http://127.0.0.1:54154/inbox.html', { waitUntil: 'domcontentloaded' });
  await interactionPage.locator('[data-menu]').click();
  await interactionPage.keyboard.press('Escape');
  const keyboardMenu = await interactionPage.evaluate(() => ({
    expanded: document.querySelector('[data-menu]').getAttribute('aria-expanded'),
    drawerHidden: document.querySelector('#mobile-drawer').hidden,
    focusReturned: document.activeElement === document.querySelector('[data-menu]'),
  }));
  const zoom200 = await interactionPage.evaluate(() => {
    document.body.style.zoom = '2';
    const result = {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    };
    document.body.style.zoom = '';
    return { ...result, overflow: result.scrollWidth > result.clientWidth };
  });
  await interactionPage.close();
  fs.writeFileSync(path.join(out, 'capture-report.json'), JSON.stringify(report, null, 2));
  fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify({
    javascriptErrors: errors,
    keyboardMenu,
    zoom200,
  }, null, 2));
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
})().catch((error) => { console.error(error); process.exitCode = 1; });
