// Stage 1b: enumerate EVERY vehicle from the shop-wide /vehicles list.
//
// Vehicles used to be discovered only from each customer's page, by reading rows
// that contained an <a href=".../vehicles/{id}">. Vehicles with sparse records —
// no year/make/VIN — render without that link (their only <a> is a tel: link),
// so they were silently dropped along with their entire service history.
// 77 CARGO LLC showed 15 vehicles in ETS and we captured 10.
//
// Shop-wide that meant 324 of 826 vehicles imported, which capped every revenue
// figure at roughly 60% of what ETS reports and looked like a reporting
// discrepancy rather than missing data.
//
// The list is a Laravel/Inertia page: the full records, ids included, are in the
// root element's data-page attribute, so no row clicking is needed.
const fs = require('fs');
const path = require('path');
const { loginSession, SHOP, BASE } = require('./lib/auth');

const OUT_FILE = path.join(__dirname, 'data', 'all_vehicles.json');

async function readPage(page, n, sort) {
  const url = `${BASE}/${SHOP}/vehicles?page=${n}` + (sort ? `&sort=${sort}` : '');
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(300);
      return await page.evaluate(() => {
        const el = document.querySelector('[data-page]');
        if (!el) return null;
        const v = JSON.parse(el.getAttribute('data-page')).props.vehicles;
        return {
          // NB: the VIN key is upper-case, and the customer arrives as a nested
          // object rather than a customer_id column.
          rows: (v.data || []).filter(r => !r.deleted).map(r => ({
            vehicleId: String(r.id),
            unit: r.unit ?? null,
            customerId: r.customer && r.customer.id != null ? String(r.customer.id) : null,
            company: r.customer ? (r.customer.company ?? null) : null,
            vin: r.VIN ?? null,
            make: r.make ?? null,
            model: r.model ?? null,
            year: r.year ?? null,
            lastServiceDate: r.last_service_date ?? null,
          })),
          // Laravel paginators expose this as last_page, meta.last_page, or only
          // as numbered entries in a links array — accept whichever is present.
          lastPage: (() => {
            if (v.last_page) return v.last_page;
            if (v.meta && v.meta.last_page) return v.meta.last_page;
            const links = Array.isArray(v.links) ? v.links
                        : (v.meta && Array.isArray(v.meta.links)) ? v.meta.links : [];
            return links.reduce((m, l) => {
              const n = parseInt(l && l.label, 10);
              return Number.isFinite(n) && n > m ? n : m;
            }, 1);
          })(),
          total: v.total ?? (v.meta && v.meta.total) ?? null,
        };
      });
    } catch (e) {
      console.log(`  page ${n} failed (attempt ${attempt}/3): ${e.message.split('\n')[0]}`);
      if (attempt === 3) return null;
      await page.waitForTimeout(4000 * attempt);
    }
  }
  return null;
}

(async () => {
  const { browser, page } = await loginSession({ headless: true });

  const first = await readPage(page, 1);
  if (!first) {
    console.error('ABORT: could not read the vehicle list. Refusing to write a partial file.');
    await browser.close();
    process.exit(1);
  }
  const lastPage = first.lastPage || 1;
  const expected = first.total;
  console.log(`Vehicles: ${expected ?? '?'} total across ${lastPage} pages`);

  const byId = new Map();
  first.rows.forEach(r => byId.set(r.vehicleId, r));

  // The list has no stable default order, so a row can shift between page loads
  // and be missed — the same pagination instability this repo hit on the
  // customers and parts lists. Walk it again in a second ordering and union by
  // id; a straggler in one pass is picked up by the other.
  for (const sort of [null, 'unit']) {
    for (let p = sort ? 1 : 2; p <= lastPage; p++) {
      const res = await readPage(page, p, sort);
      if (!res) { console.log(`  page ${p}${sort ? ' (sorted)' : ''}: SKIPPED after retries`); continue; }
      res.rows.forEach(r => byId.set(r.vehicleId, r));
    }
    console.log(`  pass ${sort ? `sort=${sort}` : 'default'} complete — ${byId.size} vehicles`);
    if (expected && byId.size >= expected) break;
  }

  const out = Array.from(byId.values());
  fs.writeFileSync(OUT_FILE, JSON.stringify(out, null, 2));

  if (expected && out.length < expected) {
    console.log(`WARNING: captured ${out.length} of ${expected} vehicles — some pages failed.`);
  }
  console.log(`DONE. Total vehicles: ${out.length}`);
  await browser.close();
})();
