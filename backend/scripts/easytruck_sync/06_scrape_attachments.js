// Stage 6: scrape customer-level Attachments tab metadata (filename/thumbnail URL,
// linked service number, date, private flag). Per user decision: metadata only,
// not downloading/re-hosting the actual files (that's a separate larger task since
// our WorkPhoto schema expects a Cloudinary URL, not an Easy Truck Shop CDN link).
const fs = require('fs');
const path = require('path');
const { loginSession, SHOP, BASE } = require('./lib/auth');

const IDS_FILE = path.join(__dirname, 'data', 'customer_ids.json');
const OUT_FILE = path.join(__dirname, 'data', 'attachments.json');
const FAIL_FILE = path.join(__dirname, 'data', 'attachments_failures.json');

async function scrapeAttachmentsForCustomer(page, customerId) {
  const url = `${BASE}/${SHOP}/customers/${customerId}/attachments`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(400);

  return page.evaluate(() => {
    const imgs = Array.from(document.querySelectorAll('img')).filter(img =>
      !img.src.includes('logo') && !img.src.includes('avatar')
    );
    return imgs.map(img => {
      let card = img.closest('div');
      for (let i = 0; i < 4 && card; i++) {
        if (/Service #|Private|\d{4}/.test(card.textContent)) break;
        card = card.parentElement;
      }
      const text = card ? card.innerText.trim() : '';
      const serviceMatch = text.match(/Service #(\d+)/);
      const dateMatch = text.match(/([A-Z][a-z]{2} \d{1,2}, \d{4})/);
      return {
        thumbnailUrl: img.src,
        isPrivate: text.includes('Private'),
        serviceNumber: serviceMatch ? serviceMatch[1] : null,
        date: dateMatch ? dateMatch[1] : null,
        rawText: text,
      };
    });
  });
}

(async () => {
  const customerIds = JSON.parse(fs.readFileSync(IDS_FILE, 'utf8'));
  console.log(`Loaded ${customerIds.length} customer ids to check for attachments`);

  let results = {};
  if (fs.existsSync(OUT_FILE)) {
    results = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8'));
    console.log(`Resuming: ${Object.keys(results).length} already checked`);
  }
  const failures = fs.existsSync(FAIL_FILE) ? JSON.parse(fs.readFileSync(FAIL_FILE, 'utf8')) : [];

  const { browser, page } = await loginSession({ headless: true });

  let processed = 0;
  for (const cust of customerIds) {
    if (results[cust.id]) continue;
    try {
      const attachments = await scrapeAttachmentsForCustomer(page, cust.id);
      if (attachments.length > 0) {
        results[cust.id] = attachments;
      } else {
        results[cust.id] = [];
      }
    } catch (e) {
      failures.push({ customerId: cust.id, reason: e.message });
    }
    processed++;
    if (processed % 25 === 0) {
      fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
      fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
      const withAttachments = Object.values(results).filter(a => a.length > 0).length;
      console.log(`Checked ${Object.keys(results).length}/${customerIds.length}. With attachments: ${withAttachments}. Failures: ${failures.length}`);
    }
  }

  fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
  fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
  const withAttachments = Object.values(results).filter(a => a.length > 0).length;
  console.log(`DONE. Checked ${Object.keys(results).length}. With attachments: ${withAttachments}. Failures: ${failures.length}`);
  await browser.close();
})();
