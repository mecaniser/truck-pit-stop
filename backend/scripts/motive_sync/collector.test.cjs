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
const {newTooltip}=require('./collect.cjs');
test('status hover owns only a new unique tooltip, ignores persistent unrelated content',()=>{
 assert.equal(newTooltip(['Help tip'],['Help tip','Oct 7, 2026, 1:49 PM']),'Oct 7, 2026, 1:49 PM');
 assert.equal(newTooltip(['Help tip'],['Help tip','Yesterday afternoon']),'Yesterday afternoon');
 assert.equal(newTooltip(['Oct 7, 2026, 1:49 PM'],['Oct 7, 2026, 1:49 PM']),null);
 assert.throws(()=>newTooltip(['Help tip'],['Help tip','First new','Second new']),/unowned_timestamp_tooltip/);
});
const {leafTooltipTexts}=require('./collect.cjs');
test('observed nested tooltip wrappers count once but distinct copies still reject',()=>{
 const leaf={innerText:'Oct 7, 2026, 1:49 PM',querySelector:()=>null};
 const wrapper={innerText:leaf.innerText,querySelector:()=>leaf};
 assert.deepEqual(leafTooltipTexts([wrapper,leaf]),[leaf.innerText]);
 assert.equal(newTooltip([],leafTooltipTexts([wrapper,leaf])),leaf.innerText);
 assert.throws(()=>newTooltip([],leafTooltipTexts([leaf,{...leaf}])),/unowned_timestamp_tooltip/);
});
const {speedFromParts,readSpeed}=require('./collect.cjs');
test('speed parsing accepts explicit zero and bounded decimals, never status or unsupported units',()=>{
 assert.deepEqual(speedFromParts(' 0 ',' MPH '),{speed_mph:0,speedText:'0 MPH',speedReason:null});
 assert.equal(speedFromParts('65.5','mph').speed_mph,65.5);
 for(const value of ['NaN','Infinity','-1','251','65 mph','60 61','',true])assert.equal(speedFromParts(value,'MPH').speed_mph,null);
 assert.equal(speedFromParts('65','km/h').speedReason,'speed_unit_unsupported');
 for(const status of ['Stationary','Parked','In motion'])assert.equal(speedFromParts(status,null).speed_mph,null);
});
test('speed selector is scoped to the unique live vehicle panel and rejects ambiguity',async()=>{
 let sections=1,speeds=1,values=1,units=1;
 const speed={filter:()=>speed,count:async()=>speeds,locator:s=>({count:async()=>s==='.value'?values:units,innerText:async()=>s==='.value'?'65':'MPH'})};
 const section={filter:()=>section,count:async()=>sections,locator:s=>{assert.equal(s,'.current-location [data-e2e="speed-info"]');return speed;}};
 const page={locator:s=>{assert.equal(s,'section.driver-location-info');return section;}};
 assert.equal((await readSpeed(page)).speed_mph,65);
 speeds=0;assert.equal((await readSpeed(page)).speedReason,'speed_unavailable');
 speeds=2;assert.equal((await readSpeed(page)).speedReason,'speed_ambiguous');
 speeds=1;values=2;assert.equal((await readSpeed(page)).speedReason,'speed_ambiguous');
 values=1;units=2;assert.equal((await readSpeed(page)).speedReason,'speed_ambiguous');
 sections=2;assert.equal((await readSpeed(page)).speedReason,'speed_ambiguous');
});
test('stable speed shares verified source observation and unknown time drops numeric speed',async()=>{
 const base={timestamp:async()=>({rawTimestamp:'Oct 7, 2026, 1:49 PM',sourceAge:'1m',timestampReason:null}),point:async()=>[35,-80],verifyVin:async()=>{},address:null,speed:async()=>speedFromParts('0','MPH')};
 const known=await stableObservation(base);assert.equal(known.speed_mph,0);assert.equal(known.precision,'minute');
 const unknown=await stableObservation({...base,timestamp:async()=>({rawTimestamp:null,sourceAge:'Stationary',timestampReason:'timestamp_unavailable'})});
 assert.equal(unknown.speed_mph,null);assert.equal(unknown.speedText,'0 MPH');assert.equal(unknown.speedReason,'speed_timestamp_unavailable');
 const missing=await stableObservation({...base,speed:async()=>({speed_mph:null,speedText:null,speedReason:'speed_unavailable'})});assert.equal(missing.status,'located');assert.equal(missing.speed_mph,null);
});
test('changing speed discards whole observation and never copies it into a retried location',async()=>{
 let n=0;
 const base={timestamp:async()=>({rawTimestamp:'Oct 7, 2026, 1:49 PM',sourceAge:'1m',timestampReason:null}),point:async()=>[35,-80],verifyVin:async()=>{},address:null};
 await assert.rejects(stableObservation({...base,speed:async()=>speedFromParts(String(n++),'MPH')}),/source_changed/);
 const context={newPage:async()=>({setDefaultTimeout:()=>{},url:()=> 'https://app.gomotive.com/en-US/',close:async()=>{}})};
 let attempt=0;
 const row=await collectWithRetries(context,{href:'#/fleetview/vehicles/summary/1',unit:'1'},async(p,l,bind)=>{bind(`VIN ${VIN}`);return stableObservation({...base,point:async()=>[36,-81],speed:attempt++?async()=>speedFromParts('0','MPH'):async()=>speedFromParts(String(n++),'MPH')});});
 assert.equal(row.speed_mph,0);assert.equal(row.lat,36);assert.equal(attempt,2);
});
test('final retry may retain stable location while omitting unstable speed',async()=>{
 let n=0,verified=0;
 const base={timestamp:async()=>({rawTimestamp:'Oct 7, 2026, 1:49 PM',sourceAge:'1m',timestampReason:null}),point:async()=>[35,-80],verifyVin:async()=>{verified++;},address:null,speed:async()=>speedFromParts(String(n++),'MPH'),allowUnstableSpeed:true};
 const location=await stableObservation(base);
 assert.equal(location.lat,35);assert.equal(location.speed_mph,null);assert.equal(location.speedReason,'speed_ambiguous');assert.equal(verified,1);
 let point=0;await assert.rejects(stableObservation({...base,point:async()=>[35+point++,-80]}),/source_changed/);
 await assert.rejects(stableObservation({...base,verifyVin:async()=>{throw new Error('vin_changed');}}),/vin_changed/);
});
const {canonicalInlineDate}=require('./collect.cjs');
test('inline dates normalize only case and whitespace, never borrow a year or accept substrings',()=>{
 assert.equal(canonicalInlineDate(' OCT  13,\n2026, 5:34 pm '),'Oct 13, 2026, 5:34 PM');
 for(const value of ['Last updated Oct 13, 2026, 5:34 PM','Disconnected Oct 13, 2026, 5:34 PM','Oct 13, 5:34 PM','Yesterday at 5:34 PM','10/13/2026, 5:34:00 PM',null])assert.equal(canonicalInlineDate(value),null);
});
test('inline location-only clock never promotes speed and preserves minute bounds',async()=>{
 const row=await stableObservation({timestamp:async()=>({rawTimestamp:'Oct 13, 2026, 5:34 PM',sourceAge:null,timestampReason:null,timestampBasis:'inline_location'}),point:async()=>[35,-80],verifyVin:async()=>{},address:null,speed:async()=>speedFromParts('0','MPH')});
 assert.equal(row.precision,'minute');assert.equal(row.observed_at,null);
 assert.equal(row.observed_minute_start,'2026-10-13T21:34:00.000Z');assert.equal(row.observed_minute_end,'2026-10-13T21:35:00.000Z');
 assert.equal(row.timestampBasis,'inline_location');assert.equal(row.speed_mph,null);
 assert.equal(row.speedText,'0 MPH');assert.equal(row.speedReason,'speed_timestamp_location_only');
});
test('timestamp ownership basis cannot change around the same coordinate capture',async()=>{
 let n=0;
 await assert.rejects(stableObservation({timestamp:async()=>({rawTimestamp:'Oct 13, 2026, 5:34 PM',sourceAge:null,timestampReason:null,...(n++?{timestampBasis:'inline_location'}:{})}),point:async()=>[35,-80],verifyVin:async()=>{},address:null}),/source_changed/);
});

const {readVehicleVinOnce,readVehicleVin}=require('./collect_trips.cjs');
const identityReadDiagnostics=require('./vehicle_identity_diagnostics.cjs');
const identityLink={href:'#/fleetview/vehicles/summary/123',unit:'synthetic'};
function identityReadFixture({failAt,error=Object.assign(new Error('PRIVATE_SOURCE'),{name:'TimeoutError'}),cleanupError,url:overrideUrl,body='VIN\n'+VIN}={}) {
 const calls=[];let url='about:blank';
 const action=async stage=>{calls.push(stage);if(stage===failAt)throw error;};
 const page={
  setDefaultTimeout(value){calls.push(['default_timeout',value]);},
  async goto(value,options){calls.push(['goto_options',options]);await action('goto_summary');url=overrideUrl||value;},
  getByRole(role,options){calls.push(['role',role,options]);return {filter(options){calls.push(['filter',options]);return {first(){return {waitFor:()=>action('wait_live_link')};}};}};},
  async waitForFunction(fn,arg,options){calls.push(['vin_wait_options',options]);await action('vin_presence_wait');},
  url(){return url;},
  locator(selector){assert.equal(selector,'body');return {innerText:async()=>{await action('read_summary');return body;}};},
  async close(){calls.push('cleanup');if(cleanupError)throw cleanupError;},
 };
 return {calls,page,error,context:{newPage:async()=>{await action('new_page');return page;}}};
}
for(const [stage,route] of [['new_page','unavailable'],['goto_summary','about_blank'],['wait_live_link','expected_summary'],['read_summary','expected_summary']])test(`VIN read diagnostics identify ${stage} without changing the thrown error`,async()=>{
 const f=identityReadFixture({failAt:stage});const seen=[];
 await assert.rejects(readVehicleVinOnce(f.context,identityLink,{onStage:s=>seen.push(s)}),e=>e===f.error);
 assert.deepEqual(identityReadDiagnostics.diagnostic(f.error),{identity_step:stage,identity_route:route});
 assert.equal(f.calls.filter(x=>x==='cleanup').length,stage==='new_page'?0:1);
 assert.equal(seen.at(-1),stage==='new_page'?'new_page':'cleanup');
});
test('VIN diagnostic observers receive only static stages and do not alter successful reads or deadlines',async()=>{
 const f=identityReadFixture(),seen=[];
 assert.equal(await readVehicleVinOnce(f.context,identityLink,{onStage:s=>seen.push(s)}),VIN);
 assert.deepEqual(seen,['new_page','goto_summary','wait_live_link','vin_presence_wait','route_check','read_summary','cleanup']);
 assert.deepEqual(f.calls.find(x=>Array.isArray(x)&&x[0]==='default_timeout'),['default_timeout',15000]);
 assert.deepEqual(f.calls.find(x=>Array.isArray(x)&&x[0]==='goto_options')[1],{waitUntil:'domcontentloaded',timeout:45000});
 assert.deepEqual(f.calls.find(x=>Array.isArray(x)&&x[0]==='vin_wait_options')[1],{timeout:15000});
});
test('swallowed optional VIN wait remains swallowed and still reads the original summary',async()=>{
 const f=identityReadFixture({failAt:'vin_presence_wait'});
 assert.equal(await readVehicleVinOnce(f.context,identityLink),VIN);
 assert.equal(identityReadDiagnostics.diagnostic(f.error),null);
 assert.ok(f.calls.includes('read_summary'));assert.equal(f.calls.at(-1),'cleanup');
});
test('VIN source guard and existing foreign-origin timeout conversion retain their original outcomes',async()=>{
 const wrong=identityReadFixture({url:'https://app.gomotive.com/en-US/#/different'});
 await assert.rejects(readVehicleVinOnce(wrong.context,identityLink),e=>{
  assert.equal(e.message,'vehicle_source_changed');assert.deepEqual(identityReadDiagnostics.diagnostic(e),{identity_step:'route_check',identity_route:'other_app_route'});return true;
 });
 const foreign=identityReadFixture({url:'https://auth.gomotive.com/login/lookup',failAt:'wait_live_link'});
 await assert.rejects(readVehicleVinOnce(foreign.context,identityLink),e=>{
  assert.equal(e.message,'session_lost');assert.deepEqual(identityReadDiagnostics.diagnostic(e),{identity_step:'wait_live_link',identity_route:'unexpected_origin'});return true;
 });
});
test('successful cleanup preserves the primary failing step; failing cleanup overrides exactly as before',async()=>{
 const primary=identityReadFixture({failAt:'wait_live_link'});
 await assert.rejects(readVehicleVinOnce(primary.context,identityLink),e=>e===primary.error);
 assert.equal(identityReadDiagnostics.diagnostic(primary.error).identity_step,'wait_live_link');
 const cleanupError=new Error('PRIVATE_CLEANUP');
 const both=identityReadFixture({failAt:'wait_live_link',cleanupError});
 await assert.rejects(readVehicleVinOnce(both.context,identityLink),e=>e===cleanupError);
 assert.equal(identityReadDiagnostics.diagnostic(cleanupError).identity_step,'cleanup');
 assert.equal(identityReadDiagnostics.diagnostic(both.error).identity_step,'wait_live_link');
 const only=identityReadFixture({cleanupError});
 await assert.rejects(readVehicleVinOnce(only.context,identityLink),e=>e===cleanupError);
 assert.equal(identityReadDiagnostics.diagnostic(cleanupError).identity_step,'cleanup');
});
test('throwing or rejected observers cannot replace successful reads or frozen source errors',async()=>{
 for(const onStage of [()=>{throw new Error('PRIVATE_OBSERVER');},()=>Promise.reject(new Error('PRIVATE_OBSERVER'))]) {
  assert.equal(await readVehicleVinOnce(identityReadFixture().context,identityLink,{onStage}),VIN);
  const error=Object.freeze(Object.assign(new Error('PRIVATE_FROZEN'),{name:'TimeoutError'}));
  await assert.rejects(readVehicleVinOnce(identityReadFixture({failAt:'wait_live_link',error}).context,identityLink,{onStage}),e=>e===error);
  assert.equal(identityReadDiagnostics.diagnostic(error).identity_step,'wait_live_link');
 }
 const primitive=identityReadFixture({failAt:'new_page',error:'PRIVATE_PRIMITIVE'});
 await assert.rejects(readVehicleVinOnce(primitive.context,identityLink),e=>e==='PRIVATE_PRIMITIVE');
 assert.equal(await readVehicleVinOnce(identityReadFixture().context,identityLink,{get onStage(){throw new Error('PRIVATE_OBSERVER');}}),VIN);
});
test('diagnostic classification and attachment failure cannot mask a source error',async()=>{
 const f=identityReadFixture({failAt:'goto_summary'});let reads=0;
 const link={get href(){if(++reads>1)throw new Error('PRIVATE_METADATA');return identityLink.href;}};
 await assert.rejects(readVehicleVinOnce(f.context,link),e=>e===f.error);
 const unavailable=identityReadFixture({failAt:'wait_live_link'});unavailable.page.url=()=>{throw new Error('PRIVATE_URL');};
 await assert.rejects(readVehicleVinOnce(unavailable.context,identityLink),e=>{
  // Existing timeout-to-session conversion also reads url and preserves that failure.
  assert.equal(e.message,'PRIVATE_URL');assert.equal(identityReadDiagnostics.diagnostic(e).identity_route,'unavailable');return true;
 });
});
test('outer VIN retry behavior remains exactly three transient attempts and one fatal attempt',async()=>{
 let attempts=0;const transient=identityReadFixture({failAt:'wait_live_link'});
 const context={newPage:async()=>{attempts++;return transient.page;}};
 await assert.rejects(readVehicleVin(context,identityLink),e=>e===transient.error);
 assert.equal(attempts,3);assert.equal(transient.calls.filter(x=>x==='cleanup').length,3);
 attempts=0;const fatal=identityReadFixture({body:'VIN\n'+VIN+'\nVIN\n'+OTHER});
 await assert.rejects(readVehicleVin({newPage:async()=>{attempts++;return fatal.page;}},identityLink),/ambiguous_vin/);
 assert.equal(attempts,1);assert.equal(fatal.calls.filter(x=>x==='cleanup').length,1);
});
