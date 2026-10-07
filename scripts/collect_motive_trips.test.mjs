import test from 'node:test';
import assert from 'node:assert/strict';
import {captureStep, finalizeWindow, newWindow, reportUrl, readReport} from './collect_motive_trips.mjs';
const headers=['','Origin (MDY EDT)','Destination (MDY EDT)','Dist. (mi) / Duration','Vehicle ID / Mode','Driver / ID','','Notes',''];
const row=(id,text='City')=>({cells:['',`09/28/2026 09:00 AM\n${text}`,'09/28/2026 10:00 AM\nOther','40\n1h 0m 0s'],links:[`#/fleetview/vehicles/summary/${id}`]});
const report=(rows,extra={})=>({state:'rows',url:reportUrl('2026-09-28','2026-09-28'),headers,rows,footer:`Showing ${rows.length} results`,...extra});
const page=r=>({evaluate:async()=>r});
test('overlapping pages do not duplicate; missing tail cannot complete',async()=>{
 let r=await captureStep(page(report([row(1)])),newWindow('2026-09-28','2026-09-28'));
 assert.throws(()=>finalizeWindow(r,2,'1/2'),/Incomplete/);
 r=await captureStep(page(report([row(1),row(2)])),r);
 assert.equal(finalizeWindow(r,2,'1/2').status,'captured');
});
test('changed versions cannot manufacture completion',async()=>{
 let r=await captureStep(page(report([row(1)])),newWindow('2026-09-28','2026-09-28'));
 r=await captureStep(page(report([row(1,'Changed')],{footer:'Showing 2 results'})),r);
 assert.equal(r.rows.length,2);
 assert.throws(()=>finalizeWindow(r,2,'1/2'),/ambiguous/);
});
test('wrong date filters and header order fail closed',async()=>{
 for(const extra of [{url:reportUrl('2026-09-27','2026-09-28')},{headers:[...headers].reverse()},{url:reportUrl('2026-09-28','2026-09-28')+';vehicle_id=1'}])
  await assert.rejects(captureStep(page(report([row(1)],extra)),newWindow('2026-09-28','2026-09-28')));
});
test('loading never becomes empty; empty cannot erase rows',async()=>{
 const initial=newWindow('2026-09-28','2026-09-28');
 const loading=await captureStep(page(report([],{state:'loading'})),initial);
 assert.equal(loading.status,'loading');assert.throws(()=>finalizeWindow(loading,0,'none'));
 const empty=await captureStep(page(report([],{state:'empty'})),initial);
 assert.equal(finalizeWindow(empty,0,'No trips').status,'empty');
 await assert.rejects(captureStep(page(report([],{state:'empty'})),{...initial,rows:[row(1)]}));
});
test('expired session stops; stagnation stays partial',async()=>{
 const initial=newWindow('2026-09-28','2026-09-28');
 await assert.rejects(captureStep(page({state:'unavailable'}),initial),/login/);
 let r=await captureStep(page(report([row(1)])),initial);
 r=await captureStep(page(report([row(1)])),r);
 assert.equal(r.stagnant_steps,1);assert.equal(r.status,'partial');
});
import {openState} from './motive_collector_state.mjs';
import {mkdtemp,stat,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
test('private checkpoints are atomic and exclusive across runners',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'motive-state-'));
 try{const state=await openState(dir);await assert.rejects(openState(dir),/EEXIST/);
 await state.write('window.json',{status:'partial'});await state.write('window.json',{status:'captured'});
 assert.equal((await state.read('window.json')).status,'captured');assert.equal((await stat(join(dir,'window.json'))).mode&0o777,0o600);
 await assert.rejects(state.write('../escape.json',{}));await state.close();const again=await openState(dir);await again.close();
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('EST requires verified New York settings; mismatched or changing header zones fail',async()=>{
 const winter=headers.map(s=>s.replaceAll('EDT','EST'));
 const initial=newWindow('2026-09-28','2026-09-28');
 await assert.rejects(captureStep(page(report([row(1)],{headers:winter})),initial),/verification/);
 const r=await captureStep(page(report([row(1)],{headers:winter})),initial,{verifiedTimezone:'America/New_York'});
 assert.equal(r.header_timezone,'EST');
 await assert.rejects(captureStep(page(report([row(1)])),r,{verifiedTimezone:'America/New_York'}),/timezone changed/);
 const mixed=[...headers];mixed[2]='Destination (MDY EST)';
 await assert.rejects(captureStep(page(report([row(1)],{headers:mixed})),initial,{verifiedTimezone:'America/New_York'}),/layout/);
});
import server from '../backend/scripts/motive_sync/collect_trips.cjs';
test('daily overlap follows New York calendar across midnight and DST',()=>{
 assert.deepEqual(server.recentWindow(new Date('2026-10-08T02:00:00Z')),{start:'2026-10-05',end:'2026-10-07'});
 assert.deepEqual(server.recentWindow(new Date('2026-03-09T04:01:00Z')),{start:'2026-03-07',end:'2026-03-09'});
});
test('directory rejects partial pages and conflicting identity, missing VIN remains unknown',()=>{
 const links=[{href:'#/fleetview/vehicles/summary/123',unit:'1'}];
 assert.equal(server.validateDirectory(links,1,1).length,1);
 assert.throws(()=>server.validateDirectory(links,1,2),/incomplete/);
 assert.throws(()=>server.validateDirectory([...links,{...links[0],unit:'2'}],1,1),/ambiguous/);
 assert.equal(server.summaryVin('VIN —'),null);
 assert.equal(server.summaryVin('VIN 1FUJGLDR0DLBY1234'),'1FUJGLDR0DLBY1234');
 assert.throws(()=>server.summaryVin('VIN 1FUJGLDR0DLBY1234 VIN 1FUJGLDR0DLBY1235'),/ambiguous/);
});
test('server report traversal never commits a truncated or perpetually loading window',async()=>{
 const adapter={reportUrl,newWindow,captureStep,finalizeWindow};
 const initial=report([row(1)],{footer:'Showing 2 results'});
 const fake={waitForFunction:async()=>{},goto:async()=>{},url:()=>initial.url,evaluate:async fn=>fn.toString().includes('document.querySelector')?initial:true,waitForTimeout:async()=>{}};
 let last;
 await assert.rejects(server.collectWindow(fake,{start:'2026-09-28',end:'2026-09-28'},async r=>{last=r;},adapter,{maxSteps:5}),/step_limit/);
 assert.equal(last.status,'partial');
});
test('server completion requires bottom evidence even when visible count matches',async()=>{
 const adapter={reportUrl,newWindow,captureStep,finalizeWindow};
 const source=report([row(1)]);let bottom=false,last;
 const fake={waitForFunction:async()=>{},goto:async()=>{},url:()=>source.url,evaluate:async fn=>fn.toString().includes('const headers =')?source:bottom,waitForTimeout:async()=>{}};
 const checkpoint=async r=>{last=r;};
 await assert.rejects(server.collectWindow(fake,{start:'2026-09-28',end:'2026-09-28'},checkpoint,adapter,{maxSteps:5}),/step_limit/);
 assert.equal(last.status,'partial');bottom=true;
 assert.equal((await server.collectWindow(fake,{start:'2026-09-28',end:'2026-09-28'},checkpoint,adapter,{maxSteps:5})).status,'captured');
 source.state='loading';source.rows=[];
 await assert.rejects(server.collectWindow(fake,{start:'2026-09-28',end:'2026-09-28'},checkpoint,adapter,{maxSteps:5}),/step_limit/);
 assert.equal(last.status,'loading');
});
test('finalized producer windows carry backend count contract including explicit empty',async()=>{
 const adapter={reportUrl,newWindow,captureStep,finalizeWindow};
 const source=report([row(1)]);
 const fake={waitForFunction:async()=>{},goto:async()=>{},url:()=>source.url,evaluate:async fn=>fn.toString().includes('const headers =')?source:true,waitForTimeout:async()=>{}};
 const filled=await server.collectWindow(fake,{start:'2026-09-28',end:'2026-09-28'},async()=>{},adapter,{maxSteps:5});
 for(const key of ['expected_total','footerShown'])assert.equal(filled[key],filled.rows.length);
 assert.equal(filled.status,'captured');assert.ok(filled.terminal_evidence);
 source.state='empty';source.rows=[];source.footer=null;
 const empty=await server.collectWindow(fake,{start:'2026-09-28',end:'2026-09-28'},async()=>{},adapter,{maxSteps:5});
 assert.equal(empty.expected_total,0);assert.equal(empty.footerShown,0);assert.equal(empty.status,'empty');
 assert.ok(empty.terminal_evidence.includes('No trips found'));
});
test('collector error diagnostics never echo unknown errors or authentication contents',()=>{
 assert.equal(server.safeFailure(new Error('duplicate_vin')),'duplicate_vin');
 assert.equal(server.safeFailure(new Error('Motive table layout or timezone changed')),'report_layout_changed');
 assert.equal(server.safeFailure({name:'TimeoutError',message:'password contents secret'}),'ui_timeout');
 assert.equal(server.safeFailure(new Error('my email and password contents')),'collection_failed');
});
test('each vehicle VIN comes from a fresh document, never previous SPA summary',async()=>{
 const pages=[];const vins=['1FUJGLDR0DLBY1234','1FUJGLDR0DLBY1235'];
 const context={newPage:async()=>{
  const index=pages.length;let url='about:blank';
  const ready={filter:()=>ready,first:()=>ready,waitFor:async()=>{}};
  const p={setDefaultTimeout:()=>{},goto:async value=>{url=value;},url:()=>url,getByRole:()=>ready,waitForFunction:async()=>{},locator:()=>({innerText:async()=>`VIN ${vins[index]}`}),close:async()=>{p.closed=true;}};
  pages.push(p);return p;
 }};
 assert.equal(await server.readVehicleVin(context,{href:'#/fleetview/vehicles/summary/1'}),vins[0]);
 assert.equal(await server.readVehicleVin(context,{href:'#/fleetview/vehicles/summary/2'}),vins[1]);
 assert.equal(pages.length,2);assert.ok(pages.every(p=>p.closed));
});
test('fresh vehicle page closes when session or source changes',async()=>{
 let closed=false;const ready={filter:()=>ready,first:()=>ready,waitFor:async()=>{}};
 const context={newPage:async()=>({setDefaultTimeout:()=>{},goto:async()=>{},url:()=>'https://auth.gomotive.com/login',getByRole:()=>ready,waitForFunction:async()=>{},close:async()=>{closed=true;}})};
 await assert.rejects(server.readVehicleVin(context,{href:'#/fleetview/vehicles/summary/1'}),/vehicle_source_changed/);
 assert.ok(closed);
});
test('report DOM ignores unrelated tables and blank placeholders while loading',async()=>{
 const priorDocument=globalThis.document,priorLocation=globalThis.location;
 const placeholder={querySelectorAll:selector=>selector==='th'?[]:[{querySelectorAll:()=>[{innerText:''}]}]};
 let records=[];
 const table={querySelectorAll:selector=>selector==='th'?headers.map(innerText=>({innerText:innerText.toUpperCase()})):records};
 globalThis.document={querySelector:()=>({innerText:'Loading',querySelectorAll:()=>[placeholder,table]})};
 globalThis.location={href:reportUrl('2026-09-28','2026-09-28')};
 try {
  const p={evaluate:async fn=>fn()};
  assert.equal((await readReport(p)).state,'loading');
  records=[{querySelectorAll:selector=>selector==='td'?[{innerText:''},{innerText:' '}]:[]}];
  assert.equal((await readReport(p)).state,'loading');
  records=[{querySelectorAll:selector=>selector==='td'?row(1).cells.map(innerText=>({innerText})):[{getAttribute:()=>row(1).links[0]}]}];
  const ready=await readReport(p);assert.equal(ready.state,'rows');assert.equal(ready.rows.length,1);assert.equal(ready.headers.length,9);
 } finally {globalThis.document=priorDocument;globalThis.location=priorLocation;}
});
test('rendered uppercase report headers preserve EDT and verified EST acceptance',async()=>{
 const initial=newWindow('2026-09-28','2026-09-28');
 for(const zone of ['EDT','EST']) {
  const source=report([row(1)],{headers:headers.map(value=>value.replaceAll('EDT',zone).toUpperCase())});
  const capture=await captureStep(page(source),initial,{verifiedTimezone:'America/New_York'});
  assert.equal(capture.header_timezone,zone);assert.equal(capture.rows.length,1);
 }
});
test('only ongoing ticking duration is deduplicated, preserving first raw observation',async()=>{
 const first=row(1);first.cells[2]='IN PROGRESS';first.cells[3]='40\n1h 0m 1s';
 let receipt=await captureStep(page(report([first])),newWindow('2026-09-28','2026-09-28'));
 const later=structuredClone(first);later.cells[3]='40\n1h 0m 3s';
 receipt=await captureStep(page(report([later])),receipt);
 assert.equal(receipt.rows.length,1);assert.equal(receipt.rows[0].cells[3],'40\n1h 0m 1s');
 assert.equal(finalizeWindow(receipt,1,'Showing 1 results').status,'captured');
 const changedDistance=structuredClone(later);changedDistance.cells[3]='41\n1h 0m 4s';
 const conflict=await captureStep(page(report([changedDistance])),receipt);
 assert.equal(conflict.rows.length,2);assert.throws(()=>finalizeWindow(conflict,1,'Showing 1 results'),/ambiguous/);
 const completed=row(1);completed.cells[3]='40\n1h 0m 3s';
 const transitioned=await captureStep(page(report([completed])),receipt);
 assert.equal(transitioned.rows.length,2);assert.throws(()=>finalizeWindow(transitioned,1,'Showing 1 results'),/ambiguous/);
});
test('completed duration changes remain conflicting revisions',async()=>{
 const first=row(1),later=structuredClone(first);later.cells[3]='40\n1h 0m 3s';
 let receipt=await captureStep(page(report([first])),newWindow('2026-09-28','2026-09-28'));
 receipt=await captureStep(page(report([later])),receipt);
 assert.equal(receipt.rows.length,2);assert.throws(()=>finalizeWindow(receipt,1,'Showing 1 results'),/ambiguous/);
});
