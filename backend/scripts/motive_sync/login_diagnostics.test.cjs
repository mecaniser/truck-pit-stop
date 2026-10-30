const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {phase,failureDiagnostic}=require('./tasks.cjs');
const steps=['login_navigate','login_auth_redirect','login_email','login_password','login_submit','login_app_redirect'];
for(const file of ['collect.cjs','collect_trips.cjs','collect_fuel.cjs','../motive_health/collect.cjs','../motive_drivers/collect.cjs']) {
 test(`${file}: every login operation identifies its failure without leaking browser content`,async()=>{
  const source=fs.readFileSync(path.join(__dirname,file),'utf8');
  const delegated=file==='../motive_health/collect.cjs'||file==='collect.cjs';
  const checkedSteps=delegated?steps.slice(2):steps;
  const start=source.indexOf(delegated?"phase('login_email');":"phase('login_navigate');");
  const terminal="await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});";
  const end=source.indexOf(terminal,start)+terminal.length;
  assert.ok(start>=0&&end>start);
  const execute=new (Object.getPrototypeOf(async function(){}).constructor)('page','phase','ORIGIN','prepareLegacyLogin',source.slice(start,end));
  for(let target=0;target<checkedSteps.length;target++) {
   let operation=0;
   const act=async()=>{if(operation++===target)throw Object.assign(new Error('password=PRIVATE cookie=PRIVATE https://secret/?token=PRIVATE'),{name:'TimeoutError'});};
   const page={goto:act,waitForURL:act,url:()=> 'https://auth.gomotive.com/login',locator:()=>({fill:act}),getByRole:()=>({click:act})};
   await assert.rejects(execute(page,phase,'https://app.gomotive.com',async()=>{}),error=>{
    assert.deepEqual(failureDiagnostic(error),{phase:checkedSteps[target],error_kind:'browser_timeout'});return true;
   });
  }
  if(delegated)return; // Anonymous navigation is exercised through each wrapper below.
  let filled=false;
  await assert.rejects(execute({goto:async()=>{},waitForURL:async()=>{},url:()=> 'https://unexpected.invalid/',locator:()=>{filled=true;}},phase,'https://app.gomotive.com'),error=>{
   assert.deepEqual(failureDiagnostic(error),{phase:'login_origin_check',error_kind:'unexpected_login_origin'});return true;
  });
  assert.equal(filled,false);
 });
}
test('diagnostic classification allows only known categories, never raw error fields',()=>{
 phase('login_submit');
 for(const name of ['CONNECTION_RESET','CONNECTION_CLOSED','TIMED_OUT','NETWORK_CHANGED']) {
  assert.equal(failureDiagnostic(new Error(`page.goto: net::ERR_${name} https://PRIVATE/?token=PRIVATE`)).error_kind,'network_'+name.toLowerCase());
 }
 assert.equal(failureDiagnostic(new Error('PRIVATE')).error_kind,'unclassified');
 phase('unrecognized');
 assert.deepEqual(failureDiagnostic({name:'PRIVATE',message:'PRIVATE'}),{phase:'other',error_kind:'unclassified'});
});

test('legacy preflight diagnostics expose static categories only',()=>{
 for(const stage of ['login_form_check','login_legacy_link','login_legacy_retry','login_legacy_redirect']){
  phase(stage);
  for(const reason of ['login_form_timeout','login_form_ambiguous','login_legacy_link_ambiguous','login_legacy_link_invalid','login_legacy_redirect_loop']){
   assert.deepEqual(failureDiagnostic(new Error(reason)),{phase:stage,error_kind:reason});
  }
  assert.deepEqual(failureDiagnostic(new Error('https://private.invalid/?secret=PRIVATE')),{phase:stage,error_kind:'unclassified'});
 }
});

// Health and sync delegate only anonymous bootstrap to the bounded orchestrator.
// Preserve fault injection of both navigation boundaries and the origin guard.
const {prepareHealthLogin}=require('../motive_health/login.cjs');
const {prepareSyncLogin}=require('./sync_login.cjs');
for(const [kind,prepare] of [['health',prepareHealthLogin],['sync',prepareSyncLogin]])
for(const target of ['login_navigate','login_auth_redirect','login_origin_check'])test(`${kind} bootstrap diagnostic ${target} stays static`,async()=>{
 const error=Object.assign(new Error('password=PRIVATE cookie=PRIVATE https://secret/?token=PRIVATE'),{name:'TimeoutError'});
 const page={setDefaultTimeout(){},async goto(){if(target==='login_navigate')throw error;},async waitForURL(){if(target==='login_auth_redirect')throw error;},url:()=>target==='login_origin_check'?'https://unexpected.invalid/':'https://auth.gomotive.com/login'};
 const browser={async newContext(){return {async newPage(){return page;},async close(){}};}};
 await assert.rejects(prepare(browser,{phase,diagnostic(){}}),actual=>{
  assert.deepEqual(failureDiagnostic(actual),{phase:target,error_kind:target==='login_origin_check'?'unexpected_login_origin':'browser_timeout'});return true;
 });
});
