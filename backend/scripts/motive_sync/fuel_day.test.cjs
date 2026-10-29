const test=require('node:test');const assert=require('node:assert/strict');
const {closed,validatePlan,finalizeDay}=require('./fuel_day.cjs');
const env={MOTIVE_SYNC_TENANT_ID:'tenant',MOTIVE_SYNC_ACTOR_ID:'actor',MOTIVE_COMPANY_ID:'company',MOTIVE_COMPANY_LABEL:'label'};
const now=new Date('2026-10-26T14:00:00Z');
const plan={version:1,run_id:'00000000-0000-0000-0000-000000000001',created_at:now.toISOString(),mode:'automatic',scope:{tenant_id:'tenant',actor_id:'actor',company_id:'company',company_label:'label',baseline:'2026-08-15',date_policy:'unverified_zone_conservative_v1'},days:['2026-08-15','2026-10-25']};
test('historical closure is conservative at noon and rejects rollover',()=>{assert.equal(closed('2026-10-25',new Date('2026-10-26T11:59:59Z')),false);assert.equal(closed('2026-10-25',new Date('2026-10-26T12:00:00Z')),true);assert.equal(closed('2026-02-30',now),false);assert.deepEqual(validatePlan(plan,now,env),plan.days);});
test('scope, duplicate, stale and incomplete dates reject before browser',()=>{for(const changed of [{...plan,scope:{...plan.scope,actor_id:'other'}},{...plan,days:['2026-10-26']},{...plan,days:['2026-08-15','2026-08-15']},{...plan,created_at:'2026-10-26T13:00:00Z'}])assert.throws(()=>validatePlan(changed,now,env));});
test('child success requires separate exact receipt verifier, no retries',()=>{const calls=[];let fresh=0;finalizeDay('/private/source.json','/private/plan.json','2026-08-15',()=>fresh++,(exe,args,opts)=>{calls.push({exe,args,opts});return {status:0};});assert.equal(calls.length,2);assert.equal(calls[0].args.includes('--verify-only'),false);assert.equal(calls[1].args.includes('--verify-only'),true);assert.equal(fresh,2);assert.equal(calls[0].opts.timeout,600000);});
for(const outcome of [{status:17},{status:null,signal:'SIGTERM'},{status:null,error:Error('private data')}])test('ambiguous child aborts without verifier or next day '+JSON.stringify({status:outcome.status,signal:outcome.signal}),()=>{let calls=0;assert.throws(()=>finalizeDay('source','plan','2026-08-15',()=>{},()=>{calls++;return outcome;}),/fuel_day_unverified/);assert.equal(calls,1);});
test('bad receipt verification and expired deadline stop advancement',()=>{let calls=0;assert.throws(()=>finalizeDay('source','plan','day',()=>{},()=>({status:++calls===1?0:1})),/fuel_day_unverified/);assert.equal(calls,2);calls=0;assert.throws(()=>finalizeDay('source','plan','day',()=>{throw Error('expired');},()=>{calls++;}),/expired/);assert.equal(calls,0);});
test('actual date-first collector retains complete first day on later failure',async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
 const {collectPlannedDays}=require('./collect_fuel.cjs');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'fuel-day-test-'));
 const savedEnv={...process.env};Object.assign(process.env,env);
 const freshPlan={...plan,created_at:new Date().toISOString()};
 const result={version:1,company_verified_before:true,company_verified_after:false,complete:false,started_at:new Date().toISOString(),vehicles:[{provider_vehicle_id:'1',vin:null,unit:'A',records:[]},{provider_vehicle_id:'2',vin:null,unit:'B',records:[]}],reports:[]};
 let companyCalls=0;const sequence=[],committed=[];
 try{
  await assert.rejects(collectPlannedDays({output:path.join(dir,'source.json'),planPath:path.join(dir,'plan.json'),plan:freshPlan,result,
   tasks:{assertFresh(){},run:async(_name,_key,read)=>read()},context:{},company:async()=>{companyCalls++;},
   capture:async(_context,date,vehicle)=>{sequence.push([date,vehicle.provider_vehicle_id]);if(date==='2026-10-25')throw Error('timeout');return {record:{report_date:date},report:{report_date:date}};},
   finalize:(source,_plan,day,assertFresh)=>{assertFresh();const doc=JSON.parse(fs.readFileSync(source));assert.equal(doc.complete,true);assert.equal(doc.company_verified_after,true);assert.equal(doc.vehicles.length,2);committed.push(day);}
  }),/timeout/);
  assert.deepEqual(sequence,[['2026-08-15','1'],['2026-08-15','2'],['2026-10-25','1']]);
  assert.deepEqual(committed,['2026-08-15']);assert.equal(companyCalls,1);
  assert.equal(JSON.parse(fs.readFileSync(path.join(dir,'2026-08-15/source.json'))).complete,true);
  assert.equal(JSON.parse(fs.readFileSync(path.join(dir,'2026-10-25/source.json'))).complete,false);
 }finally{for(const k of Object.keys(env)){if(savedEnv[k]===undefined)delete process.env[k];else process.env[k]=savedEnv[k];}fs.rmSync(dir,{recursive:true,force:true});}
});
test('reviewed fuel day brackets the exact provider report with fresh identity',async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
 const {collectPlannedDays,reviewedFuelIdentity}=require('./collect_fuel.cjs');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'fuel-bound-test-')),savedEnv={...process.env};Object.assign(process.env,env);
 const freshPlan={...plan,days:['2026-10-25'],created_at:new Date().toISOString()};
 const vehicle={provider_vehicle_id:'5981300',vin:null,unit:'26',source_vin_state:'not_displayed',records:[]};
 const result={version:1,company_verified_before:true,complete:false,started_at:new Date().toISOString(),vehicles:[vehicle],reports:[]};
 const calls=[];let finalized=0;
 const identity=async()=>{calls.push('identity');return {vin:null,source_vin_state:'not_displayed',read_at:new Date().toISOString()};};
 try{
  const proof=await reviewedFuelIdentity({},vehicle,async(_context,link)=>{assert.equal(link.href,'#/fleetview/vehicles/summary/5981300');return {vin:null,source_vin_state:'not_displayed'};});
  assert.equal(proof.provider_vehicle_id,'5981300');assert.equal(proof.unit,'26');
  await assert.rejects(reviewedFuelIdentity({},vehicle,async()=>({vin:'1M8GDM9AXKP042788',source_vin_state:null})),/reviewed_fuel_identity_changed/);
  await collectPlannedDays({output:path.join(dir,'source.json'),planPath:path.join(dir,'plan.json'),plan:freshPlan,result,
   tasks:{assertFresh(){},run:async(_stage,key,read)=>{assert.equal(key.length,4);return read();}},context:{},company:async()=>{},readIdentity:identity,
   capture:async()=>{calls.push('report');return {record:{report_date:'2026-10-25',source_read_at:new Date().toISOString()},report:{report_date:'2026-10-25'}};},
   finalize:source=>{const doc=JSON.parse(fs.readFileSync(source));const record=doc.vehicles[0].records[0];assert.ok(record.identity_before);assert.ok(record.identity_after);finalized++;}});
  assert.deepEqual(calls,['identity','report','identity']);assert.equal(finalized,1);
 }finally{for(const k of Object.keys(env)){if(savedEnv[k]===undefined)delete process.env[k];else process.env[k]=savedEnv[k];}fs.rmSync(dir,{recursive:true,force:true});}
});
