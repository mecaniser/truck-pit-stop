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

  // IMPORTANT: use a stable sort. The unsorted /customers list reorders rows
  // between page loads (pagination instability), which caused a re-navigate-
  // per-row scraper like this one to revisit the same customers and never reach
  // others (311 of 542 collected). Sorting by name pins the order.
  const listUrl = `${BASE}/${SHOP}/customers?sort=name&direction=asc`;
  await page.goto(listUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const bodyText = await page.locator('body').innerText();
  const totalMatch = bodyText.match(/Showing \d+ to \d+ of ([\d,]+) results/);
  const total = totalMatch ? parseInt(totalMatch[1].replace(/,/g, ''), 10) : null;
  const perPage = 50;
  const totalPages = total ? Math.ceil(total / perPage) : 1;
  console.log(`Total customers: ${total}, pages: ${totalPages}`);

  for (let p = 1; p <= totalPages; p++) {
    const url = `${listUrl}&page=${p}`;
    let pageFailures = 0;

    // Load the page once and read every row's customer id straight from its
    // <tr id="row-{customerId}"> attribute + the row cell text. No per-row
    // clicking, so no navigation races and ~50x fewer page loads. Retry the
    // page load a few times to ride out transient network hiccups.
    let rows = null;
    for (let attempt = 0; attempt < 3 && rows === null; attempt++) {
      try {
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(500);
        rows = await page.locator('table tbody tr').evaluateAll(trs =>
          trs.map(tr => {
            const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
            const m = (tr.id || '').match(/row-(\d+)/);
            return { id: m ? m[1] : null, cells };
          })
        );
      } catch (e) {
        if (attempt === 2) { failures.push({ page: p, reason: `page load failed: ${e.message}` }); rows = []; }
        else await page.waitForTimeout(1500);
      }
    }

    for (const { id, cells } of rows) {
      const company = cells[0];
      if (!id) {
        pageFailures++;
        failures.push({ page: p, company, reason: 'no row-{id} attribute' });
        continue;
      }
      if (seen.has(id)) continue;
      const [, usdot, contact, balance, units, group] = cells;
      results.push({ id, company, usdot, balance, units, group });
      seen.add(id);
    }
    fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
    fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
    console.log(`Page ${p}/${totalPages} done. Total so far: ${results.length}. Failures this page: ${pageFailures}`);
  }

  console.log('DONE. Total customer IDs collected:', results.length, 'Failures:', failures.length);
  await browser.close();
})();
