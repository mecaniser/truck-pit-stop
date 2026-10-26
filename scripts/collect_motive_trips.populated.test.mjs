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
 const result=spawnSync(process.execPath,['-e',code,file],{encoding:'utf8'});assert.equal(result.status,1);assert.deepEqual(JSON.parse(result.stdout),{kind:'trip_populated_canary',failed:true,stage:'browser',import_permitted:false});assert(!result.stderr.includes('PRIVATE'));
});
