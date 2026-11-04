const test=require('node:test'),assert=require('node:assert/strict');
const {parseCard,parseCount,validateCounts,validateInventory,safeReason}=require('./collect.cjs');
const detail=(spn='00123',occurrence='0')=>`SPN ${spn} FMI 03 · Test circuit condition
First detected on Sep 25, 2026
High
Hide details
Test circuit condition
Network
J1939
Source address
11 · Test controller
First detected
Sep 25, 2026, 5:50 AM
Last observed
Oct 7, 2026, 6:59 PM
Occurrence count
${occurrence}`;
test('expanded detail preserves code strings, unknown event timestamps, and explicit zero occurrence',()=>{
 const p=parseCard('Current fault codes\n'+detail(),1);assert.equal(p.explicit_empty,false);assert.equal(p.codes.length,1);
 assert.equal(p.codes[0].spn,'00123');assert.equal(p.codes[0].fmi,'03');assert.equal(p.codes[0].occurrence_count,0);assert.equal(p.codes[0].last_observed_at,null);assert.equal(p.codes[0].timestamp_precision,'unknown');assert.equal(p.codes[0].timezone_basis,'unverified');assert.equal(p.codes[0].source_status,'Current fault codes');assert.equal(p.codes[0].provider_fault_id,null);
 assert.equal(parseCard('Current fault codes\n'+detail('00123','—'),1).codes[0].occurrence_count,null);
});
test('multiple cards and literal timestamps retained; mismatched and duplicate cards reject',()=>{
 const p=parseCard('Current fault codes\n'+detail()+'\n'+detail('00456','17'),2);assert.equal(p.codes.length,2);assert.equal(p.codes[1].occurrence_count,17);
 assert.throws(()=>parseCard('Current fault codes\n'+detail()+'\n'+detail(),2),/duplicate/);
 assert.throws(()=>parseCard('Current fault codes\n'+detail(),2),/details/);
 assert.throws(()=>parseCard('Current fault codes\n'+detail().replace('Hide details','Show details'),1),/details/);
});
test('zero means explicit current-code empty only; missing cannot be manufactured as healthy',()=>{
 const empty=parseCard('Current fault codes\nNo fault codes',0);assert.deepEqual(validateCounts(0,0,empty),{explicit_empty:true,codes:[]});
 for(const text of ['Current fault codes','No fault codes','Current fault codes\nLoading'])assert.throws(()=>parseCard(text,0));
 assert.throws(()=>validateCounts(4,2,parseCard('Current fault codes\n'+detail()+'\n'+detail('00456'),2)),/count_mismatch/);
 assert.throws(()=>validateCounts(0,1,empty),/count_mismatch/);
});
test('health directory count and exact table headers guard pagination and ambiguity',()=>{
 const s={headers:['VEHICLE OR ASSET','AVAILABILITY','DEFECTS','FAULT CODES','NEXT SERVICE','',''],footer:'Showing 1 of 2',rows:[{href:'#/fleetview/vehicles/summary/1',unit:'01',count:'2'}]};
 assert.deepEqual(validateInventory(s),{shown:1,expected:2});
 assert.throws(()=>validateInventory(s,3),/changed/);
 assert.throws(()=>validateInventory({...s,rows:[...s.rows,...s.rows]}),/duplicate/);
 assert.throws(()=>validateInventory({...s,headers:s.headers.slice(1)}),/layout/);
 assert.throws(()=>parseCount('—'),/unavailable/);assert.throws(()=>parseCount('-1'),/unavailable/);
});
test('failure logs never expose unknown browser errors',()=>{assert.equal(safeReason(new Error('password secret')),'health_data_unavailable');assert.equal(safeReason({name:'TimeoutError'}),'ui_timeout');});
test('missing field values never consume the next diagnostic label',()=>{
 const blank=detail().replace('Source address\n11 · Test controller','Source address\n').replace('First detected\nSep 25, 2026, 5:50 AM','First detected\n').replace('Last observed\nOct 7, 2026, 6:59 PM','Last observed\n');
 const code=parseCard('Current fault codes\n'+blank,1).codes[0];
 assert.equal(code.source_address,null);assert.equal(code.first_detected_text,null);assert.equal(code.last_observed_text,null);assert.equal(code.occurrence_count,0);assert.equal(code.timestamp_precision,'unknown');
});
test('observed J1708 SID and PID retain their own code namespace, never fabricate SPN',()=>{
 const sid=detail('00232','0').replace('SPN 00232','SID 00232').replace('J1939','J1708');
 const pid=detail('00110','0').replace('SPN 00110','PID 00110').replace('J1939','J1708');
 const codes=parseCard('Current fault codes\n'+sid+'\n'+pid,2).codes;
 assert.equal(codes[0].code,'SID 00232');assert.equal(codes[1].code,'PID 00110');
 assert.ok(codes.every(c=>c.spn===null&&c.fmi==='03'&&c.network==='J1708'&&c.occurrence_count===0));
 assert.ok(codes.every(c=>c.last_observed_at===null&&c.timezone_basis==='unverified'));
});

test('vitals parse source units, zero and independent missing fields',()=>{
 const {parseVitals}=require('./collect.cjs');
 assert.deepEqual(parseVitals([{label:'ODOMETER',value:'692,224.14 mi'},{label:'Engine hours',value:'23,520'}]),{odometer_miles:692224.14,engine_hours:23520});
 assert.deepEqual(parseVitals([{label:'Odometer',value:'0 mi'},{label:'Engine hours',value:'0'}]),{odometer_miles:0,engine_hours:0});
 assert.equal(parseVitals([{label:'Odometer',value:'160.9344 km'}]).odometer_miles,100);
 for(const raw of ['—','NaN','12,34 mi','-1 mi','123','999999999 mi'])assert.equal(parseVitals([{label:'Odometer',value:raw}]).odometer_miles,null);
 assert.deepEqual(parseVitals([{label:'Odometer',value:'1 mi'},{label:'Odometer',value:'2 mi'},{label:'Engine hours',value:'34 h'}]),{odometer_miles:null,engine_hours:34});
});

test('live Other details owns vitals only for exact provider and VIN',()=>{
 const {liveVitals}=require('./collect.cjs');
 const identity={href:'#/fleetview/vehicles/summary/123',unit:'example'};
 const vin='1M8GDM9AXKP042788';
 const snapshot={url:'https://app.gomotive.com/en-US/#/fleetview/map/vehicle/123-null-null/123/live',fields:[{label:'VIN',value:vin},{label:'ODOMETER',value:'692,224.14 mi'},{label:'ENGINE HOURS',value:'23,520'}]};
 assert.deepEqual(liveVitals(snapshot,identity,vin),{odometer_miles:692224.14,engine_hours:23520});
 assert.throws(()=>liveVitals(snapshot,identity,'1M8GDM9AXKP042789'),/identity/);
 assert.throws(()=>liveVitals({...snapshot,url:snapshot.url.replace('/123/live','/456/live')},identity,vin));
 assert.throws(()=>liveVitals({...snapshot,url:snapshot.url.replace('app.gomotive.com','example.test')},identity,vin));
 assert.throws(()=>liveVitals({...snapshot,fields:[...snapshot.fields,{label:'VIN',value:vin}]},identity,vin),/identity/);
});

// Reviewed VIN-less Live vitals contract, grounded on truck26 Nov4 DOM.
const {boundLiveVitals,boundLiveVitalsSnapshot}=require('./collect.cjs');
const identity={href:'#/fleetview/vehicles/summary/123',unit:'26'};
const proof={vin:null,source_vin_state:'not_displayed'};
const fields=[{label:'GROUPS',value:'0 groups'},{label:'ODOMETER',value:'548,550.82 mi'},{label:'ENGINE HOURS',value:'21,109'},{label:'MAKE/MODEL',value:'Synthetic truck'},{label:'DATA SOURCE',value:'AI Dashcam Plus'}];
const snapshot={url:'https://app.gomotive.com/en-US/#/fleetview/map/vehicle/123-null-null/123/live',fields,vin_fields:[]};

test('reviewed no-VIN Live table preserves actual odometer, hours and zero',()=>{
 assert.deepEqual(boundLiveVitals(snapshot,identity,proof),{odometer_miles:548550.82,engine_hours:21109});
 assert.deepEqual(boundLiveVitals({...snapshot,fields:[{label:'ODOMETER',value:'0 mi'},{label:'ENGINE HOURS',value:'0'}]},identity,proof),{odometer_miles:0,engine_hours:0});
 assert.deepEqual(boundLiveVitals({...snapshot,fields:[{label:'ODOMETER',value:'—'},{label:'ENGINE HOURS',value:'0'}]},identity,proof),{odometer_miles:null,engine_hours:0});
});

test('VIN-less Live never accepts a true, malformed, ambiguous or contradictory VIN',()=>{
 for(const value of ['1M8GDM9AXKP042788','PENDING-26','malformed'])assert.throws(()=>boundLiveVitals({...snapshot,vin_fields:[{label:'VIN',value}]},identity,proof),/identity_changed/);
 assert.throws(()=>boundLiveVitals({...snapshot,vin_fields:[{label:'VIN',value:''},{label:'VIN',value:''}]},identity,proof),/identity_changed/);
 assert.throws(()=>boundLiveVitals(snapshot,identity,{vin:'1M8GDM9AXKP042788',source_vin_state:null}),/identity_changed/);
 assert.throws(()=>boundLiveVitals(snapshot,identity,{vin:null,source_vin_state:'unknown'}),/identity_changed/);
 assert.throws(()=>boundLiveVitals({...snapshot,url:snapshot.url.replace('/123/live','/456/live')},identity,proof),/source_changed/);
 assert.throws(()=>boundLiveVitals({...snapshot,url:snapshot.url.replace('app.gomotive.com','foreign.example')},identity,proof),/source_changed/);
});

test('duplicate or missing vital labels do not prove a loaded Live table',()=>{
 assert.throws(()=>boundLiveVitals({...snapshot,fields:fields.filter(f=>f.label!=='ENGINE HOURS')},identity,proof),/layout_changed/);
 assert.throws(()=>boundLiveVitals({...snapshot,fields:[...fields,fields[1]]},identity,proof),/layout_changed/);
});

test('grounded VIN-less DOM selects one loaded detail table and retains hidden VIN contradictions',async()=>{
 const {chromium}=require('../motive_sync/node_modules/playwright');
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  const table=(extra='')=>`<table class="ui fixed table unstackable detail-table"><tbody><tr><td>GROUPS</td><td>0 groups</td></tr><tr><td>ODOMETER</td><td>548550.82 mi</td></tr><tr><td>ENGINE HOURS</td><td>21109</td></tr>${extra}</tbody></table>`;
  await page.setContent(table());
  let observed=await page.evaluate(boundLiveVitalsSnapshot);
  assert.equal(observed.fields.length,3);assert.deepEqual(observed.vin_fields,[]);
  await page.setContent(table('<tr style="display:none"><td>VIN</td><td>1M8GDM9AXKP042788</td></tr>'));
  observed=await page.evaluate(boundLiveVitalsSnapshot);
  assert.equal(observed.vin_fields[0].value,'1M8GDM9AXKP042788');
  await page.setContent(table()+table());
  observed=await page.evaluate(boundLiveVitalsSnapshot);assert.deepEqual(observed.fields,[]);
 }finally{await browser.close();}
});

const {readVitals}=require('./collect.cjs');
const vitalsVin='1M8GDM9AXKP042788',vitalsIdentity={href:'#/fleetview/vehicles/summary/70',unit:'70'};
async function vitalsFixture(attempts=[{}]){
 const {chromium}=require('../motive_sync/node_modules/playwright');
 const browser=await chromium.launch({headless:true,args:['--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND']});
 const raw=await browser.newContext(),pages=[],reads=[],summaries=[];
 await raw.route('**/*',async route=>{
  if(new URL(route.request().url()).origin!=='https://app.gomotive.com')return route.fulfill({contentType:'text/html',body:'<h1>Foreign</h1>'});
  const n=pages.findIndex(p=>p===route.request().frame().page()),setting=attempts[n]||attempts.at(-1);
  if(setting.network)return route.abort(typeof setting.network==='string'?setting.network:'connectionreset');
  const cells=[['Fuel type','Diesel'],['Regulated','Yes'],['Availability','Available'],['Groups','0 groups'],['Data source','ELD'],['Odometer',setting.summaryOdo||'567615 mi'],['VIN',setting.summaryVin||vitalsVin]];
  const summary=`<phx-breadcrumb><span data-testid="breadcrumb-title">70</span></phx-breadcrumb><vehicle-profile-v2-summary><phx-card class="vehicle-profile-card"><section phx-card-header><span phxcardtitle>70</span></section><div class="cells-container">${cells.map(([label,value])=>`<div class="cell"><span class="header">${label}</span><span>${value}</span></div>`).join('')}</div></phx-card></vehicle-profile-v2-summary>`;
  const liveFields=[['VIN',setting.liveVin||vitalsVin],['ODOMETER',setting.odo??'567618.88 mi'],...(setting.delayedHours||setting.lateWrongVin?[]:[['ENGINE HOURS',setting.hours??'104']])];
  const table=`<table class="detail-table"><tbody>${liveFields.map(([label,value])=>`<tr><td>${label}</td><td>${value}</td></tr>`).join('')}${setting.duplicateLabel?'<tr><td>ENGINE HOURS</td><td>105</td></tr>':''}</tbody></table>`;
  const liveHash=`#/fleetview/map/vehicle/${setting.wrongProvider?'71':'70'}-null-null/${setting.wrongProvider?'71':'70'}/live`;
  const script=`<script>document.querySelector('a').onclick=event=>{event.preventDefault();window.fixtureRead();${setting.foreign?"location.assign('https://evil.invalid/live');":`location.hash=${JSON.stringify(liveHash)};document.querySelector('main').innerHTML='Loading';setTimeout(()=>{document.querySelector('main').innerHTML=${JSON.stringify(table+(setting.duplicateTable?table:'')+(setting.liveExtra||''))};${setting.lateWrongVin?`setTimeout(()=>{document.querySelector('td + td').textContent='1M8GDM9AXKP042789'},50);`:''}${setting.delayedHours?`setTimeout(()=>{document.querySelector('tbody').insertAdjacentHTML('beforeend','<tr><td>ENGINE HOURS</td><td>104</td></tr>')},50);`:''}},${setting.timeout?10000:0});`}};</script>`;
  await route.fulfill({contentType:'text/html',body:`<main>${summary}${setting.summaryExtra||''}<a href="${liveHash}">Live</a></main>${script}`});
 });
 const context={async newPage(){
  const n=pages.length,setting=attempts[n]||attempts.at(-1);
  if(setting.latePage)await new Promise(resolve=>setTimeout(resolve,setting.latePage));
  const page=await raw.newPage();pages.push(page);
  await page.exposeBinding('fixtureRead',()=>reads.push(n));
  const evaluate=page.evaluate.bind(page);page.evaluate=async(fn,...args)=>{
   if(setting.unknown&&fn.name==='liveVitalsSnapshot')throw new Error('fixture_unknown');
   const result=await evaluate(fn,...args);
   if(fn.name==='summarySnapshot')summaries.push({n,at:Date.now()});return result;
  };return page;
 }};
 return {browser,context,pages,reads,summaries};
}
async function withVitals(attempts,action){const f=await vitalsFixture(attempts);try{await action(f);}finally{await f.browser.close();}}
const readFixture=f=>readVitals(f.context,vitalsIdentity,vitalsVin,{timeoutMs:8000,liveTimeoutMs:180});
test('fresh Live retry recovers available precise mileage and104hours after first Timeout',async()=>{
 await withVitals([{timeout:true},{}],async f=>{
  const value=await readFixture(f);assert.equal(value.odometer_miles,567618.88);assert.equal(value.engine_hours,104);
  assert.deepEqual(f.reads,[0,1]);assert.equal(f.pages.length,2);assert.ok(f.pages.every(p=>p.isClosed()));
 });
});
test('two Live Timeouts retain latest verified summary value and original read timestamp',async()=>{
 await withVitals([{timeout:true},{timeout:true,summaryOdo:'567616 mi'}],async f=>{
  const value=await readFixture(f);assert.equal(value.odometer_miles,567616);assert.equal(value.engine_hours,null);
  assert.deepEqual(f.reads,[0,1]);assert.ok(Date.parse(value.source_read_at)<Date.now()-150);assert.ok(f.pages.every(p=>p.isClosed()));
 });
});
test('second transient failure before summary preserves the first verified summary',async()=>{
 await withVitals([{timeout:true},{network:true}],async f=>{
  const value=await readFixture(f);assert.equal(value.odometer_miles,567615);assert.equal(value.engine_hours,null);
  assert.deepEqual(f.reads,[0]);assert.ok(Date.parse(value.source_read_at)<Date.now()-150);assert.ok(f.pages.every(p=>p.isClosed()));
 });
});
test('initial pre-Live navigation failure is terminal without retry or fabricated summary',async()=>{
 await withVitals([{network:true},{network:true}],async f=>{
  await assert.rejects(readFixture(f),/CONNECTION_RESET/);assert.equal(f.pages.length,1);assert.ok(f.pages.every(p=>p.isClosed()));
 });
});
for(const [name,setting,reason] of [
 ['wrong summary VIN',{summaryVin:'1M8GDM9AXKP042789'},'vehicle_identity_changed'],
 ['VIN contradiction rendering during timed-out hours wait',{lateWrongVin:true},'vehicle_identity_changed'],
 ['non-allowlisted network error',{network:'failed'},'ERR_FAILED'],
 ['wrong Live VIN',{liveVin:'1M8GDM9AXKP042789'},'vehicle_identity_changed'],
 ['wrong provider',{wrongProvider:true},'vehicle_source_changed'],
 ['foreign origin',{foreign:true},'session_lost'],
 ['duplicate table',{duplicateTable:true},'vehicle_vitals_layout_changed'],
 ['duplicate label',{duplicateLabel:true},'vehicle_vitals_layout_changed'],
 ['unknown error',{unknown:true},'fixture_unknown'],
])test(`${name} rejects on one page without retry or summary fallback`,async()=>{
 await withVitals([setting],async f=>{await assert.rejects(readFixture(f),new RegExp(reason));assert.equal(f.pages.length,1);assert.ok(f.pages[0].isClosed());});
});
test('Live waits for delayed engine hours after VIN and table have rendered',async()=>{
 await withVitals([{delayedHours:true}],async f=>{const value=await readFixture(f);assert.equal(value.engine_hours,104);assert.equal(f.pages.length,1);});
});
for(const [label,setting,expected] of [['zero',{odo:'0 mi',hours:'0'},[0,0]],['missing',{odo:'—',hours:'—'},[null,null]],['malformed',{odo:'bad mi',hours:'bad'},[null,null]]])test(`${label} vital field values do not trigger retries`,async()=>{
 await withVitals([setting],async f=>{const value=await readFixture(f);assert.deepEqual([value.odometer_miles,value.engine_hours],expected);assert.equal(f.pages.length,1);});
});
test('per-vehicle deadline is shared across attempts and closes every created page',async()=>{
 await withVitals([{timeout:true},{timeout:true}],async f=>{
  await assert.rejects(readVitals(f.context,vitalsIdentity,vitalsVin,{timeoutMs:450,liveTimeoutMs:180}),e=>e.name==='TimeoutError');
  await new Promise(resolve=>setTimeout(resolve,60));assert.ok(f.pages.every(p=>p.isClosed()));assert.ok(f.pages.length<=2);
 });
});
test('page returned after per-vehicle deadline is disposed without navigation',async()=>{
 await withVitals([{latePage:100}],async f=>{
  await assert.rejects(readVitals(f.context,vitalsIdentity,vitalsVin,{timeoutMs:20,liveTimeoutMs:10}),e=>e.name==='TimeoutError');
  await new Promise(resolve=>setTimeout(resolve,250));assert.equal(f.pages.length,1);assert.ok(f.pages[0].isClosed());assert.equal(f.reads.length,0);
 });
});
for(const [name,markup] of [
 ['password','<input type="password" name="user_password">'],
 ['autocomplete OTP','<form><input name="securityCheck" autocomplete="section-login one-time-code"></form>'],
 ['named OTP','<form><input name="otp"></form>'],
 ['named TOTP','<form><input name="totp"></form>'],
 ['verification code','<form><input name="verification_code"></form>'],
 ['known reCAPTCHA','<iframe src="https://www.google.com/recaptcha/api2/anchor"></iframe>'],
 ['known hCaptcha','<iframe src="https://newassets.hcaptcha.com/captcha/v1/example"></iframe>'],
 ['known Cloudflare challenge','<iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/example"></iframe>'],
])test(`same-origin Live ${name} overlay is terminal without retry or summary fallback`,async()=>{
 await withVitals([{liveExtra:markup}],async f=>{
  await assert.rejects(readFixture(f),/source_authentication_required/);assert.equal(f.pages.length,1);assert.deepEqual(f.reads,[0]);assert.ok(f.pages[0].isClosed());
 });
});
test('authentication guard runs before the observed Live click',async()=>{
 await withVitals([{summaryExtra:'<form><input name="otp"></form>'}],async f=>{
  await assert.rejects(readFixture(f),/source_authentication_required/);assert.equal(f.pages.length,1);assert.deepEqual(f.reads,[]);
 });
});
test('a same-origin authentication overlay detected after a Live timeout is never retried',async()=>{
 await withVitals([{lateWrongVin:false,liveExtra:'<form><input name="verificationCode"></form>',delayedHours:true}],async f=>{
  // Suppress the hours row so the guard must catch the overlay on timeout.
  const newPage=f.context.newPage.bind(f.context);f.context.newPage=async()=>{const page=await newPage();await page.addInitScript(()=>{const native=window.setTimeout;window.setTimeout=(fn,ms)=>native(fn,ms===50?10000:ms);});return page;};
  await assert.rejects(readFixture(f),/source_authentication_required/);assert.equal(f.pages.length,1);assert.deepEqual(f.reads,[0]);
 });
});
for(const [name,markup] of [
 ['ordinary app search','<input name="search" type="search"><input name="code" autocomplete="off">'],
 ['unrelated iframe','<iframe src="https://evil.invalid/challenge/code"></iframe>'],
 ['lookalike CAPTCHA host','<iframe src="https://www.google.com.evil.invalid/recaptcha/api2/anchor"></iframe>'],
 ['unrelated known-host path','<iframe src="https://www.google.com/help/challenge"></iframe>'],
])test(`${name} does not trigger source authentication guard`,async()=>{
 await withVitals([{liveExtra:markup}],async f=>{const value=await readFixture(f);assert.equal(value.engine_hours,104);assert.equal(f.pages.length,1);});
});
test('rejected active attempt disposal is terminal before any fresh retry page',async()=>{
 await withVitals([{timeout:true},{}],async f=>{
  const create=f.context.newPage.bind(f.context);f.context.newPage=async()=>{const page=await create();page.close=async()=>{throw new Error('fixture_close_failed');};return page;};
  await assert.rejects(readFixture(f),/fixture_close_failed/);assert.equal(f.pages.length,1);assert.deepEqual(f.reads,[0]);assert.equal(f.pages[0].isClosed(),false);
 });
});
test('hung active attempt disposal consumes shared budget and prevents fresh retry page',async()=>{
 await withVitals([{timeout:true},{}],async f=>{
  const create=f.context.newPage.bind(f.context);f.context.newPage=async()=>{const page=await create();page.close=()=>new Promise(()=>{});return page;};
  await assert.rejects(readVitals(f.context,vitalsIdentity,vitalsVin,{timeoutMs:700,liveTimeoutMs:180}),e=>e.name==='TimeoutError');assert.equal(f.pages.length,1);assert.deepEqual(f.reads,[0]);
 });
});
