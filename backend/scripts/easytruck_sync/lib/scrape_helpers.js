const { BASE, SHOP } = require('./auth');

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
  await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(500);
  const rows = await page.locator('table tbody tr').evaluateAll(trs =>
    trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))
  );
  return rows.map(([role, firstName, lastName, phone, email, notes]) => ({ role, firstName, lastName, phone, email, notes }))
    .filter(c => c.firstName || c.lastName || c.email || c.phone);
}

module.exports = { getCustomerVehicleIds, getVehicleEditData, getVehicleServiceHistory, getCustomerContacts };
