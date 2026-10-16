const { BASE, SHOP } = require('./auth');
const { contactSnapshot } = require('./contact_snapshot');

// Get vehicle IDs + unit numbers for a customer from their detail page. The
// vehicle rows carry the id in an <a href=".../vehicles/{id}">, so read it
// directly in one page load — no per-row clicking (which raced navigations and
// was ~Nx slower).
async function getCustomerVehicleIds(page, customerId) {
  const url = `${BASE}/${SHOP}/customers/${customerId}`;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
      await page.waitForTimeout(400);
      return await page.locator('table tbody tr').evaluateAll(trs =>
        trs.map(tr => {
          const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
          const link = tr.querySelector('a[href*="/vehicles/"]');
          let vehicleId = null;
          if (link) {
            const m = link.getAttribute('href').match(/\/vehicles\/(\d+)/);
            vehicleId = m ? m[1] : null;
          }
          return { vehicleId, listCells: cells };
        })
      ).then(rows => rows.filter(r => r.vehicleId)); // skip non-vehicle rows
    } catch (e) {
      if (attempt === 2) throw e;
      await page.waitForTimeout(1200);
    }
  }
  return [];
}

// Scrape full vehicle detail from its /edit form (has full VIN)
async function getVehicleEditData(page, vehicleId) {
  const url = `${BASE}/${SHOP}/vehicles/${vehicleId}/edit`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(500);

  const data = await page.evaluate(() => {
    function getLabelValue(labelText) {
      const labels = Array.from(document.querySelectorAll('label'));
      const label = labels.find(l => l.textContent.trim().replace('*', '').trim() === labelText);
      if (!label) return null;
      // find nearest following input/textarea within same form group
      let container = label.closest('div');
      while (container && !container.querySelector('input, textarea')) {
        container = container.parentElement;
        if (!container || container.tagName === 'BODY') return null;
      }
      const input = container ? container.querySelector('input, textarea') : null;
      return input ? input.value : null;
    }
    return {
      company: getLabelValue('Company'),
      unit: getLabelValue('Unit'),
      vin: getLabelValue('VIN'),
      licensePlate: getLabelValue('Licence Plate'),
      make: getLabelValue('Make'),
      model: getLabelValue('Model'),
      year: getLabelValue('Year'),
      color: getLabelValue('Color'),
      notes: getLabelValue('Notes'),
      odometer: getLabelValue(''),
    };
  });
  return data;
}

// Scrape service history table from vehicle detail page (not edit)
// Service history is paginated at 15 rows. Reading only the first page silently
// dropped every service past the 15th — vehicle 97945 has 25 services in ETS and
// we were importing 15 of them. That under-reported revenue for the whole shop,
// and looked like a reporting discrepancy rather than missing data. Walk every
// page and stop when the pager says we have them all.
async function getVehicleServiceHistory(page, vehicleId) {
  const base = `${BASE}/${SHOP}/vehicles/${vehicleId}`;
  const all = [];
  let expected = null;

  for (let p = 1; p <= 50; p++) {
    const url = p === 1 ? base : `${base}?page=${p}`;
    await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(500);

    if (expected === null) {
      const text = await page.locator('body').innerText();
      const m = text.match(/Showing \d+ to \d+ of ([\d,]+) results/);
      expected = m ? parseInt(m[1].replace(/,/g, ''), 10) : null;
    }

    const rows = await page.locator('table tbody tr').evaluateAll(trs =>
      trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))
    );
    const real = rows.filter(r => r[0] && r[0] !== 'No results');
    if (!real.length) break;
    all.push(...real);

    // No pager means a single page; otherwise stop once we have them all.
    if (expected === null || all.length >= expected) break;
  }

  if (expected !== null && all.length < expected) {
    console.log(`  WARNING vehicle ${vehicleId}: captured ${all.length} of ${expected} services`);
  }
  return all;
}

// Scrape contacts table for a customer
async function getCustomerContacts(page, customerId) {
  const url = `${BASE}/${SHOP}/customers/${customerId}/contacts`;
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(500);
    const view = await page.evaluate(() => {
      // Verified AX contract: CUSTOMER h2, CONTACT details and exact account
      // navigation share a header ancestor; the contacts table is outside it.
      // A generic/global page header cannot establish this binding.
      let accountHeader = null;
      for (const heading of document.querySelectorAll('h2')) {
        for (let parent = heading.parentElement; parent && !parent.querySelector('table'); parent = parent.parentElement) {
          const links = [...parent.querySelectorAll('a[href]')].map(el => new URL(el.href).pathname);
          if (links.includes(location.pathname) && links.includes(location.pathname.replace(/\/contacts$/, ''))
              && /\bCUSTOMER\b/.test(parent.textContent) && /\bCONTACT\b/.test(parent.textContent)) {
            accountHeader = parent; break;
          }
        }
        if (accountHeader) break;
      }
      const search = document.querySelector('#filter-search-input input, .filter-search-input input');
      const archive = [...document.querySelectorAll('label')].find(el => /Show archived/.test(el.textContent));
      const checkbox = archive && (archive.querySelector('input[type=checkbox]') || document.getElementById(archive.htmlFor));
      const footer = [...document.querySelectorAll('p, div, span')].find(el => /^Showing\s+\d+\s+to\s+\d+\s+of\s+\d+\s+results$/.test(el.textContent.trim()));
      return {pathname: location.pathname, searchValue: search ? search.value : null,
        archived: checkbox ? checkbox.checked : null,
        headerBound: !!accountHeader,
        headerPhones: accountHeader ? [...accountHeader.querySelectorAll('a[href^="tel:"]')].map(el => el.textContent.trim()) : [],
        headers: [...document.querySelectorAll('table thead th')].map(el => el.textContent.trim()),
        rows: [...document.querySelectorAll('table tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim())),
        footer: footer ? footer.textContent.trim() : '',
        hasNext: [...document.querySelectorAll('a,button')].some(el => /^(Next|Next page|›|»)$/i.test(el.textContent.trim()) && !el.disabled && el.getAttribute('aria-disabled') !== 'true' && (el.tagName !== 'A' || el.hasAttribute('href')))};
    });
    const snapshot = contactSnapshot(view, {shop: SHOP, customerId, observedAt: new Date().toISOString()});
    return {contacts: snapshot.complete ? view.rows.map(([role, firstName, lastName, phone, email, notes]) => ({role, firstName, lastName, phone, email, notes}))
      .filter(c => c.firstName || c.lastName || c.email || c.phone) : [], snapshot};
  } catch (_) {
    return {contacts: [], snapshot: {source_shop_id: SHOP, source_customer_id: String(customerId),
      observed_at: new Date().toISOString(), complete: false, reason: 'read_unavailable', phones: []}};
  }
}

module.exports = { getCustomerVehicleIds, getVehicleEditData, getVehicleServiceHistory, getCustomerContacts };
