// Stage 2: for each customer, scrape contacts (email), vehicles (full VIN via edit form),
// and each vehicle's service history. Resumable: skips customers already in output.
//
// Vehicles come from data/all_vehicles.json (stage 01b), NOT from links on the
// customer page. A vehicle with no VIN renders there without an <a href=
// ".../vehicles/{id}">, so link-scraping silently dropped it along with its whole
// service history — 324 of 826 vehicles were reaching us, capping every revenue
// figure at roughly 60% of what ETS reports.
const fs = require('fs');
const path = require('path');
const { loginSession } = require('./lib/auth');
const { getVehicleEditData, getVehicleServiceHistory, getCustomerContacts } = require('./lib/scrape_helpers');

const IDS_FILE = path.join(__dirname, 'data', 'customer_ids.json');
const ALL_VEHICLES_FILE = path.join(__dirname, 'data', 'all_vehicles.json');
const OUT_FILE = path.join(__dirname, 'data', 'customer_details.json');
const FAIL_FILE = path.join(__dirname, 'data', 'customer_details_failures.json');

(async () => {
  const customerIds = JSON.parse(fs.readFileSync(IDS_FILE, 'utf8'));
  console.log(`Loaded ${customerIds.length} customer ids to process`);

  if (!fs.existsSync(ALL_VEHICLES_FILE)) {
    console.error('ABORT: data/all_vehicles.json missing — run 01b_scrape_all_vehicles.js first.\n'
                + 'Without it this stage falls back to link-scraping and silently drops '
                + 'every vehicle that has no VIN.');
    process.exit(1);
  }
  const allVehicles = JSON.parse(fs.readFileSync(ALL_VEHICLES_FILE, 'utf8'));
  const vehiclesByCustomer = new Map();
  for (const v of allVehicles) {
    if (!v.customerId) continue;
    if (!vehiclesByCustomer.has(v.customerId)) vehiclesByCustomer.set(v.customerId, []);
    vehiclesByCustomer.get(v.customerId).push(v);
  }
  console.log(`Loaded ${allVehicles.length} vehicles across ${vehiclesByCustomer.size} customers`);

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
      const vehicleRows = (vehiclesByCustomer.get(String(cust.id)) || []).map(v => ({
        vehicleId: v.vehicleId,
        // The customer page's row cells used to supply unit/desc; take the
        // equivalents from the authoritative vehicle record instead.
        listCells: [v.unit || '', '', [v.year, v.make, v.model].filter(Boolean).join(' • ')],
      }));

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
