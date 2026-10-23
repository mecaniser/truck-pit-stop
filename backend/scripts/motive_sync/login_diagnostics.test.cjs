const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {phase,failureDiagnostic}=require('./tasks.cjs');
const steps=['login_navigate','login_auth_redirect','login_email','login_password','login_submit','login_app_redirect'];
for(const file of ['collect.cjs','collect_trips.cjs','collect_fuel.cjs','../motive_health/collect.cjs','../motive_drivers/collect.cjs']) {
 test(`${file}: every login operation identifies its failure without leaking browser content`,async()=>{
  const source=fs.readFileSync(path.join(__dirname,file),'utf8');
  const start=source.indexOf("phase('login_navigate');");
  const terminal="await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});";
  const end=source.indexOf(terminal,start)+terminal.length;
  assert.ok(start>=0&&end>start);
  const execute=new (Object.getPrototypeOf(async function(){}).constructor)('page','phase','ORIGIN',source.slice(start,end));
  for(let target=0;target<steps.length;target++) {
   let operation=0;
   const act=async()=>{if(operation++===target)throw Object.assign(new Error('password=PRIVATE cookie=PRIVATE https://secret/?token=PRIVATE'),{name:'TimeoutError'});};
   const page={goto:act,waitForURL:act,url:()=> 'https://auth.gomotive.com/login',locator:()=>({fill:act}),getByRole:()=>({click:act})};
   await assert.rejects(execute(page,phase,'https://app.gomotive.com'),error=>{
    assert.deepEqual(failureDiagnostic(error),{phase:steps[target],error_kind:'browser_timeout'});return true;
   });
  }
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
