// Stage 3: for each unique service number (repair order), scrape its Parts tab
// to get itemized parts used (part#, description, qty, cost, price, vendor, status),
// grouped by service line item.
const fs = require('fs');
const path = require('path');
const { loginSession, SHOP, BASE } = require('./lib/auth');

const CUSTOMER_DETAILS_FILE = path.join(__dirname, 'data', 'customer_details.json');
const OUT_FILE = path.join(__dirname, 'data', 'parts_usage.json');
const FAIL_FILE = path.join(__dirname, 'data', 'parts_usage_failures.json');

function getAllServiceNumbers() {
  const data = JSON.parse(fs.readFileSync(CUSTOMER_DETAILS_FILE, 'utf8'));
  const nums = new Set();
  data.forEach(c => (c.vehicles || []).forEach(v => (v.serviceHistory || []).forEach(row => {
    if (row[0] && row[0] !== 'No results') nums.add(row[0].replace('#', '').trim());
  })));
  return Array.from(nums);
}

async function scrapePartsForService(page, serviceNo) {
  const url = `${BASE}/${SHOP}/services/${serviceNo}/parts`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(400);

  // The page has one parts table per service line item, each preceded by the
  // line-item name as plain text. We need to associate each parts row with its
  // line-item group. Grab the full body structure via DOM walk.
  const groups = await page.evaluate(() => {
    const result = [];
    const tables = Array.from(document.querySelectorAll('table'));
    tables.forEach(table => {
      // find nearest preceding heading-like sibling text (the line item name)
      let el = table.previousElementSibling;
      let lineItemName = null;
      let depth = 0;
      while (el && depth < 10 && !lineItemName) {
        const t = el.textContent.trim();
        if (t && t.length < 100 && !t.includes('PART')) lineItemName = t;
        el = el.previousElementSibling;
        depth++;
      }
      const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr =>
        Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())
      );
      result.push({ lineItemName, rows });
    });
    return result;
  });

  return groups;
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
      const groups = await scrapePartsForService(page, serviceNo);
      results[serviceNo] = groups;
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
