import test from 'node:test';
import assert from 'node:assert/strict';
import {captureStep, finalizeWindow, newWindow, reportUrl} from './collect_motive_trips.mjs';
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
