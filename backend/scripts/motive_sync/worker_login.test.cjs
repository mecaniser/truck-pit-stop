const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
function adapter(prepare){
 const file=path.join(__dirname,'worker_login.cjs'),m=new Module(file,module);m.filename=file;
 const actual=Module.createRequire(file);m.require=name=>name==='../motive_health/login.cjs'?{prepareHealthLogin:prepare}:actual(name);
 m._compile(fs.readFileSync(file,'utf8'),file);return m.exports.prepareWorkerLogin;
}
for(const worker of ['trips','fuel','drivers'])test(`${worker} delegates exact options and static diagnostics to reviewed login`,async()=>{
 const browser={},context={},page={},events=[],phase=()=>{};
 const prepare=adapter(async(b,o)=>{assert.equal(b,browser);assert.equal(o.phase,phase);assert.equal(o.lookupEmail,'fixture@example.invalid');assert.equal(o.lookupPassword,'synthetic-only');assert.equal(o.timeout,123);for(const stage of ['health_login_context_recovery','health_login_context_recovered','health_login_lookup_recovery','health_login_lookup_recovered'])o.diagnostic(stage);return {context,page,authenticated:true};});
 const result=await prepare(browser,{worker,phase,lookupEmail:'fixture@example.invalid',lookupPassword:'synthetic-only',timeout:123,diagnostic:stage=>events.push(stage)});
 assert.equal(result.context,context);assert.equal(result.page,page);assert.equal(result.authenticated,true);
 assert.deepEqual(events,['login_context_recovery','login_context_recovered','login_lookup_recovery','login_lookup_recovered'].map(s=>`${worker}_${s}`));
});
for(const worker of [undefined,'health','sync','fuel/other',{},1])test(`invalid worker label rejects before browser use: ${String(worker)}`,()=>{
 let called=false;const prepare=adapter(()=>{called=true;});assert.throws(()=>prepare({}, {worker}),/login_worker_invalid/);assert.equal(called,false);
});
test('reviewed login failure propagates unchanged with no fallback/retry',async()=>{
 const error=new Error('login_form_target');let calls=0;
 const prepare=adapter(async()=>{calls++;throw error;});await assert.rejects(prepare({}, {worker:'fuel'}),e=>e===error);assert.equal(calls,1);
});
const collectors={fuel:'collect_fuel.cjs',trips:'collect_trips.cjs',drivers:'../motive_drivers/collect.cjs'};
async function caller(worker,authenticated,error){
 const file=path.resolve(__dirname,collectors[worker]),actual=Module.createRequire(file),events=[];
 const page={
  async goto(url){assert.ok(url.endsWith('/admin/company'));events.push('company_source_gate');throw new Error('fixture_company_gate');},
  locator(selector){return {async fill(value){assert.equal(value,selector.includes('password')?'synthetic-only':'fixture@example.invalid');events.push(selector.includes('password')?'password_fill':'email_fill');}};},
  getByRole(role,{name}){return {async click(){assert.equal(name,'Log in');events.push('legacy_submit');}};},
  async waitForURL(url){assert.equal(url,'https://app.gomotive.com/**');events.push('legacy_app_redirect');},
  async close(){events.push('page_closed');},
 };
 const context={async newPage(){return page;}},browser={};
 const m=new Module(file,module);m.filename=file;m.paths=Module._nodeModulePaths(path.dirname(file));
 m.require=name=>{
  if(name.endsWith('worker_login.cjs'))return {async prepareWorkerLogin(b,options){assert.equal(b,browser);assert.equal(options.worker,worker);assert.equal(options.lookupEmail,'fixture@example.invalid');assert.equal(options.lookupPassword,'synthetic-only');events.push('reviewed_preparation');if(error)throw error;return {context,page,authenticated};}};
  if(name==='playwright'||name.endsWith('node_modules/playwright'))return {chromium:{async launch(){return browser;}}};
  if(name==='node:fs')return {...fs,writeFileSync(){},chmodSync(){},renameSync(){}};
  if(name.endsWith('tasks.cjs'))return {...actual(name),phase:s=>events.push(s),async closeBrowser(){events.push('browser_closed');}};
  if(name.endsWith('vehicle_identity.cjs'))return {...actual(name),allowlist:()=>new Map()};
  return actual(name);
 };
 const environment={MOTIVE_COMPANY_LABEL:'fixture',MOTIVE_COMPANY_ID:'fixture',MOTIVE_EMAIL:'fixture@example.invalid',MOTIVE_PASSWORD:'synthetic-only'};
 m._compile('const process={env:'+JSON.stringify(environment)+'};\n'+fs.readFileSync(file,'utf8'),file);
 let failure;try{await m.exports.collect('synthetic-output.json');}catch(e){failure=e;}
 return {events,failure};
}
for(const worker of Object.keys(collectors)){
 test(`${worker} actual collector never re-submits credentials after authenticated native success`,async()=>{
  const {events,failure}=await caller(worker,true);assert.equal(failure.message,'fixture_company_gate');
  assert.equal(events.filter(s=>s==='email_fill'||s==='password_fill'||s==='legacy_submit').length,0);assert.ok(events.includes('company_before'));assert.equal(events.at(-1),'browser_closed');
 });
 for(const flag of [undefined,false,'true',1,{},[]])test(`${worker} actual collector skips legacy only for boolean true (${String(flag)})`,async()=>{
  const {events,failure}=await caller(worker,flag);assert.equal(failure.message,'fixture_company_gate');
  assert.equal(events.filter(s=>s==='email_fill').length,1);assert.equal(events.filter(s=>s==='password_fill').length,1);assert.equal(events.filter(s=>s==='legacy_submit').length,1);assert.ok(events.indexOf('reviewed_preparation')<events.indexOf('email_fill'));assert.ok(events.indexOf('legacy_submit')<events.indexOf('company_before'));assert.equal(events.at(-1),'browser_closed');
 });
 test(`${worker} actual collector propagates auth failure before credentials/company/capture`,async()=>{
  const error=new Error('login_form_ambiguous'),{events,failure}=await caller(worker,false,error);assert.equal(failure,error);assert.equal(events.filter(s=>['email_fill','password_fill','legacy_submit','company_before'].includes(s)).length,0);assert.equal(events.at(-1),'browser_closed');
 });
}
