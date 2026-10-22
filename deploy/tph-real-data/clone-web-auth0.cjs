'use strict';
// Read-only mounted adapter for the reviewed native pinned image. No identity shim.
const assert = require('node:assert/strict');
assert.equal(process.env.REAL_DATA_CLONE, 'true');
assert.equal(process.env.LOCAL_TEST_ONLY, 'true');
assert.equal(process.env.SQUARE_ENVIRONMENT, 'sandbox');
assert.equal(process.env.DISABLE_SCHEDULER, 'true');
for (const key of ['BLOG_STUDIO_ENABLED', 'BLOG_STUDIO_RUN_IN_WEB', 'WORKOS_TENANT_ENABLED',
 'MONTHLY_SUBSCRIPTIONS_ENABLED', 'MONTHLY_CUSTOM_AUTOPAY_ENABLED', 'HIRING_CANDIDATE_SMS_ENABLED',
 'ADMIN_SMS_ENABLED', 'ADMIN_PAYMENT_SMS_ENABLED', 'ERROR_ALERTS_ENABLED', 'ERROR_ALERTS_SMS_ENABLED',
 'PERF_SLO_ALERTS_ENABLED']) assert.equal(process.env[key], 'false');
const uri = new URL(process.env.MONGO_URI_DEV);
assert.equal(uri.hostname, 'mongo'); assert.equal(uri.pathname, '/tph_local_test');
assert.equal(uri.username, 'clone_reader'); assert.equal(uri.search, '?authSource=tph_local_test');
assert.equal(process.env.AUTH0_DOMAIN, 'dev-wp1mdcmju5ix3zgt.us.auth0.com');
assert.equal(process.env.AUTH0_AUDIENCE, 'https://trucksparkinghub.com/api');
assert.equal(process.env.SQUARE_ACCESS_TOKEN, 'LOCAL_TEST_INVALID_NOT_A_PROVIDER_CREDENTIAL');
for (const [key,value] of Object.entries(process.env)) {
 if (/^(POSTMARK|RESEND|TWILIO|STRIPE|WORKOS|META|FACEBOOK|SENDGRID|SMTP).*?(TOKEN|SECRET|KEY|PASSWORD|SID)$/i.test(key) || /^(AUTH0).*?(SECRET|PASSWORD)$/i.test(key)) {
  assert.ok(!value, 'provider credentials refused');
 }
}
const mongoose = require('mongoose');
// Existing restored native indexes remain authoritative; application startup may not create any.
mongoose.set('autoIndex', false); mongoose.set('autoCreate', false);
require('/run/clone/auth0_cached_jwks.cjs').install(require);
const { app, httpServer } = require('./backend/server');
const connect = require('./backend/config/database');
// Importing native modules must not introduce a provider credential or change the guarded DB.
assert.equal(process.env.MONGO_URI_DEV, uri.href);
assert.equal(process.env.DISABLE_SCHEDULER, 'true');
assert.equal(process.env.SQUARE_ENVIRONMENT, 'sandbox');
for (const [key,value] of Object.entries(process.env)) {
 if (/^(POSTMARK|RESEND|TWILIO|STRIPE|WORKOS|META|FACEBOOK|SENDGRID|SMTP).*?(TOKEN|SECRET|KEY|PASSWORD|SID)$/i.test(key)
  || /^(AUTH0).*?(SECRET|PASSWORD)$/i.test(key)) assert.ok(!value, 'provider credentials refused');
}
require('node:http').createServer(async (req,res) => {
 if(req.url !== '/local-test/ready') { res.writeHead(404); return res.end(); }
 res.setHeader('Content-Type','application/json'); res.setHeader('Cache-Control','no-store');
 try {
  assert.equal(mongoose.connection.db.databaseName, 'tph_local_test');
  await mongoose.connection.db.admin().ping();
  res.end(JSON.stringify({status:'ready',environment:'real-data-clone',source:process.env.LOCAL_SOURCE_SHA,
   scheduler:'disabled',workers:0,auth0:'Mac-client-with-cached-public-JWKS',writes:'pin-usage-only'}));
 } catch (_) { res.writeHead(503); res.end(JSON.stringify({status:'unavailable'})); }
}).listen(5051,'0.0.0.0');
connect().then(()=>httpServer.listen(5050,'0.0.0.0')).catch(()=>{
 console.error('Isolated clone unavailable; private diagnostics only');process.exit(1);
});
