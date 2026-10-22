'use strict';
// One-shot diagnostic only. Never imports the app/Mongoose/models/workers/providers.
// Reviewed runner must join ONLY the NEW clone internal network, with no env secrets.
const crypto = require('node:crypto');
const fs = require('node:fs');
const { MongoClient, BSON } = require('mongodb');
const MAX_DOCS = 2000000, MAX_BYTES = 2 * 1024 * 1024 * 1024;
function check(value) { if (!value) throw Error('target_inventory_refused'); }
function sha(value) { return crypto.createHash('sha256').update(value).digest('hex'); }
function canonical(value) {
 if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
 if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',') + '}';
 check(typeof value !== 'number' || Number.isFinite(value));
 return JSON.stringify(value);
}
function ordered(value) {
 if(Array.isArray(value)) return value.map(ordered);
 if(value && typeof value==='object') {check(!Object.keys(value).some(k=>/^[0-9]+$/.test(k)));return {$ordered:Object.entries(value).map(([k,v])=>[k,ordered(v)])};}
 return value;
}
function fingerprints(options,indexes,collection) {
 check(options && typeof options==='object' && !Array.isArray(options) && Array.isArray(indexes));
 const names=new Set();
 const hashes=indexes.map(input=>{
  const index=BSON.EJSON.serialize(input,{relaxed:false});
  check(typeof index.name==='string' && index.key && typeof index.key==='object' && !Array.isArray(index.key) && !names.has(index.name));
  names.add(index.name);
  if(Object.hasOwn(index,'ns')) {check(index.ns==='tph_local_test.'+collection);index.ns='ParkRightDB.'+collection;}
  const normalized=Object.fromEntries(Object.keys(index).sort().map(k=>[k,ordered(index[k])]));
  return sha(canonical(normalized));
 }).sort();
 return {collection_options_sha256:sha(canonical(ordered(BSON.EJSON.serialize(options,{relaxed:false})))),
  indexes_sha256:sha(canonical(hashes)),index_count:indexes.length};
}
function documentFingerprint(hashes) {
 const result=crypto.createHash('sha256').update(Buffer.from('raw-bson-multiset-v1\0','utf8'));
 for(const [key,count] of [...hashes.entries()].sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0)) {
  const size=Buffer.alloc(8);size.writeBigUInt64BE(BigInt(count));
  result.update(Buffer.from(key,'hex'));result.update(size);
 }
 return result.digest('hex');
}
function inputConfig(input) {
 check(input && Object.keys(input).sort().join(',')==='mongoUri');
 const uri=new URL(input.mongoUri);
 check(uri.protocol==='mongodb:' && uri.hostname==='mongo' && uri.port==='27017'
  && uri.username==='clone_restore_admin' && uri.password && uri.pathname==='/tph_local_test'
  && uri.search==='?authSource=admin' && !uri.hash);
 return input.mongoUri;
}
async function inventory(client) {
 const db=client.db('tph_local_test');
 const collections=await db.listCollections({}, {nameOnly:false,promoteValues:false,promoteLongs:false}).toArray();
 check(collections.length<=4096);
 const names=new Set(),result={version:1,method:'raw-bson-multiset-v1',database:'tph_local_test',
  document_count:0,namespace_count:collections.length,namespaces:{},collection_uuid_equality:'not_asserted_mongorestore_may_generate_new_uuids'};
 for(const info of collections) {
  check(typeof info.name==='string' && info.name && Buffer.byteLength(info.name)<=255 && !/[\0\r\n]/.test(info.name)
    && !names.has(info.name) && info.type==='collection' && !info.options?.timeseries && !info.options?.viewOn);
  names.add(info.name);
  const collection=db.collection(info.name);
  const indexes=await collection.listIndexes({maxTimeMS:60000,promoteValues:false,promoteLongs:false}).toArray();
  const hashes=new Map();let count=0,bytes=0;
  const cursor=collection.find({}, {raw:true,batchSize:200,maxTimeMS:60000});
  try {
   for await(const raw of cursor) {
    check(Buffer.isBuffer(raw) && raw.length>=5 && raw.length<=16*1024*1024
      && raw.readInt32LE(0)===raw.length && raw[raw.length-1]===0);
    const digest=sha(raw);hashes.set(digest,(hashes.get(digest)||0)+1);count++;bytes+=raw.length;
    check(result.document_count+count<=MAX_DOCS && bytes<=MAX_BYTES);
   }
  } finally {await cursor.close();}
  result.document_count+=count;
  result.namespaces['ParkRightDB.'+info.name]={count,bson_bytes:bytes,documents_sha256:documentFingerprint(hashes),
    ...fingerprints(info.options||{},indexes,info.name)};
 }
 check(Object.values(result.namespaces).reduce((n,c)=>n+c.bson_bytes,0)<=MAX_BYTES);
 return result;
}
async function main() {
 // Process environment must not carry provider credentials or native app startup hooks.
 check(!process.env.NODE_OPTIONS && !process.env.NODE_PATH);
 for(const [key,value] of Object.entries(process.env)) if(/^(POSTMARK|RESEND|TWILIO|STRIPE|WORKOS|META|FACEBOOK|SENDGRID|SMTP).*?(TOKEN|SECRET|KEY|PASSWORD|SID)$/i.test(key))check(!value);
 const raw=fs.readFileSync(0,'utf8');check(Buffer.byteLength(raw)<=4096);
 const uri=inputConfig(JSON.parse(raw));
 const client=new MongoClient(uri,{directConnection:true,serverSelectionTimeoutMS:10000,connectTimeoutMS:10000,
   socketTimeoutMS:60000,retryReads:false,appName:'approved-clone-inventory'});
 try {await client.connect(); const result=await inventory(client); process.stdout.write(canonical(result)+'\n');}
 finally {await client.close();}
}
module.exports={canonical,ordered,fingerprints,documentFingerprint,inputConfig,inventory};
if(require.main===module)main().catch(()=>{console.error('target_inventory_failed_values_withheld');process.exitCode=1;});
