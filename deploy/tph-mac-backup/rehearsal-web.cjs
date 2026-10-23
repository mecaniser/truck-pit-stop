// This bootstrap is for a synthetic failover rehearsal only.
process.env.DISABLE_SCHEDULER = 'true';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
assert.equal(process.env.LOCAL_TEST_ONLY, 'true');
assert.equal(process.env.SQUARE_ENVIRONMENT, 'sandbox');
const uri = new URL(process.env.MONGO_URI_DEV);
assert.equal(uri.hostname, 'mongo');
assert.equal(uri.pathname, '/tph_backup_restored');
assert.match(process.env.REHEARSAL_CONTROL_TOKEN, /^[a-f0-9]{64}$/);
const { app, httpServer } = require('./backend/server');
const connect = require('./backend/config/database');
const mongoose = require('mongoose');
const token = process.env.REHEARSAL_CONTROL_TOKEN;
require('node:http').createServer(async (req, res) => {
  res.setHeader('Content-Type', 'application/json');
  try {
    if (req.method === 'GET' && req.url === '/ready') {
      await mongoose.connection.db.admin().ping();
      return res.end(JSON.stringify({ready:true,source:process.env.LOCAL_SOURCE_SHA,site:process.env.REHEARSAL_SITE}));
    }
    if (req.method === 'GET' && req.url === '/authority') {
      const row = await mongoose.connection.db.collection('backup_rehearsal_authority').findOne({_id:'shared'});
      assert(row);
      const pin = await mongoose.connection.db.collection('pins').findOne({type:'client'});
      return res.end(JSON.stringify({authority_id:row.authority_id,watermark:row.watermark,database:mongoose.connection.db.databaseName,instance_prefix:require('node:os').hostname(),pin_usage:pin?.usageCount||0,source:process.env.LOCAL_SOURCE_SHA}));
    }
    const given = req.headers['x-rehearsal-control'];
    if (req.method === 'POST' && req.url === '/checkpoint' && typeof given === 'string' && given.length === token.length && crypto.timingSafeEqual(Buffer.from(given),Buffer.from(token))) {
      let data=''; for await (const chunk of req) {data+=chunk;if(data.length>1024)throw Error('body_limit');}
      const value=JSON.parse(data);
      assert(Number.isSafeInteger(value.watermark)&&value.watermark>=0);
      assert.equal(value.authority_id,process.env.REHEARSAL_AUTHORITY);
      const result=await mongoose.connection.db.collection('backup_rehearsal_authority').updateOne({_id:'shared',authority_id:value.authority_id},{$max:{watermark:value.watermark}});
      assert.equal(result.matchedCount,1);
      return res.end(JSON.stringify({checkpointed:true}));
    }
    res.writeHead(404);res.end('{}');
  } catch (_) {res.writeHead(503);res.end('{"ready":false}');}
}).listen(5051,'0.0.0.0');
connect().then(()=>httpServer.listen(5050,'0.0.0.0')).catch(()=>{console.error('Synthetic backup app startup refused');process.exit(1);});
