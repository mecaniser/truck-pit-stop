const assert=require('node:assert/strict');
const {vinFrom,coordinates,addressFrom}=require('./collect.cjs');
assert.equal(vinFrom('VIN\n1XKYD49X6LJ311465'),'1XKYD49X6LJ311465');
assert.equal(vinFrom('VIN\t1XKYD49X6LJ311465'),'1XKYD49X6LJ311465');
assert.equal(vinFrom('VIN: 1XKYD49X6LJ311465'),'1XKYD49X6LJ311465');
assert.equal(vinFrom('unit 533'),null);
assert.equal(vinFrom('VIN\n1XKYD49X6LJ311465\nVIN\n4V4WC9EG2LN250024'),null);
assert.throws(()=>coordinates('Charlotte, NC'),/invalid_coordinates/);
assert.throws(()=>coordinates('91,-80'),/invalid_coordinates/);
assert.deepEqual(coordinates('35.1, -80.9'),[35.1,-80.9]);
assert.equal(addressFrom('Status\nStationary\n260 Seaboard Dr, Stallings, NC 28104\nTelematics\nFUEL'), '260 Seaboard Dr, Stallings, NC 28104');
assert.equal(addressFrom('Status\nI 85, Charlotte, NC 28201\nCURRENT DRIVER\nDriver name\nTelematics'), 'I 85, Charlotte, NC 28201');
assert.equal(addressFrom('Status\nAdd Vehicle Gateway to see location data\nTelematics'), null);
assert.equal(addressFrom('Status\nIn service\nTelematics'), null);
console.log('12 collector identity/coordinate/address assertions passed');
const test=require('node:test');
const {bindVin,observationTime,stableObservation,collectWithRetries}=require('./collect.cjs');
const VIN='1XKYD49X6LJ311465',OTHER='4V4WC9EG2LN250024';
test('summary/live VIN binding rejects missing, changed and ambiguous identities',()=>{
 assert.equal(bindVin(null,`VIN ${VIN}`),VIN);assert.equal(bindVin(VIN,`VIN ${VIN}`),VIN);
 assert.throws(()=>bindVin(VIN,`VIN ${OTHER}`),/vin_changed/);
 assert.throws(()=>bindVin(null,`VIN ${VIN}\nVIN ${OTHER}`),/ambiguous_vin/);
 assert.throws(()=>bindVin(null,'VIN —'),/vin_unavailable/);
});
test('unknown time is explicit and never capture time; valid minute precision remains',()=>{
 const unknown=observationTime(null);assert.equal(unknown.precision,'unknown');assert.equal(unknown.observed_at,null);assert.equal(unknown.observed_minute_start,null);assert.equal(unknown.timezone,null);
 assert.equal(observationTime('unrecognized source').timestampReason,'unsupported_format');
 assert.equal(observationTime('Oct 7, 2026, 1:49 PM').precision,'minute');
});
test('stable coordinates do not require address or source time; raw status retained',async()=>{
 let checked=0;
 const data=await stableObservation({timestamp:async()=>({rawTimestamp:null,sourceAge:'Stationary',timestampReason:'timestamp_tooltip_unavailable'}),point:async()=>[35.1,-80.9],verifyVin:async()=>{checked++;},address:null});
 assert.equal(data.address,null);assert.equal(data.observed_at,null);assert.equal(data.precision,'unknown');assert.equal(data.sourceAge,'Stationary');assert.equal(data.timestampReason,'timestamp_tooltip_unavailable');assert.equal(checked,1);
});
test('changed point or timestamp rejects an observation rather than mixing attempts',async()=>{
 let i=0;
 await assert.rejects(stableObservation({timestamp:async()=>({rawTimestamp:null,sourceAge:null}),point:async()=>[35+(i++),-80],verifyVin:async()=>{},address:null}),/source_changed/);
 i=0;await assert.rejects(stableObservation({timestamp:async()=>({rawTimestamp:`t${i++}`,sourceAge:null}),point:async()=>[35,-80],verifyVin:async()=>{},address:null}),/source_changed/);
});
test('bounded retries use separate closed pages and retain established VIN across retries',async()=>{
 const pages=[];
 const context={newPage:async()=>{const p={setDefaultTimeout:()=>{},url:()=> 'https://app.gomotive.com/en-US/',close:async()=>{p.closed=true;}};pages.push(p);return p;}};
 let calls=0;
 const row=await collectWithRetries(context,{href:'#/fleetview/vehicles/summary/1',unit:'1'},async(p,l,bind)=>{bind(`VIN ${VIN}`);if(calls++===0)throw new Error('source_changed_during_capture');return {status:'located',lat:35,lng:-80};});
 assert.equal(row.vin,VIN);assert.equal(pages.length,2);assert.ok(pages.every(p=>p.closed));
 calls=0;await assert.rejects(collectWithRetries(context,{href:'#/fleetview/vehicles/summary/1',unit:'1'},async(p,l,bind)=>{bind(`VIN ${calls?OTHER:VIN}`);calls++;throw new Error('source_changed_during_capture');}),/vin_changed/);
});
test('unsupported raw tooltip text survives unknown-time fallback',async()=>{
 const raw='Last Tuesday at noon';
 const row=await stableObservation({timestamp:async()=>({rawTimestamp:raw,sourceAge:'Parked',timestampReason:null}),point:async()=>[35,-80],verifyVin:async()=>{},address:null});
 assert.equal(row.rawTimestamp,raw);assert.equal(row.precision,'unknown');assert.equal(row.timestampReason,'unsupported_format');
});
test('unknown observation retries to known, retains whole prior snapshot on unavailable, rejects changed VIN',async()=>{
 const context={newPage:async()=>({setDefaultTimeout:()=>{},url:()=> 'https://app.gomotive.com/en-US/',close:async()=>{}})};
 const link={href:'#/fleetview/vehicles/summary/1',unit:'1'};
 const unknown={status:'located',precision:'unknown',lat:35,lng:-80,sourceReadTime:'2026-10-08T12:00:00Z',rawTimestamp:null};
 let attempt=0;
 const known=await collectWithRetries(context,link,async(p,l,bind)=>{bind(`VIN ${VIN}`);return attempt++?{...unknown,precision:'minute',lat:36}:unknown;});
 assert.equal(attempt,2);assert.equal(known.precision,'minute');assert.equal(known.lat,36);
 attempt=0;const retained=await collectWithRetries(context,link,async(p,l,bind)=>{bind(`VIN ${VIN}`);if(attempt++)throw new Error('clipboard_write_timeout');return unknown;});
 assert.equal(retained.lat,35);assert.equal(retained.sourceReadTime,unknown.sourceReadTime);assert.equal(retained.retryReason,'clipboard_write_timeout');
 attempt=0;await assert.rejects(collectWithRetries(context,link,async(p,l,bind)=>{bind(`VIN ${attempt++?OTHER:VIN}`);return unknown;}),/vin_changed/);
});
test('elapsed age may tick while the actual observation timestamp and coordinates remain stable',async()=>{
 let n=0;
 const row=await stableObservation({timestamp:async()=>({rawTimestamp:'Oct 7, 2026, 1:49 PM',sourceAge:`1m ${n++}s`,timestampReason:null}),point:async()=>[35,-80],verifyVin:async()=>{},address:null});
 assert.equal(row.precision,'minute');assert.equal(row.sourceAge,'1m 1s');
});
const {assertLiveProvider,locationControl}=require('./collect.cjs');
test('observed Live route must retain exact provider binding',()=>{
 assertLiveProvider('https://app.gomotive.com/en-US/#/fleetview/map/vehicle/123-null-null/123/live','123');
 assert.throws(()=>assertLiveProvider('https://app.gomotive.com/en-US/#/fleetview/map/vehicle/123-null-null/456/live','123'),/vehicle_source_changed/);
 assert.throws(()=>assertLiveProvider('https://other.test/#/fleetview/map/vehicle/123-null-null/123/live','123'),/vehicle_source_changed/);
});
test('location control accepts state-only labels and no label, rejects ambiguity',async()=>{
 let count=1,labels=1,text='OH';
 const control={filter:()=>control,first:()=>control,waitFor:async()=>{},count:async()=>count,locator:()=>({count:async()=>labels,innerText:async()=>text})};
 const page={locator:selector=>{assert.equal(selector,'.container.mt-4.pos-relative');return control;}};
 assert.equal((await locationControl(page)).address,'OH');labels=0;assert.equal((await locationControl(page)).address,null);
 count=2;await assert.rejects(locationControl(page),/location_control_unavailable/);
});
