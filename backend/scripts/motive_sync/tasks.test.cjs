const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {openTasks,retry,failed}=require('./tasks.cjs');
const timeout=()=>Object.assign(new Error('PRIVATE_PROVIDER_VALUE'),{name:'TimeoutError'});
function fixture(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'motive-tasks-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return path.join(dir,'source.json');}
test('process replacement resumes completed reports, retaining original read timestamps',async t=>{
 const output=fixture(t), scope={company:'synthetic',directory:['1'],date:'2026-10-21'};
 let time=10000, reads=0;
 let tasks=openTasks(output,scope,{now:()=>time});
 const original=await tasks.run('fuel_report',['1','2026-10-21'],async()=>({source_read_at:'original',value:5}));
 await assert.rejects(tasks.run('fuel_report',['2','2026-10-21'],async()=>{throw new Error('synthetic_failure');}),/synthetic_failure/);
 time=11000;tasks=openTasks(output,scope,{now:()=>time});
 assert.deepEqual(await tasks.run('fuel_report',['1','2026-10-21'],async()=>{reads++;return {};}),original);
 assert.equal(reads,0);assert.equal(tasks.startedAt,new Date(10000).toISOString());
 assert.equal((fs.statSync(output+'.tasks.json').mode&0o777),0o600);
 assert.equal(await tasks.run('fuel_report',['2','2026-10-21'],async()=>7),7);
});
test('changed scope, tenant, reviewed policy and corrupt contents fail closed',async t=>{
 const output=fixture(t),scope={company:'one',directory:['1'],date:'today'};
 await openTasks(output,scope).run('report','1',async()=>5);
 for(const change of [{company:'two'},{directory:['2']},{date:'yesterday'}])assert.throws(()=>openTasks(output,{...scope,...change}),/scope_changed/);
 const saved=process.env.MOTIVE_SYNC_TENANT_ID;
 process.env.MOTIVE_SYNC_TENANT_ID='changed';
 assert.throws(()=>openTasks(output,scope),/scope_changed/);
 if(saved===undefined)delete process.env.MOTIVE_SYNC_TENANT_ID;else process.env.MOTIVE_SYNC_TENANT_ID=saved;
 const savedPolicy=process.env.MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST;
 process.env.MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST='changed';
 assert.throws(()=>openTasks(output,scope),/scope_changed/);
 if(savedPolicy===undefined)delete process.env.MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST;else process.env.MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST=savedPolicy;
 const file=output+'.tasks.json',state=JSON.parse(fs.readFileSync(file));
 state.tasks[Object.keys(state.tasks)[0]]=999;fs.writeFileSync(file,JSON.stringify(state));
 assert.throws(()=>openTasks(output,scope),/checkpoint_invalid/);
});
test('absolute expiry never slides and future artifacts are rejected',async t=>{
 const output=fixture(t);let time=1000;
 const options={maxAgeMs:100,now:()=>time};
 const task=openTasks(output,{},options);await task.run('report',1,async()=>5);
 time=1101;assert.throws(()=>task.assertFresh(),/expired/);assert.throws(()=>openTasks(output,{},options),/expired/);
 time=900;assert.throws(()=>openTasks(output,{},options),/expired/);
});
test('current identity must pass before using cached driver content',async t=>{
 const output=fixture(t),tasks=openTasks(output,{});
 await tasks.run('driver_detail',1,async()=>({vin:'original'}));
 await assert.rejects(tasks.run('driver_detail',1,async()=>({vin:'changed'}),{validateCached:async()=>{throw new Error('vehicle_identity_changed');}}),/vehicle_identity_changed/);
});
test('retry only transient reads; fatal and unknown failures never retry or reveal content',async()=>{
 let calls=0;const logs=[];
 assert.equal(await retry('report',async()=>{if(++calls<3)throw timeout();return 9;},{pause:async()=>{},log:x=>logs.push(x)}),9);
 assert.equal(calls,3);assert.equal(JSON.stringify(logs).includes('PRIVATE'),false);
 for(const reason of ['company_mismatch','vehicle_identity_changed','session_lost','unknown_PRIVATE']) {
  calls=0;await assert.rejects(retry('report',async()=>{calls++;throw new Error(reason);},{pause:async()=>{},log:()=>{}}));assert.equal(calls,1);
 }
 calls=0;await assert.rejects(retry('report',async()=>{calls++;throw timeout();},{pause:async()=>{},log:()=>{}}));assert.equal(calls,3);
});
test('unsafe file permissions, corrupt JSON and symlinks fail closed',async t=>{
 const output=fixture(t),file=output+'.tasks.json';
 fs.writeFileSync(file,'{}',{mode:0o644});assert.throws(()=>openTasks(output,{}),/checkpoint_invalid/);
 fs.chmodSync(file,0o600);fs.writeFileSync(file,'{');assert.throws(()=>openTasks(output,{}));
 fs.unlinkSync(file);fs.symlinkSync(output,file);fs.writeFileSync(output,'{}');assert.throws(()=>openTasks(output,{}),/checkpoint_invalid/);
});
test('unavailable observations are retried rather than frozen as completed tasks',async t=>{
 const tasks=openTasks(fixture(t),{});let reads=0;
 for(let i=0;i<2;i++)await tasks.run('health_vehicle',1,async()=>({state:'unavailable',count:++reads}),{cacheable:x=>x.state==='captured'});
 assert.equal(reads,2);
});
test('failure marker has safe classification and no raw exception content',t=>{
 const output=fixture(t);failed(output,timeout());const marker=JSON.parse(fs.readFileSync(output+'.failure.json'));
 assert.equal(marker.retryable,true);assert.equal(JSON.stringify(marker).includes('PRIVATE'),false);
});
test('daily trip tasks cover exactly the original three dates at New York midnight',()=>{
 const {dailyWindows}=require('./collect_trips.cjs');
 assert.deepEqual(dailyWindows(new Date('2026-10-22T03:59:59Z')),[{start:'2026-10-19',end:'2026-10-19'},{start:'2026-10-20',end:'2026-10-20'},{start:'2026-10-21',end:'2026-10-21'}]);
});

test('real Playwright transport prefixes retry only allowlisted network failures',async()=>{
 const {transient}=require('./tasks.cjs');
 assert.equal(transient(new Error('page.goto: net::ERR_CONNECTION_RESET at https://private.test')),true);
 assert.equal(transient(new Error('page.goto: net::ERR_CERT_AUTHORITY_INVALID at https://private.test')),false);
 assert.equal(transient(new Error('session_lost net::ERR_CONNECTION_RESET')),false);
});
test('browser cleanup has a fixed deadline',async()=>{
 const {closeBrowser}=require('./tasks.cjs');
 await closeBrowser({close:async()=>{}});
 await assert.rejects(closeBrowser({close:()=>new Promise(()=>{})},{timeoutMs:20}),/browser_cleanup_failed/);
});
