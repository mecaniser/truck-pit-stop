// Stage 4: scrape the parts/inventory catalog with named fields + part images.
//
// List columns (confirmed via recon), after the leading checkbox cell:
//   PART (part# + description, two lines) | CROSS | VENDOR | LOCATION |
//   STOCK (e.g. "16 ea.") | COST ($) | PRICE ($, may have discount %) |
//   LAST SOLD (date) | NOTES
//
// Uses a stable sort (?sort=-part) to avoid the pagination-instability bug we
// hit with the unsorted customers list. For each part we also open its detail
// page and pull any image URL (cdn.easytruck.shop), so the importer can
// re-host it. Resumable: re-running skips parts already saved.
const fs = require('fs');
const path = require('path');
const { loginSession, SHOP, BASE } = require('./lib/auth');

const OUT_FILE = path.join(__dirname, 'data', 'parts_inventory.json');
const FAIL_FILE = path.join(__dirname, 'data', 'parts_inventory_failures.json');

function parseStock(s) {
  const m = (s || '').match(/([\d,]+)/);
  return m ? parseInt(m[1].replace(/,/g, ''), 10) : null;
}

// Open a part's detail page and return the first real (non-logo/avatar) image URL.
async function scrapePartImage(page, partId) {
  const url = `${BASE}/${SHOP}/parts/${partId}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(300);
  return page.evaluate(() => {
    // Only accept real uploaded attachments. Easy Truck Shop serves genuine
    // part photos under .../attachments/... on its CDN; anything else (logo,
    // avatar, or a static "no image" placeholder) must not be treated as a
    // part photo — otherwise we'd re-host the same placeholder hundreds of times.
    const imgs = Array.from(document.querySelectorAll('img')).filter(img =>
      img.src &&
      img.src.includes('cdn.easytruck.shop') &&
      img.src.includes('/attachments/') &&
      !img.src.includes('logo') &&
      !img.src.includes('avatar') &&
      !img.src.startsWith('data:')
    );
    return imgs.length ? imgs[0].src : null;
  });
}

(async () => {
  const { browser, page } = await loginSession({ headless: true });

  const listUrl = `${BASE}/${SHOP}/parts?sort=-part`;
  await page.goto(listUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const bodyText = await page.locator('body').innerText();
  const totalMatch = bodyText.match(/Showing \d+ to \d+ of ([\d,]+) results/);
  const total = totalMatch ? parseInt(totalMatch[1].replace(/,/g, ''), 10) : null;
  console.log('Total parts:', total);

  const perPage = 50;
  const totalPages = total ? Math.ceil(total / perPage) : 1;

  let results = [];
  if (fs.existsSync(OUT_FILE)) {
    results = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8'));
    console.log(`Resuming: ${results.length} parts already scraped`);
  }
  const seen = new Set(results.map(r => r.partNumber));
  const failures = fs.existsSync(FAIL_FILE) ? JSON.parse(fs.readFileSync(FAIL_FILE, 'utf8')) : [];

  for (let p = 1; p <= totalPages; p++) {
    const url = `${listUrl}&page=${p}`;
    await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(500);

    // Pull each row's cells AND its part-detail id (from the row's link href).
    const rows = await page.locator('table tbody tr').evaluateAll(trs =>
      trs.map(tr => {
        const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
        const link = tr.querySelector('a[href*="/parts/"]');
        let partId = null;
        if (link) {
          const m = link.getAttribute('href').match(/\/parts\/(\d+)/);
          partId = m ? m[1] : null;
        }
        return { cells, partId };
      })
    );

    for (const { cells, partId } of rows) {
      // cells[0] = checkbox; cells[1] = "PARTNO\nDescription"; then the named cols.
      const partCell = cells[1] || cells[0] || '';
      const [partNumber, ...descParts] = partCell.split('\n');
      const pn = (partNumber || '').trim();
      if (!pn || seen.has(pn)) continue;

      const rec = {
        etsPartId: partId,
        partNumber: pn,
        description: descParts.join(' ').trim(),
        crossRef: cells[2] || null,
        vendor: cells[3] || null,
        location: cells[4] || null,
        stock: parseStock(cells[5]),
        cost: cells[6] || null,
        price: cells[7] || null,
        lastSold: cells[8] || null,
        notes: cells[9] || null,
        imageUrl: null,
        raw: cells,
      };

      // Grab the part image from its detail page (best-effort).
      if (partId) {
        try {
          rec.imageUrl = await scrapePartImage(page, partId);
        } catch (e) {
          failures.push({ partNumber: pn, partId, reason: e.message });
        }
      }

      results.push(rec);
      seen.add(pn);
    }

    fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
    fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
    const withImg = results.filter(r => r.imageUrl).length;
    console.log(`Page ${p}/${totalPages} done. Total: ${results.length}, with image: ${withImg}, failures: ${failures.length}`);
  }

  console.log('DONE. Total parts scraped:', results.length);
  await browser.close();
})();
