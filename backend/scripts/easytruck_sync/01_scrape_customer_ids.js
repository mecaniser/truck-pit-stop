// Stage 1: collect all customer IDs + basic list-view fields (fast, list pages only)
const fs = require('fs');
const path = require('path');
const { loginSession, SHOP, BASE } = require('./lib/auth');

const OUT_FILE = path.join(__dirname, 'data', 'customer_ids.json');
const FAIL_FILE = path.join(__dirname, 'data', 'customer_ids_failures.json');

(async () => {
  const { browser, page } = await loginSession({ headless: true });

  let results = [];
  if (fs.existsSync(OUT_FILE)) {
    results = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8'));
    console.log(`Resuming: ${results.length} already collected`);
  }
  const seen = new Set(results.map(r => r.id));
  const failures = [];

  const listUrl = `${BASE}/${SHOP}/customers`;
  await page.goto(listUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const bodyText = await page.locator('body').innerText();
  const totalMatch = bodyText.match(/Showing \d+ to \d+ of ([\d,]+) results/);
  const total = totalMatch ? parseInt(totalMatch[1].replace(/,/g, ''), 10) : null;
  const perPage = 50;
  const totalPages = total ? Math.ceil(total / perPage) : 1;
  console.log(`Total customers: ${total}, pages: ${totalPages}`);

  for (let p = 1; p <= totalPages; p++) {
    const url = p === 1 ? listUrl : `${listUrl}?page=${p}`;
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const rowCount = await page.locator('table tbody tr').count();
    let pageFailures = 0;

    for (let i = 0; i < rowCount; i++) {
      let cells, company;
      try {
        await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
        await page.waitForTimeout(400);
        const row = page.locator('table tbody tr').nth(i);
        cells = await row.locator('td').allInnerTexts();
        company = cells[0];

        const urlBefore = page.url();
        await row.locator('td').first().click();
        // robust wait: poll page.url() instead of relying solely on waitForURL
        let id = null;
        for (let attempt = 0; attempt < 20; attempt++) {
          const m = page.url().match(/\/customers\/(\d+)$/);
          if (m) { id = m[1]; break; }
          await page.waitForTimeout(300);
        }

        if (!id) {
          pageFailures++;
          failures.push({ page: p, row: i, company, reason: 'no id after click+poll', urlAfter: page.url() });
          continue;
        }
        if (seen.has(id)) continue;

        const [, usdot, contact, balance, units, group] = cells;
        results.push({ id, company, usdot, balance, units, group });
        seen.add(id);
      } catch (e) {
        pageFailures++;
        failures.push({ page: p, row: i, company: company || '?', reason: e.message });
      }
    }
    fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
    fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
    console.log(`Page ${p}/${totalPages} done. Total so far: ${results.length}. Failures this page: ${pageFailures}`);
  }

  console.log('DONE. Total customer IDs collected:', results.length, 'Failures:', failures.length);
  await browser.close();
})();
