// Isolated test entrypoint; requiring server prevents its direct-start scheduler.
process.env.DISABLE_SCHEDULER = 'true';
const assert = require('node:assert/strict');
assert.equal(process.env.SQUARE_ENVIRONMENT, 'sandbox');
const uri = new URL(process.env.MONGO_URI_DEV);
assert.equal(uri.hostname, 'mongo');
assert.equal(uri.pathname, '/tph_local_test');
const { app, httpServer } = require('./backend/server');
const connect = require('./backend/config/database');
const mongoose = require('mongoose');
// This test-only readiness route is distinct from production's liveness route.
require('node:http').createServer(async (req, res) => {
  if (req.url !== '/local-test/ready') { res.writeHead(404); return res.end(); }
  res.setHeader('Content-Type', 'application/json');
  try {
    await mongoose.connection.db.admin().ping();
    res.end(JSON.stringify({ status: 'ready', environment: 'local-test', source: process.env.LOCAL_SOURCE_SHA,
               database: mongoose.connection.db.databaseName, scheduler: 'disabled' }));
  } catch (_) { res.writeHead(503); res.end(JSON.stringify({ status: 'unavailable' })); }
}).listen(5051, '0.0.0.0');
connect().then(() => httpServer.listen(5050, '0.0.0.0')).catch(() => {
  console.error('Isolated TPH startup failed; inspect private log'); process.exit(1);
});
