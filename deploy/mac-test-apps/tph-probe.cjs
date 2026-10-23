const assert = require('node:assert/strict');
const fs = require('node:fs');
const mongoose = require('mongoose');
const jwt = require('jsonwebtoken');
async function main() {
  const credentials = JSON.parse(fs.readFileSync(0, 'utf8'));
  const base = 'http://127.0.0.1:5050';
  const listed = await (await fetch(base + '/api/addresses?id=LOCALTEST-001')).json();
  assert.equal(listed.success, true); assert.equal(listed.total, 1); assert.equal(listed.addresses[0].id, 'LOCALTEST-001');
  assert.equal((await fetch(base + '/api/addresses/LOCALTEST-HIDDEN')).status, 404);
  const login = await fetch(base + '/api/pin/verify-client', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ pin: credentials.manager_pin }) });
  const session = await login.json();
  assert.equal(session.success, true); assert.equal(session.userName, 'LOCALTEST Manager');
  assert.equal(jwt.verify(session.managerToken, process.env.MANAGER_JWT_SECRET, { algorithms: ['HS256'], issuer: 'rstc-manager-auth', audience: 'rstc-manager-api' }).role, 'manager');
  assert.ok(session.managerToken); assert.ok(session.managerTokenExpiresAt);
  assert.equal((await fetch(base + '/api/pin/verify-client', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ pin: '000000' }) })).status, 403);
  const unauthorized = await fetch(base + '/api/admin/hiring');
  assert.ok([401,403].includes(unauthorized.status));
  await mongoose.connect(process.env.MONGO_URI_DEV);
  const job = await mongoose.connection.db.collection('blogresearchjobs').findOne({ topic: 'LOCALTEST: synthetic worker acceptance' });
  assert.equal(job.status, 'completed'); assert.equal(job.attempts, 1);
  assert.equal(await mongoose.connection.db.collection('blogposts').countDocuments(), 1);
  assert.equal(await mongoose.connection.db.collection('blogposts').countDocuments({ status: 'published' }), 0);
  assert.equal(await mongoose.connection.db.collection('blogresearchjobs').countDocuments({ trigger: 'scheduled' }), 0);
  console.log(JSON.stringify({ public_location: true, hidden_denied: true, manager_login: true, wrong_pin_denied: true,
    admin_unauthenticated_denied: true, job_status: job.status, job_attempts: job.attempts, drafts: 1, published: 0, scheduled_jobs: 0 }));
  await mongoose.disconnect();
  process.exit(0);
}
main().catch(() => { console.error('Local TPH acceptance failed; credentials and responses withheld'); process.exit(1); });
