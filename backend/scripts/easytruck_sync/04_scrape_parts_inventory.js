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

  // The total drives how many pages we walk. A failed/slow first load used to
  // leave it null, which silently fell back to ONE page — the run then exited
  // reporting success while skipping every part past page 1. Retry, and abort
  // loudly rather than under-collecting behind a "DONE" message.
  let total = null;
  for (let attempt = 1; attempt <= 4 && total === null; attempt++) {
    try {
      await page.goto(listUrl, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(800);
      const bodyText = await page.locator('body').innerText();
      const m = bodyText.match(/Showing \d+ to \d+ of ([\d,]+) results/);
      if (m) total = parseInt(m[1].replace(/,/g, ''), 10);
      else console.log(`Total parts not found (attempt ${attempt}/4), retrying…`);
    } catch (e) {
      console.log(`Total-count load failed (attempt ${attempt}/4): ${e.message}`);
    }
    if (total === null) await page.waitForTimeout(3000 * attempt);
  }
  if (total === null) {
    console.error('ABORT: could not determine total part count after 4 attempts. '
                + 'Refusing to run, since that would silently scrape only page 1.');
    await browser.close();
    process.exit(1);
  }
  console.log('Total parts:', total);

  const perPage = 50;
  const totalPages = Math.ceil(total / perPage);

  let results = [];
  if (fs.existsSync(OUT_FILE)) {
    results = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8'));
    console.log(`Resuming: ${results.length} parts already scraped`);
  }
  const seen = new Set(results.map(r => r.partNumber));
  const failures = fs.existsSync(FAIL_FILE) ? JSON.parse(fs.readFileSync(FAIL_FILE, 'utf8')) : [];

  for (let p = 1; p <= totalPages; p++) {
    const url = `${listUrl}&page=${p}`;
    // A single transient ERR_TIMED_OUT used to reject unhandled and kill the
    // whole process mid-catalog. Retry the page, and record it as a failure
    // (rather than dying) so the rest of the catalog still gets scraped.
    let loaded = false;
    for (let attempt = 1; attempt <= 3 && !loaded; attempt++) {
      try {
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(500);
        loaded = true;
      } catch (e) {
        console.log(`Page ${p} load failed (attempt ${attempt}/3): ${e.message.split('\n')[0]}`);
        if (attempt === 3) failures.push({ page: p, reason: e.message.split('\n')[0] });
        else await page.waitForTimeout(5000 * attempt);
      }
    }
    if (!loaded) continue;

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
