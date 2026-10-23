// Empty-database-only synthetic seed. Credentials arrive through private stdin.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const mongoose = require('mongoose');
const Parking = require('./backend/models/ParkingSpace');
const Pin = require('./backend/models/Pin');
const Job = require('./backend/models/BlogResearchJob');
async function main() {
  assert.equal(process.env.LOCAL_TEST_ONLY, 'true');
  const uri = new URL(process.env.MONGO_URI_DEV);
  assert.equal(uri.hostname, 'mongo'); assert.equal(uri.pathname, '/tph_local_test');
  const credentials = JSON.parse(fs.readFileSync(0, 'utf8'));
  assert.match(credentials.manager_pin, /^[1-9][0-9]{5}$/);
  await mongoose.connect(process.env.MONGO_URI_DEV);
  const collections = await mongoose.connection.db.listCollections().toArray();
  for (const collection of collections) {
    if (await mongoose.connection.db.collection(collection.name).countDocuments()) throw new Error('Populated database; seed refused');
  }
  await Parking.create([
    { id: 'LOCALTEST-001', title: 'LOCALTEST Synthetic Parking', address: '100 Synthetic Test Road, Test City, NC 00000',
      coordinates: { lat: 0, lng: 0 }, publiclyHidden: false, availability: true, openForParking: true,
      openForDaily: false, openForMonthly: false, monthlySubscriptionMode: 'none' },
    { id: 'LOCALTEST-HIDDEN', title: 'LOCALTEST Hidden Parking', address: '200 Synthetic Test Road, Test City, NC 00000',
      coordinates: { lat: 0, lng: 0 }, publiclyHidden: true, availability: true, openForParking: true,
      openForDaily: false, openForMonthly: false, monthlySubscriptionMode: 'none' },
  ]);
  await Pin.createPin({ type: 'client', pin: credentials.manager_pin, name: 'LOCALTEST Manager', createdBy: 'local-synthetic-seed' });
  await Job.create({ topic: 'LOCALTEST: synthetic worker acceptance', trigger: 'manual', sourceUrls: [] });
  console.log(JSON.stringify({ seeded: true, locations: 2, manager: 1, synthetic_jobs: 1 }));
  await mongoose.disconnect();
}
main().catch(() => { console.error('Synthetic seed refused or failed; inspect isolated database'); process.exit(1); });
