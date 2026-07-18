// Stage 2: for each customer, scrape contacts (email), vehicles (full VIN via edit form),
// and each vehicle's service history. Resumable: skips customers already in output.
const fs = require('fs');
const path = require('path');
const { loginSession } = require('./lib/auth');
const { getCustomerVehicleIds, getVehicleEditData, getVehicleServiceHistory, getCustomerContacts } = require('./lib/scrape_helpers');

const IDS_FILE = path.join(__dirname, 'data', 'customer_ids.json');
const OUT_FILE = path.join(__dirname, 'data', 'customer_details.json');
const FAIL_FILE = path.join(__dirname, 'data', 'customer_details_failures.json');

(async () => {
  const customerIds = JSON.parse(fs.readFileSync(IDS_FILE, 'utf8'));
  console.log(`Loaded ${customerIds.length} customer ids to process`);

  let results = [];
  if (fs.existsSync(OUT_FILE)) {
    results = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8'));
    console.log(`Resuming: ${results.length} customers already have details`);
  }
  const done = new Set(results.map(r => r.id));
  const failures = fs.existsSync(FAIL_FILE) ? JSON.parse(fs.readFileSync(FAIL_FILE, 'utf8')) : [];

  const { browser, page } = await loginSession({ headless: true });

  let processed = 0;
  for (const cust of customerIds) {
    if (done.has(cust.id)) continue;

    try {
      const contacts = await getCustomerContacts(page, cust.id);
      const vehicleRows = await getCustomerVehicleIds(page, cust.id);

      const vehicles = [];
      for (const v of vehicleRows) {
        if (!v.vehicleId) {
          failures.push({ customerId: cust.id, company: cust.company, reason: 'vehicle row had no id', listCells: v.listCells });
          continue;
        }
        try {
          const editData = await getVehicleEditData(page, v.vehicleId);
          const serviceHistory = await getVehicleServiceHistory(page, v.vehicleId);
          vehicles.push({ vehicleId: v.vehicleId, listCells: v.listCells, edit: editData, serviceHistory });
        } catch (e) {
          failures.push({ customerId: cust.id, vehicleId: v.vehicleId, reason: e.message });
        }
      }

      results.push({ id: cust.id, company: cust.company, contacts, vehicles });
      done.add(cust.id);
    } catch (e) {
      failures.push({ customerId: cust.id, company: cust.company, reason: e.message });
    }

    processed++;
    if (processed % 5 === 0) {
      fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
      fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
      console.log(`Processed ${results.length}/${customerIds.length} customers. Failures logged: ${failures.length}`);
    }
  }

  fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));
  fs.writeFileSync(FAIL_FILE, JSON.stringify(failures, null, 2));
  console.log(`DONE. Total customers with details: ${results.length}. Failures: ${failures.length}`);
  await browser.close();
})();
