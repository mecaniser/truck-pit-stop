const { BASE, SHOP } = require('./auth');

// Get vehicle IDs + unit numbers for a customer by clicking each row on their detail page.
async function getCustomerVehicleIds(page, customerId) {
  const url = `${BASE}/${SHOP}/customers/${customerId}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(500);

  const rowCount = await page.locator('table tbody tr').count();
  const vehicles = [];
  for (let i = 0; i < rowCount; i++) {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(300);
    const row = page.locator('table tbody tr').nth(i);
    const cells = await row.locator('td').allInnerTexts();
    await row.locator('td').first().click();
    let vehicleId = null;
    for (let attempt = 0; attempt < 15; attempt++) {
      const m = page.url().match(/\/vehicles\/(\d+)$/);
      if (m) { vehicleId = m[1]; break; }
      await page.waitForTimeout(250);
    }
    vehicles.push({ vehicleId, listCells: cells });
  }
  return vehicles;
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
async function getVehicleServiceHistory(page, vehicleId) {
  const url = `${BASE}/${SHOP}/vehicles/${vehicleId}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(500);

  const rows = await page.locator('table tbody tr').evaluateAll(trs =>
    trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))
  );
  return rows;
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
