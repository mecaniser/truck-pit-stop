// Stage 5: scrape the Invoice tab for every unique service number, giving us
// Invoice (fees, tax, discount, total) and Payment (amount/date/method) data.
const fs = require('fs');
const path = require('path');
const { loginSession, SHOP, BASE } = require('./lib/auth');
const { parseInvoicePage } = require('./lib/invoice_parse');

const CUSTOMER_DETAILS_FILE = path.join(__dirname, 'data', 'customer_details.json');
const OUT_FILE = path.join(__dirname, 'data', 'invoices.json');
const FAIL_FILE = path.join(__dirname, 'data', 'invoices_failures.json');

function getAllServiceNumbers() {
  const data = JSON.parse(fs.readFileSync(CUSTOMER_DETAILS_FILE, 'utf8'));
  const nums = new Set();
  data.forEach(c => (c.vehicles || []).forEach(v => (v.serviceHistory || []).forEach(row => {
    if (row[0] && row[0] !== 'No results') nums.add(row[0].replace('#', '').trim());
  })));
  return Array.from(nums);
}

(async () => {
  const serviceNumbers = getAllServiceNumbers();
  console.log(`Found ${serviceNumbers.length} unique service numbers to scrape`);

  let results = {};
  if (fs.existsSync(OUT_FILE)) {
    results = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8'));
    console.log(`Resuming: ${Object.keys(results).length} already scraped`);
  }
  const failures = fs.existsSync(FAIL_FILE) ? JSON.parse(fs.readFileSync(FAIL_FILE, 'utf8')) : [];

  const { browser, page } = await loginSession({ headless: true });

  let processed = 0;
  for (const serviceNo of serviceNumbers) {
    if (results[serviceNo]) continue;
    try {
      await page.goto(`${BASE}/${SHOP}/services/${serviceNo}/invoice`, { waitUntil: 'networkidle', timeout: 20000 });
      await page.waitForTimeout(400);
      const text = await page.locator('body').innerText();
      results[serviceNo] = parseInvoicePage(text);
    } catch (e) {
      failures.push({ serviceNo, reason: e.message });
    }
    processed++;
    if (processed % 20 === 0) {
      fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
      fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
      console.log(`Processed ${Object.keys(results).length}/${serviceNumbers.length}. Failures: ${failures.length}`);
    }
  }

  fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
  fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
  console.log(`DONE. Total: ${Object.keys(results).length}. Failures: ${failures.length}`);
  await browser.close();
})();
