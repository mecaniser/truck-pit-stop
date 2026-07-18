// Stage 7: scrape MC Number (from the customer edit form) and QuickBooks link
// status (from the customer detail page) for all 506 imported customers.
const fs = require('fs');
const path = require('path');
const { loginSession, SHOP, BASE } = require('./lib/auth');

const IDS_FILE = path.join(__dirname, 'data', 'customer_ids.json');
const OUT_FILE = path.join(__dirname, 'data', 'mc_qb.json');
const FAIL_FILE = path.join(__dirname, 'data', 'mc_qb_failures.json');

async function scrapeMcNumber(page, customerId) {
  await page.goto(`${BASE}/${SHOP}/customers/${customerId}/edit`, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(400);
  return page.evaluate(() => {
    const labels = Array.from(document.querySelectorAll('label'));
    const mcLabel = labels.find(l => l.textContent.trim() === 'MC Number');
    if (!mcLabel) return null;
    let container = mcLabel.closest('div');
    let depth = 0;
    while (container && !container.querySelector('input, textarea') && depth < 5) {
      container = container.parentElement;
      depth++;
    }
    const input = container ? container.querySelector('input, textarea') : null;
    return input ? input.value.trim() || null : null;
  });
}

async function scrapeQuickbooksStatus(page, customerId) {
  await page.goto(`${BASE}/${SHOP}/customers/${customerId}`, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(400);
  const text = await page.locator('body').innerText();
  const idx = text.indexOf('QUICKBOOKS');
  if (idx === -1) return null;
  const after = text.slice(idx + 'QUICKBOOKS'.length, idx + 60).trim();
  const firstLine = after.split('\n')[0].trim();
  return firstLine || null;
}

(async () => {
  const customerIds = JSON.parse(fs.readFileSync(IDS_FILE, 'utf8'));
  console.log(`Loaded ${customerIds.length} customer ids to process`);

  let results = {};
  if (fs.existsSync(OUT_FILE)) {
    results = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8'));
    console.log(`Resuming: ${Object.keys(results).length} already scraped`);
  }
  const failures = fs.existsSync(FAIL_FILE) ? JSON.parse(fs.readFileSync(FAIL_FILE, 'utf8')) : [];

  const { browser, page } = await loginSession({ headless: true });

  let processed = 0;
  for (const cust of customerIds) {
    if (results[cust.id]) continue;
    try {
      const mcNumber = await scrapeMcNumber(page, cust.id);
      const qbStatus = await scrapeQuickbooksStatus(page, cust.id);
      results[cust.id] = { mcNumber, qbStatus };
    } catch (e) {
      failures.push({ customerId: cust.id, reason: e.message });
    }
    processed++;
    if (processed % 20 === 0) {
      fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
      fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
      console.log(`Processed ${Object.keys(results).length}/${customerIds.length}. Failures: ${failures.length}`);
    }
  }

  fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
  fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
  console.log(`DONE. Total: ${Object.keys(results).length}. Failures: ${failures.length}`);
  await browser.close();
})();
