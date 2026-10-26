import test from 'node:test';import assert from 'node:assert/strict';import {EventEmitter} from 'node:events';
import proof from '../backend/scripts/motive_sync/trip_populated_proof.cjs';import server from '../backend/scripts/motive_sync/collect_trips.cjs';import * as adapter from './collect_motive_trips.mjs';
const day='2026-09-01';const row=i=>({links:[`#/fleetview/vehicles/summary/${i}`],cells:['','09/01/2026 09:00 AM\nFixture','IN PROGRESS','1\n1m']});
const record=i=>({driving_period:{id:i,vehicle:{id:i},start_time:'2026-09-01T13:00:00Z'}});
const req=(date=day)=>({url:()=>`https://api.keeptruckin.com/observed?start_date=${date}&end_date=${date}`,postData:()=>null});
const response=(r,items,total=87)=>({url:()=>r.url(),request:()=>r,status:()=>200,headers:()=>({'content-type':'application/json'}),body:async()=>Buffer.from(JSON.stringify({total,per_page:50,driving_periods:items}))});
function send(p,items,total=87,r=req()){p.emit('request',r);p.emit('response',response(r,items,total));}
test('actual collector waits past quiet50 page and accepts delayed37 only with identity parity',async()=>{
 const p=new EventEmitter();let ticks=0;Object.assign(p,{goto:async()=>{send(p,Array.from({length:50},(_,i)=>record(i+1)));},waitForFunction:async()=>{},url:()=>adapter.reportUrl(day,day),waitForTimeout:async()=>{ticks++;if(ticks===20)send(p,Array.from({length:37},(_,i)=>record(i+51)));},evaluate:async fn=>fn.toString().includes('const headers =')?{url:adapter.reportUrl(day,day),loading:false,state:'rows',headers:['','Origin (MDY EDT)','Destination (MDY EDT)','Dist. (mi) / Duration','Vehicle ID / Mode','Driver / ID','','Notes',''],rows:Array.from({length:ticks<20?50:87},(_,i)=>row(i+1)),footer:`Showing ${ticks<20?50:87} results`}:true});
 const result=await server.collectWindow(p,{start:day,end:day},async()=>{},adapter,{maxSteps:40});assert(ticks>=20);assert.equal(result.rows.length,87);assert.equal(result.populated_proof.total,87);assert(proof.validProof(result));assert.equal(p.listenerCount('response'),0);
});
for(const kind of ['duplicatepage','duplicateid','duplicateidentity','totalchange','invalidid','missingvehicle','wrongdate'])test(kind+' fails closed',async()=>{
 const p=new EventEmitter(),state=proof.createProof(p,{start:day,end:day});
 const items=[record(1),record(2)];if(kind==='duplicateid')items[1].driving_period.id=1;if(kind==='duplicateidentity')items[1].driving_period.vehicle.id=1;if(kind==='invalidid')items[0].driving_period.id='private';if(kind==='missingvehicle')delete items[0].driving_period.vehicle;if(kind==='wrongdate')items[0].driving_period.start_time='2026-09-02T13:00:00Z';
 send(p,items,2);if(kind==='duplicatepage')send(p,items,2);if(kind==='totalchange')send(p,[record(3)],3);
 await assert.rejects(state.proof([row(1),row(2)],new Date().toISOString()),/proof_invalid/);state.close();
});
test('equal count wrongidentity cannot complete; unseen page not complete',async()=>{
 const p=new EventEmitter(),s=proof.createProof(p,{start:day,end:day});send(p,[record(1)],2);assert.equal(await s.proof([row(1)],new Date().toISOString()),null);send(p,[record(2)],2);await assert.rejects(s.proof([row(1),row(3)],new Date().toISOString()));s.close();
});
test('prior epoch request, wrong window and duplicate date query cannot supply proof',async()=>{
 const p=new EventEmitter(),old=req();p.emit('request',old);const s=proof.createProof(p,{start:day,end:day});p.emit('response',response(old,[record(1)],1));send(p,[record(1)],1,req('2026-09-02'));const duplicate={url:()=>req().url()+'&start_date='+day,postData:()=>null};send(p,[record(1)],1,duplicate);assert.equal(await s.proof([row(1)],new Date().toISOString()),null);s.close();
});
test('legacy quiet footer without populated proof is rejected',()=>assert.throws(()=>adapter.finalizeWindow({start:day,end:day,status:'partial',rows:[row(1)],footer:'Showing 1 results'},1,'Showing 1 results'),/proof required/));
test('empty DOM cannot override positive authoritative total or malformed response',async()=>{
 for(const malformed of [false,true]){const p=new EventEmitter(),s=proof.createProof(p,{start:day,end:day});const item=record(1);if(malformed)delete item.driving_period.vehicle;send(p,[item],1);await assert.rejects(s.empty(),/proof_invalid/);s.close();}
});
test('known inflight request prevents finalization and late conflicting queue is checked',async()=>{
 const p=new EventEmitter(),s=proof.createProof(p,{start:day,end:day});send(p,[record(1)],1);const later=req();p.emit('request',later);assert.equal(await s.proof([row(1)],new Date().toISOString()),null);p.emit('response',response(later,[record(2)],2));await assert.rejects(s.proof([row(1)],new Date().toISOString()),/proof_invalid/);s.close();
});
test('calendar rollover cannot manufacture matching departure identity',async()=>{
 const p=new EventEmitter(),s=proof.createProof(p,{start:'2026-03-02',end:'2026-03-02'});const item=record(1);item.driving_period.start_time='2026-02-30T18:00:00Z';send(p,[item],1,req('2026-03-02'));await assert.rejects(s.proof([],new Date().toISOString()),/proof_invalid/);s.close();
});
test('failed matching request aborts proof and closed epoch does not consume late events',async()=>{
 const p=new EventEmitter(),s=proof.createProof(p,{start:day,end:day});const r=req();p.emit('request',r);p.emit('requestfailed',r);await assert.rejects(s.proof([],new Date().toISOString()));s.close();assert.equal(p.listenerCount('requestfailed'),0);
});
import {spawnSync} from 'node:child_process';
test('read-only canary positive preflight reaches browser with no auth or DB actions',()=>{
 const file=new URL('../backend/scripts/motive_sync/probe_trip_populated.cjs',import.meta.url).pathname;
 const code=`const M=require('node:module'),fs=require('node:fs');const original=M._load;M._load=function(name){if(name==='playwright')return {chromium:{launch:async()=>{throw Error('PRIVATE_MUST_NOT_ESCAPE');}}};return original.apply(this,arguments);};Object.assign(process.env,{MOTIVE_COMPANY_ID:'KT8934277',MOTIVE_COMPANY_LABEL:'77 CARGO LLC',MOTIVE_SYNC_TENANT_ID:'fixture',MOTIVE_SYNC_ACTOR_ID:'fixture',MOTIVE_EMAIL:'synthetic',MOTIVE_PASSWORD:'synthetic'});const file=process.argv[1],m=new M(file);m.filename=file;m.paths=M._nodeModulePaths(require('node:path').dirname(file));process.mainModule=m;process.argv=[process.execPath,file,'--read-only','2026-09-01'];m._compile(fs.readFileSync(file,'utf8'),file);`;
 const result=spawnSync(process.execPath,['-e',code,file],{encoding:'utf8'});assert.equal(result.status,1);assert.deepEqual(JSON.parse(result.stdout),{kind:'trip_populated_canary',failed:true,stage:'browser',reason:'collection_failed',diagnostic:{},import_permitted:false});assert(!result.stderr.includes('PRIVATE'));
});

import diagnostics from '../backend/scripts/motive_sync/trip_populated_diagnostics.cjs';
test('diagnostic sink accepts only bounded static values and immutable copies',()=>{
 const raw={phase:'SECRET',reason:'SECRET',responses:Infinity,pending:-1,decoded_pages:1.5,dom_rows:999999999,fields:{id:'SECRET',vehicle_id:'missing',secret:'string'},url:'SECRET'};
 assert.deepEqual(diagnostics.sanitize(raw),{dom_rows:1000000,fields:{vehicle_id:'missing'}});
 const e=diagnostics.attach(Error('SECRET'),{phase:'capture',fields:{id:'number'}});assert(Object.isFrozen(e.tripPopulatedDiagnostic));assert(Object.isFrozen(e.tripPopulatedDiagnostic.fields));assert(!JSON.stringify(e.tripPopulatedDiagnostic).includes('SECRET'));
});
for(const [code,mutate]of [
 ['id_invalid',x=>{x.driving_period.id='SECRET';}],['vehicle_id_invalid',x=>{delete x.driving_period.vehicle;}],['timestamp_invalid',x=>{x.driving_period.start_time='SECRET';}],['outside_day',x=>{x.driving_period.start_time='2026-09-02T13:00:00Z';}],['record_shape',x=>{x.driving_period=null;}],
])test('safe decisive diagnostic '+code,async()=>{
 const p=new EventEmitter(),s=proof.createProof(p,{start:day,end:day});const item=record(1);mutate(item);send(p,[item],1);await assert.rejects(s.proof([row(1)],new Date().toISOString()));const d=s.snapshot();assert.equal(d.reason,code);assert.equal(d.decoded_pages,1);assert(!JSON.stringify(d).includes('SECRET'));s.close();assert.equal(d.responses,1);
});
test('absence, pending and missing tail have distinct bounded progress',async()=>{
 const p=new EventEmitter(),s=proof.createProof(p,{start:day,end:day});assert.equal(s.snapshot().reason,'no_matching_response');const r=req();p.emit('request',r);p.emit('response',response(r,[record(1)],2));await s.proof([row(1)],new Date().toISOString());assert.equal(s.snapshot().reason,'incomplete_tail');const next=req();p.emit('request',next);assert.equal(s.snapshot().reason,'pending_response');s.close();
});
test('actual collector copies proof diagnostic before cleanup and never raw field value',async()=>{
 const p=new EventEmitter();Object.assign(p,{goto:async()=>{const item=record(1);delete item.driving_period.vehicle;send(p,[item],1);},waitForFunction:async()=>{},url:()=>adapter.reportUrl(day,day),waitForTimeout:async()=>{},evaluate:async fn=>fn.toString().includes('const headers =')?{url:adapter.reportUrl(day,day),loading:false,state:'rows',headers:['','Origin (MDY EDT)','Destination (MDY EDT)','Dist. (mi) / Duration','Vehicle ID / Mode','Driver / ID','','Notes',''],rows:[row(1)],footer:'Showing 1 results'}:true});
 await assert.rejects(server.collectWindow(p,{start:day,end:day},async()=>{},adapter),e=>{assert.equal(e.tripPopulatedDiagnostic.reason,'vehicle_id_invalid');assert.equal(e.tripPopulatedDiagnostic.phase,'populated_proof');assert.equal(e.tripPopulatedDiagnostic.responses,1);assert.equal(e.tripPopulatedDiagnostic.fields.vehicle_id,'missing');return true;});assert.equal(p.listenerCount('response'),0);
});
for(const success of [false,true])test('actual canary capture path '+(success?'success':'sanitized failure'),()=>{
 const file=new URL('../backend/scripts/motive_sync/probe_trip_populated.cjs',import.meta.url).pathname;
 const code=`const M=require('node:module'),fs=require('node:fs');const original=M._load;let url='https://auth.gomotive.com/login';const locator={waitFor:async()=>{},fill:async()=>{},click:async()=>{},innerText:async()=>'KT8934277 77 CARGO LLC',evaluate:async()=>'Eastern Time - New York'};const page={setDefaultTimeout:()=>{},goto:async u=>{url=u.includes('/admin/')||u.includes('/settings')?u:'https://auth.gomotive.com/login';},waitForURL:async u=>{if(u.includes('app.gomotive'))url='https://app.gomotive.com/';},url:()=>url,locator:()=>locator,getByText:()=>locator,getByRole:()=>locator};M._load=function(name){if(name==='playwright')return {chromium:{launch:async()=>({newContext:async()=>({newPage:async()=>page}),close:async()=>{}})}};if(name==='./login.cjs')return {prepareLegacyLogin:async()=>{}};if(name==='node:child_process')return {spawnSync:()=>({status:0})};if(name==='./collect_trips.cjs'){const real=original.apply(this,arguments);return {...real,collectWindow:async()=>{if(${success})return {status:'captured',rows:[{}],populated_proof:{version:1,total:1,response_count:1,response_identity_count:1}};const e=Error('SECRET');e.tripPopulatedDiagnostic={phase:'populated_proof',reason:'vehicle_id_invalid',responses:1,fields:{vehicle_id:'missing',secret:'SECRET'},secret:'SECRET'};throw e;}};}return original.apply(this,arguments);};Object.assign(process.env,{MOTIVE_COMPANY_ID:'KT8934277',MOTIVE_COMPANY_LABEL:'77 CARGO LLC',MOTIVE_SYNC_TENANT_ID:'fixture',MOTIVE_SYNC_ACTOR_ID:'fixture',MOTIVE_EMAIL:'synthetic',MOTIVE_PASSWORD:'synthetic'});const file=process.argv[1],m=new M(file);m.filename=file;m.paths=M._nodeModulePaths(require('node:path').dirname(file));process.mainModule=m;process.argv=[process.execPath,file,'--read-only','2026-09-01'];m._compile(fs.readFileSync(file,'utf8'),file);`;
 const result=spawnSync(process.execPath,['-e',code,file],{encoding:'utf8'});assert.equal(result.status,success?0:1,result.stderr);assert(!result.stdout.includes('SECRET'));assert(!result.stderr.includes('SECRET'));const out=JSON.parse(result.stdout);assert.equal(out.import_permitted,false);if(success)assert.equal(out.python_validated,true);else{assert.equal(out.stage,'populated_capture');assert.equal(out.diagnostic.reason,'vehicle_id_invalid');assert.deepEqual(out.diagnostic.fields,{vehicle_id:'missing'});}
});
test('UI timeout and missing pagination remain distinguishable on actual collector',async()=>{
 const p=new EventEmitter();p.goto=async()=>{const e=Error('SECRET locator and URL');e.name='TimeoutError';throw e;};
 await assert.rejects(server.collectWindow(p,{start:day,end:day},async()=>{},adapter),e=>{assert.equal(server.safeFailure(e),'ui_timeout');assert.equal(e.tripPopulatedDiagnostic.phase,'navigation');assert.equal(e.tripPopulatedDiagnostic.matched_requests,0);assert(!JSON.stringify(e.tripPopulatedDiagnostic).includes('SECRET'));return true;});
});
for(const kind of ['root_shape','json','total_changed','duplicate_id','duplicate_identity','bijection_mismatch'])test('specific safe pagination reason '+kind,async()=>{
 const p=new EventEmitter(),s=proof.createProof(p,{start:day,end:day});const r=req();let items=[record(1),record(2)],res=response(r,items,2);
 if(kind==='root_shape')res.body=async()=>Buffer.from(JSON.stringify({total:'SECRET',per_page:50,driving_periods:items}));
 if(kind==='json')res.body=async()=>Buffer.from('SECRET');
 if(kind==='duplicate_id')items[1].driving_period.id=1;
 if(kind==='duplicate_identity')items[1].driving_period.vehicle.id=1;
 p.emit('request',r);p.emit('response',res);if(kind==='total_changed')send(p,[record(3)],3);
 await assert.rejects(s.proof(kind==='bijection_mismatch'?[row(1),row(3)]:[row(1),row(2)],new Date().toISOString()));assert.equal(s.snapshot().reason,kind);assert(!JSON.stringify(s.snapshot()).includes('SECRET'));s.close();
});
