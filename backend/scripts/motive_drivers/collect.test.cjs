const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {parseRanges,classify,directoryColumns,validateDirectory,validateSummaryIdentity,summaryDomReady,parseSummary,readDriverVehicleVin,canDeferReviewedPreSummaryIdentity,readBeforeSummaryIdentity,safeReason}=require('./collect.cjs');
const ranges=parseRanges('Performance ranges\nFair\nGood\nExcellent\nFair 50 – 84 Good 85 – 95 Excellent 96 – 100');
const snapshot=()=>({safety_score_texts:['82'],safety_lines:['Safety Score','SEP 28, 2026 - OCT 4, 2026','82','Top behaviors impacting score','Close following','-9','Stop sign violation','-4.7','Speeding','-4'],coaching_annotation:true,fuel_text:'Fuel performance LAST 30 DAYS 41.4% UTILIZATION Summary Active time 68h 14m Idle time 96h 26m',coaching_text:'Driver needs coaching Never coached 4',event_headers:['DATE (MDY EDT) / LOCATION','VEHICLE ID / MMY','STATUS','BEHAVIOR / SEVERITY'],events:[['Oct 9, 2026, 2:29 PM\n—','01\nFRHT 2019','Pending review','Stop sign violation\nN/A']]});
test('Motive source ranges determine bands, including exact boundaries',()=>{
 assert.deepEqual([50,84,85,95,96,100].map(s=>classify(s,ranges).band),['red','red','yellow','yellow','green','green']);
 assert.equal(classify(null,ranges).band,'unknown');assert.equal(classify(0,ranges).band,'unknown');
 const changed=parseRanges('Fair 50-66 Good 67-83 Excellent 84-100');assert.equal(classify(84,changed).band,'green');
});
test('rejects missing duplicate overlapping gapped and reordered source ranges',()=>{
 for(const text of ['Fair 50-84 Good 85-95','Fair 50-85 Good 85-95 Excellent 96-100','Fair 50-84 Good 86-95 Excellent 96-100','Good 50-84 Fair 85-95 Excellent 96-100','Fair 0-84 Good 85-95 Excellent 96-100'])assert.throws(()=>parseRanges(text));
});
test('parses source summary without treating graph coaching annotation as band',()=>{
 const data=parseSummary(snapshot(),ranges);assert.equal(data.safety.score,82);assert.equal(data.safety.band,'red');assert.equal(data.safety.band_label,'Fair (50–84)');assert.equal(data.safety.coaching_label,'Coaching');
 assert.deepEqual(data.safety.top_behaviors.map(b=>b.score_impact),[-9,-4.7,-4]);assert.equal(data.fuel.utilization_percent,41.4);assert.equal(data.fuel.active_time_text,'68h 14m');assert.equal(data.coaching.open_count,4);assert.equal(data.recent_events[0].location,null);assert.equal(data.recent_events[0].severity,null);assert.equal(data.coverage,'partial');
});
test('preserves explicit zero and unknown readings independently',()=>{
 const source=snapshot();source.safety_lines[2]='0';source.safety_score_texts=['0'];source.fuel_text='Fuel performance LAST 30 DAYS 0% UTILIZATION Active time 0h 0m Idle time 0h 0m';
 const value=parseSummary(source,ranges);assert.equal(value.safety.score,0);assert.equal(value.safety.band,'unknown');assert.equal(value.fuel.utilization_percent,0);
 const missing=parseSummary({},ranges);assert.equal(missing.sections.safety,'unavailable');assert.equal(missing.sections.fuel,'unavailable');assert.equal(missing.sections.recent_events,'unavailable');
});
test('preserves the observed bare-zero fuel state without inventing a driver score',()=>{
 const source={fuel_text:'Fuel performance LAST 30 DAYS 0 UTILIZATION Summary Active time 0m Idle time 0m'};
 const value=parseSummary(source,ranges);
 assert.equal(value.sections.fuel,'available');assert.equal(value.fuel.utilization_percent,0);
 assert.equal(value.fuel.active_time_text,'0m');assert.equal(value.fuel.idle_time_text,'0m');
 assert.equal(value.sections.safety,'unavailable');assert.equal(value.sections.coaching,'unavailable');
});
test('fuel rejects malformed, duplicate, missing, out-of-range and nonzero unitted readings',()=>{
 for(const reading of ['-10%','.5%','1.2.3%','41.4% 20%','101%','Infinity%','NaN%','','20','0.0','10','-0']) {
  const source=snapshot();source.fuel_text=`Fuel performance LAST 30 DAYS ${reading} UTILIZATION Summary Active time 1h Idle time 1h`;
  const result=parseSummary(source,ranges);assert.equal(result.sections.fuel,'unavailable',reading);assert.equal(result.fuel.utilization_percent,undefined,reading);
 }
 const source=snapshot();source.fuel_text+=' 20% UTILIZATION';assert.equal(parseSummary(source,ranges).sections.fuel,'unavailable');
});
test('ambiguous scores are unavailable and malformed impact/event rows fail',()=>{
 const a=snapshot();a.safety_score_texts.push('100');assert.equal(parseSummary(a,ranges).sections.safety,'unavailable');
 const b=snapshot();b.safety_lines.push('Unexpected metric');assert.throws(()=>parseSummary(b,ranges));
 const c=snapshot();c.events[0][0]='unknown time';assert.throws(()=>parseSummary(c,ranges));
});
const cell=(text,href=null)=>({text,anchors:href?[{href,text}]:[]});
const directory=()=>({headers:['DRIVER NAME / ID','VEHICLE ID'],footer:'Showing 2 of 2',rows:[{cells:[cell('Sample Driver','#/fleetview/drivers/summary/1'),cell('9','#/fleetview/vehicles/summary/9')]},{cells:[cell('Unassigned Driver','#/fleetview/drivers/summary/2'),cell('')]}]});
test('directory joins stable provider identities in the same source row',()=>{const data=validateDirectory(directory());assert.equal(data[0].provider_driver_id,'1');assert.equal(data[0].provider_vehicle_id,'9');assert.equal(data[1].provider_vehicle_id,null);});
test('directory uses named columns with a leading checkbox and trailing utility columns',()=>{
 const source=directory();source.headers.unshift('');source.headers.push('ASSET ID','');
 for(const row of source.rows){row.cells.unshift(cell(''));row.cells.push(cell(''),cell(''));}
 assert.deepEqual(directoryColumns(source.headers),{driver:1,vehicle:2});
 assert.deepEqual(validateDirectory(source),validateDirectory(directory()));
});
test('directory follows uniquely labeled columns rather than global links or numeric positions',()=>{
 const source=directory();source.headers=['VEHICLE ID','', 'DRIVER NAME / ID'];
 for(const row of source.rows)row.cells=[row.cells[1],cell('Utility link','#/fleetview/drivers/summary/999'),row.cells[0]];
 assert.deepEqual(validateDirectory(source),validateDirectory(directory()));
});
test('rejects missing duplicate or merged directory headers and mismatched cells',()=>{
 const missing=directory();missing.headers[0]='ASSET ID';assert.throws(()=>validateDirectory(missing),/driver_directory_layout/);
 const duplicate=directory();duplicate.headers.push('DRIVER NAME / ID');assert.throws(()=>validateDirectory(duplicate),/driver_directory_layout/);
 const duplicatedVehicle=directory();duplicatedVehicle.headers.push('vehicle id');assert.throws(()=>validateDirectory(duplicatedVehicle),/driver_directory_layout/);
 const count=directory();count.rows[0].cells.unshift(cell(''));assert.throws(()=>validateDirectory(count),/driver_directory_layout/);
 for(const key of ['colspan','rowspan']){const merged=directory();merged.rows[0].cells[0][key]=2;assert.throws(()=>validateDirectory(merged),/driver_directory_layout/);}
});
test('rejects ambiguous or missing same-cell links instead of inferring assignment from text',()=>{
 const driver=directory();driver.rows[0].cells[0].anchors.push({href:'#/fleetview/drivers/summary/3',text:'Other'});assert.throws(()=>validateDirectory(driver),/driver_identity_invalid/);
 const vehicle=directory();vehicle.rows[0].cells[1].anchors.push({href:'#/fleetview/vehicles/summary/10',text:'10'});assert.throws(()=>validateDirectory(vehicle),/driver_identity_invalid/);
 const missing=directory();missing.rows[0].cells[1].anchors=[];assert.throws(()=>validateDirectory(missing),/driver_identity_invalid/);
});
test('rejects incomplete duplicate and ambiguous assignment directories',()=>{
 const a=directory();a.footer='Showing 2 of 3';assert.throws(()=>validateDirectory(a));
 const b=directory();b.rows[1].cells[0]=b.rows[0].cells[0];assert.throws(()=>validateDirectory(b));
 const c=directory();c.rows[1].cells[1]=c.rows[0].cells[1];assert.throws(()=>validateDirectory(c));
 const d=directory();d.rows[0].cells[0].anchors[0].href='https://attacker.invalid/drivers/summary/1';assert.throws(()=>validateDirectory(d));
});
test('error logging never emits provider content or credentials',()=>{assert.equal(safeReason(new Error('secret driver payload')),'driver_collection_failed');});

test('complete empty directory remains valid to clear provider assignment projection',()=>{assert.deepEqual(validateDirectory({headers:['DRIVER NAME / ID','VEHICLE ID'],footer:'Showing 0 of 0',rows:[]}),[]);});


test('recent safety events use named columns and ignore the trailing utility cell',()=>{
 const source=snapshot();source.event_headers.push('');source.events[0].push('Video controls');
 assert.deepEqual(parseSummary(source,ranges).recent_events,parseSummary(snapshot(),ranges).recent_events);
});
test('recent safety events reject ambiguous headers and row alignment changes',()=>{
 const duplicate=snapshot();duplicate.event_headers.push('STATUS');duplicate.events[0].push('Pending');
 assert.equal(parseSummary(duplicate,ranges).sections.recent_events,'unavailable');
 const truncated=snapshot();truncated.event_headers.push('');assert.throws(()=>parseSummary(truncated,ranges),/event_layout/);
});
test('explicit driver-specific empty events are preserved separately from unavailable',()=>{
 const source=snapshot();source.events=[];source.event_empty_texts=['There are no safety events for Sample Driver.'];
 const result=parseSummary(source,ranges,'Sample Driver');
 assert.equal(result.sections.recent_events,'empty');assert.deepEqual(result.recent_events,[]);
});
test('missing ambiguous malformed and other-driver empty labels stay unavailable',()=>{
 const source=snapshot();source.events=[];
 for(const labels of [[],['There are no safety events.'],['There are no safety events for Other Driver.'],['There are no safety events for Sample.'],['There are no safety events for Sample Driver.','There are no safety events for Sample Driver.'],['There are no safety events for Sample Driver. Additional text']]) {
  source.event_empty_texts=labels;assert.equal(parseSummary(source,ranges,'Sample Driver').sections.recent_events,'unavailable');
 }
 source.event_empty_texts=['There are no safety events for Sample Driver.'];
 assert.equal(parseSummary(source,ranges).sections.recent_events,'unavailable');
 source.event_headers.push('STATUS');assert.equal(parseSummary(source,ranges,'Sample Driver').sections.recent_events,'unavailable');
});
test('a rendered event row contradicting an empty-state label fails closed',()=>{
 const source=snapshot();source.event_empty_texts=['There are no safety events for Sample Driver.'];
 assert.throws(()=>parseSummary(source,ranges,'Sample Driver'),/event_layout/);
});


const driverIdentity={provider_driver_id:'123',driver_name:'Sample Driver'};
const driverUrl='https://app.gomotive.com/en-US/#/fleetview/drivers/summary/123';
const breadcrumbs=()=>[[{text:'Fleet View',href:'#/fleetview/map'},{text:'Drivers',href:'#/fleetview/list/drivers'},{text:'Sample Driver',href:null}]];
test('summary identity uses exact provider URL and breadcrumb without optional actions',()=>{
 assert.doesNotThrow(()=>validateSummaryIdentity(driverUrl,breadcrumbs(),driverIdentity));
});
test('summary identity rejects wrong names routes and ambiguous breadcrumbs',()=>{
 const wrongName=breadcrumbs();wrongName[0][2].text='Different Driver';assert.throws(()=>validateSummaryIdentity(driverUrl,wrongName,driverIdentity),/driver_identity_changed/);
 const wrongRoute=breadcrumbs();wrongRoute[0][1].href='#/fleetview/list/vehicles';assert.throws(()=>validateSummaryIdentity(driverUrl,wrongRoute,driverIdentity),/driver_identity_changed/);
 for(const url of [driverUrl.replace('/123','/124'),driverUrl.replace('app.gomotive.com','attacker.invalid')])assert.throws(()=>validateSummaryIdentity(url,breadcrumbs(),driverIdentity),/driver_identity_changed/);
 assert.throws(()=>validateSummaryIdentity(driverUrl,[...breadcrumbs(),...breadcrumbs()],driverIdentity),/driver_identity_changed/);
 const empty=breadcrumbs();empty[0][2].text='';assert.throws(()=>validateSummaryIdentity(driverUrl,empty,driverIdentity),/driver_identity_changed/);
});


test('safety score uses the rendered score label rather than chart ticks or tooltip metrics',()=>{
 const source=snapshot();source.safety_score_texts=['83'];source.safety_lines.splice(2,1,'100','80','60','40','20','0','Fleet Average','86');
 assert.equal(parseSummary(source,ranges).safety.score,83);
 source.safety_score_texts=[];assert.equal(parseSummary(source,ranges).sections.safety,'unavailable');
});


function readinessFixture({loaders=[],score='82',graph=true}={}) {
 const node=(classes,shown=true,text='')=>({classes,shown,textContent:text,getBoundingClientRect:()=>({height:shown?20:0})});
 const spinnerNodes=loaders.map(({classes,shown=true})=>node(classes,shown));
 const scoreNodes=score===null?[]:[node('',true,score)];
 const document={
  querySelectorAll:selector=>spinnerNodes.filter(el=>selector.split(',').some(part=>part==='loader.loading'?el.classes.includes('loader.loading'):el.classes.split(' ').includes(part.slice(1)))),
  querySelector:selector=>selector==='.safety-score-card'?{querySelector:()=>graph?{}:null,querySelectorAll:()=>scoreNodes}:null,
 };
 return vm.runInNewContext(`(${summaryDomReady.toString()})()`,{document,getComputedStyle:()=>({visibility:'visible'})});
}
test('action-center loaders gate readiness after the score and breadcrumb have loaded',()=>{
 for(const classes of ['ant-spin-spinning','phx-loading-icon','loader.loading'])assert.equal(readinessFixture({loaders:[{classes}]}),false);
 assert.equal(readinessFixture({loaders:[{classes:'phx-loading-icon',shown:false}]}),true);
 assert.equal(readinessFixture({loaders:[{classes:'phx-button-loading-icon'}]}),true);
});
test('readiness also waits for the rendered score while its graph initializes',()=>{
 assert.equal(readinessFixture({score:null}),false);
 assert.equal(readinessFixture({score:''}),false);
 assert.equal(readinessFixture({score:'0'}),true);
 assert.equal(readinessFixture({graph:false,score:null}),true);
});

const expectedVin='1XKWD49X03J000001',differentVin='1XKWD49X03J000002';
function vinReads(values) {
 const context={},link={href:'#/fleetview/vehicles/summary/123',unit:'Sample unit'},retries=[];
 let calls=0;
 return {context,link,retries,get calls(){return calls;},options:{
  readVin:async(actualContext,actualLink)=>{
   assert.equal(actualContext,context);assert.equal(actualLink,link);
   const value=values[calls++];
   if(value instanceof Error)throw value;
   return value;
  },
  onRetry:attempt=>retries.push(attempt),
 }};
}
test('initial VIN recovers from missing render using the same provider identity',async()=>{
 const reads=vinReads([null,expectedVin]);
 assert.equal(await readDriverVehicleVin(reads.context,reads.link,reads.options),expectedVin);
 assert.equal(reads.calls,2);assert.deepEqual(reads.retries,[{attempt:1,max_attempts:3}]);
});
test('an initially absent VIN stays unavailable after the bounded fresh-page attempts',async()=>{
 const reads=vinReads([null,null,null,expectedVin]);
 assert.equal(await readDriverVehicleVin(reads.context,reads.link,reads.options),null);
 assert.equal(reads.calls,3);assert.deepEqual(reads.retries,[{attempt:1,max_attempts:3},{attempt:2,max_attempts:3}]);
});
test('post-summary VIN verification tolerates missing render only when the exact VIN returns',async()=>{
 for(const values of [[expectedVin],[null,expectedVin],[null,null,expectedVin]]) {
  const reads=vinReads(values);
  assert.equal(await readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin}),expectedVin);
  assert.equal(reads.calls,values.length);
 }
});
test('any different VIN aborts verification immediately even if a later read would match',async()=>{
 for(const values of [[differentVin,expectedVin],[null,differentVin,expectedVin]]) {
  const reads=vinReads(values);
  await assert.rejects(readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin}),{message:'vehicle_identity_changed'});
  assert.equal(reads.calls,values.indexOf(differentVin)+1);
 }
});
test('persistently missing verification fails closed distinctly from changed identity',async()=>{
 const reads=vinReads([null,null,null,expectedVin]);
 await assert.rejects(readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin}),{message:'vehicle_identity_unavailable'});
 assert.equal(reads.calls,3);
 assert.equal(safeReason(new Error('vehicle_identity_unavailable')),'vehicle_identity_unavailable');
});
test('source, ambiguity and navigation errors never trigger an identity retry',async()=>{
 for(const message of ['vehicle_source_changed','ambiguous_vin','navigation failed with private source content']) {
  const error=new Error(message),reads=vinReads([error,expectedVin]);
  await assert.rejects(readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin}),actual=>actual===error);
  assert.equal(reads.calls,1);assert.deepEqual(reads.retries,[]);
  assert.equal(safeReason(error),message.startsWith('navigation')?'driver_collection_failed':message);
 }
});
test('only reviewed pre-summary identity failures may isolate one row',()=>{
 for(const reason of ['vehicle_identity_changed','vehicle_identity_unavailable']){
  const error=new Error(reason);
  assert.equal(canDeferReviewedPreSummaryIdentity(error,true),true,reason);
  assert.equal(canDeferReviewedPreSummaryIdentity(error,false),false,reason);
 }
 const timeout=uiTimeout();
 assert.equal(canDeferReviewedPreSummaryIdentity(timeout,true),true);
 assert.equal(canDeferReviewedPreSummaryIdentity(timeout,false),false);
 for(const reason of ['vin_changed','vehicle_source_changed','driver_identity_changed','ambiguous_vin','company_mismatch']){
  assert.equal(canDeferReviewedPreSummaryIdentity(new Error(reason),true),false,reason);
 }
});
test('reviewed pre-summary identity failures yield no VIN and no readings; other failures still abort',async()=>{
 for(const [error,expectedReason] of [[new Error('vehicle_identity_changed'),'vehicle_identity_changed'],[new Error('vehicle_identity_unavailable'),'vehicle_identity_unavailable'],[uiTimeout(),'ui_timeout']]){
  let reads=0;
  const deferred=await readBeforeSummaryIdentity(async()=>{reads++;throw error;},true);
  assert.deepEqual(deferred,{deferred:true,vin:null,reason:expectedReason});assert.equal(reads,1);
  reads=0;
  await assert.rejects(readBeforeSummaryIdentity(async()=>{reads++;throw error;},false),error);assert.equal(reads,1);
 }
 for(const reason of ['vin_changed','vehicle_source_changed','ambiguous_vin','company_mismatch']){
  await assert.rejects(readBeforeSummaryIdentity(async()=>{throw new Error(reason);},true),{message:reason});
 }
 const accepted=await readBeforeSummaryIdentity(async()=>expectedVin,true);assert.deepEqual(accepted,{deferred:false,vin:expectedVin});
});

function uiTimeout() {return Object.assign(new Error('Timed out opening private vehicle page'),{name:'TimeoutError'});}
test('a page timeout recovers only through a fresh verified VIN read',async()=>{
 for(const expected of [null,expectedVin]) {
  const error=uiTimeout(),reads=vinReads([error,expectedVin]);
  assert.equal(await readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin:expected}),expectedVin);
  assert.equal(reads.calls,2);
  assert.deepEqual(reads.retries,[{attempt:1,max_attempts:3,reason:'ui_timeout'}]);
  assert.equal(JSON.stringify(reads.retries).includes('private'),false);
 }
});
test('null and timeout reads share the same three-attempt budget',async()=>{
 const reads=vinReads([null,uiTimeout(),expectedVin]);
 assert.equal(await readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin}),expectedVin);
 assert.equal(reads.calls,3);
 assert.deepEqual(reads.retries,[{attempt:1,max_attempts:3},{attempt:2,max_attempts:3,reason:'ui_timeout'}]);
});
test('exhausted and mixed timeouts never become missing-VIN rows',async()=>{
 for(const expected of [null,expectedVin]) {
  for(const timeoutPositions of [[0],[1],[2],[0,1,2]]) {
   const error=uiTimeout(),values=[null,null,null];
   for(const position of timeoutPositions)values[position]=error;
   const reads=vinReads([...values,expectedVin]);
   await assert.rejects(readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin:expected}),actual=>actual===error);
   assert.equal(reads.calls,3);assert.equal(reads.retries.length,2);
   assert.equal(safeReason(error),'ui_timeout');
  }
 }
});
test('a conflicting VIN after a timeout still aborts immediately',async()=>{
 const reads=vinReads([uiTimeout(),differentVin,expectedVin]);
 await assert.rejects(readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin}),{message:'vehicle_identity_changed'});
 assert.equal(reads.calls,2);assert.equal(reads.retries.length,1);
});
test('source, ambiguity and other errors after a timeout still abort immediately',async()=>{
 for(const message of ['vehicle_source_changed','ambiguous_vin','navigation failed with private source content']) {
  const error=new Error(message),reads=vinReads([uiTimeout(),error,expectedVin]);
  await assert.rejects(readDriverVehicleVin(reads.context,reads.link,{...reads.options,expectedVin}),actual=>actual===error);
  assert.equal(reads.calls,2);assert.equal(reads.retries.length,1);
 }
});

async function driverLoginFixture({lookup=false,origin='https://auth.gomotive.com',ambiguous=false,href='#'}={}) {
 const fs=require('node:fs'),path=require('node:path');
 const {createRequire}=require('node:module');
 const actualRequire=createRequire(path.join(__dirname,'collect.cjs'));
 const events=[];let current=origin+(lookup?'/login/lookup?client_id=fixture':'/login?client_id=fixture');
 const page={
  setDefaultTimeout(){},on(){},off(){},
  async goto(){events.push('navigate');},url:()=>current,mainFrame:()=>page,
  async waitForURL(url){if(url==='https://app.gomotive.com/**')throw new Error('fixture_stop_after_submit');},
  async waitForTimeout(){},
  locator(selector){return {
   async count(){return new URL(current).pathname==='/login'?(ambiguous?2:1):0;},
   async fill(value){events.push(['fill',selector,value]);},
  };},
  getByRole(role,{name}){return {
   async count(){return 1;},async getAttribute(){return href;},
   async click(){events.push(name);if(role==='link')current='https://auth.gomotive.com/login?client_id=fixture';},
  };},
 };
 const browser={async newContext(){return {async newPage(){return page;}};}};
 const module={exports:{}};
 const mockedRequire=name=>{
  if(name==='node:fs')return {writeFileSync(){},chmodSync(){},renameSync(){}};
  if(name==='../motive_sync/tasks.cjs')return {phase:value=>events.push(value),closeBrowser:async()=>events.push('closed')};
  if(name==='../motive_sync/vehicle_identity.cjs')return {...actualRequire(name),allowlist:()=>new Map()};
  if(name==='../motive_sync/node_modules/playwright')return {chromium:{launch:async()=>browser}};
  return actualRequire(name);
 };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'collect.cjs'),'utf8'),{require:mockedRequire,module,process:{env:{MOTIVE_COMPANY_LABEL:'fixture',MOTIVE_COMPANY_ID:'fixture',MOTIVE_EMAIL:'fixture@example.invalid',MOTIVE_PASSWORD:'synthetic-only'}},URL,console});
 let error;
 try{await module.exports.collect('synthetic-output');}catch(e){error=e;}
 return {events,error};
}
for(const lookup of [false,true])test(`driver collector prepares ${lookup?'lookup':'legacy'} form before single credential submission`,async()=>{
 const {events,error}=await driverLoginFixture({lookup});
 assert.equal(error.message,'fixture_stop_after_submit');
 assert.ok(events.indexOf('login_form_check')<events.indexOf('login_email'));
 assert.equal(events.filter(x=>x==='Use legacy login').length,lookup?1:0);
 assert.equal(events.filter(x=>x==='Log in').length,1);
 assert.equal(events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,2);
 assert.equal(events.at(-1),'closed');
});
for(const [name,options,reason] of [
 ['wrong initial origin',{origin:'https://evil.invalid'},'login_origin'],
 ['ambiguous legacy form',{ambiguous:true},'login_form_ambiguous'],
 ['foreign legacy link',{lookup:true,href:'https://evil.invalid/login'},'login_legacy_link_invalid'],
])test(`driver collector rejects ${name} before filling credentials`,async()=>{
 const {events,error}=await driverLoginFixture(options);
 assert.equal(error.message,reason);
 assert.equal(events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,0);
 assert.equal(events.filter(x=>x==='Log in').length,0);
 assert.equal(events.at(-1),'closed');
});
