const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const fs=require('node:fs'),path=require('node:path'),{EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {prepareSyncLogin}=require('./sync_login.cjs');
const actualRequire=createRequire(path.join(__dirname,'collect.cjs'));
function credentialOrigin(){const value=new URL('https://auth.gomotive.com');value.username='fixture-user';value.password='synthetic-only';return value.href.slice(0,-1);}
function fixture(options={}){
 const events=[],contexts=[];let tick=0,closed=false;
 const settings=options.contexts||[{form:'legacy'}];
 const browser={async newContext(config){
  const ordinal=contexts.length;events.push(['new_context',ordinal,config]);
  const setting=settings[ordinal]||settings.at(-1);tick+=setting.createMs||0;
  if(setting.createError)throw new Error(setting.createError);
  const page=new EventEmitter();let current=(setting.origin||'https://auth.gomotive.com')+(setting.path||(setting.form==='legacy'?'/login':'/login/lookup'));
  Object.assign(page,{
   ordinal,url:()=>current,mainFrame:()=>page,
   setDefaultTimeout(value){events.push(['default_timeout',ordinal,value]);},
   async goto(url,args){events.push(['goto',ordinal,url,args]);tick+=setting.navigateMs||0;if(setting.navigateError)throw new Error(setting.navigateError);},
   async waitForURL(url,args){events.push(['wait_url',ordinal,url,args]);tick+=setting.authMs||0;if(url==='https://app.gomotive.com/**')throw new Error(options.afterSubmit||'fixture_after_submit');},
   async waitForTimeout(){},
   locator(selector){return {
    async count(){if(setting.countError)throw new Error(setting.countError);if(setting.missingForm)return 0;if(new URL(current).pathname!=='/login')return setting.partial?1:0;return setting.ambiguous?2:1;},
    async fill(){events.push(['fill',ordinal,selector]);},
   };},
   getByRole(role,{name}){return {
    async count(){return setting.missingLink&&role==='link'?0:setting.duplicateLink&&role==='link'?2:1;},
    async getAttribute(){return setting.href||'#';},
    async click(){events.push(['click',ordinal,name]);if(role==='link'){
     current=setting.form==='loop'?'https://auth.gomotive.com/login/lookup':'https://auth.gomotive.com/login';
     page.emit('framenavigated',page);page.emit('domcontentloaded');
     tick+=setting.clickMs||0;
    }},
   };},
  });
  const context={ordinal,page,closed:false,async grantPermissions(permissions,options){events.push(['permissions',ordinal,permissions,options]);if(setting.permissionsError)throw new Error(setting.permissionsError);},async newPage(){tick+=setting.pageMs||0;if(setting.pageError)throw new Error(setting.pageError);return page;},async close(){events.push(['close_context',ordinal]);this.closed=true;tick+=setting.closeMs||0;if(setting.closeError)throw new Error(setting.closeError);}};
  contexts.push(context);
  if(setting.createDelay)await new Promise(resolve=>setTimeout(resolve,setting.createDelay));
  return context;
 },async close(){closed=true;events.push(['close_browser']);for(const context of contexts)if(!context.closed)try{await context.close();}catch{}}};
 return {browser,events,contexts,now:()=>tick,closed:()=>closed};
}
async function collector(options={}){
 const f=fixture(options),module={exports:{}};
 const mockedRequire=name=>{
  if(name==='node:fs')return {writeFileSync(){},chmodSync(){},renameSync(){}};
  if(name==='./tasks.cjs')return {phase:value=>f.events.push(value),closeBrowser:browser=>browser.close()};
  if(name==='playwright')return {chromium:{launch:async()=>{f.events.push('launch');return f.browser;}}};
  if(name==='./sync_login.cjs')return {prepareSyncLogin:async(browser,opts)=>{
   if(Object.hasOwn(options,'authenticatedResult')){
    const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US'}),page=await context.newPage();
    return {context,page,authenticated:options.authenticatedResult};
   }
   return prepareSyncLogin(browser,{...opts,diagnostic:value=>f.events.push(value),timeout:options.timeout||200,now:options.clock?f.now:undefined});
  }};
  return actualRequire(name);
 };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'collect.cjs'),'utf8'),{require:mockedRequire,module,process:{env:{MOTIVE_EMAIL:'fixture@example.invalid',MOTIVE_PASSWORD:'synthetic-only'}},URL,console});
 let error;try{await module.exports.collect('synthetic-output');}catch(value){error=value;}
 return {...f,error};
}
for(const form of ['legacy','lookup'])test(`actual sync collector ${form} path uses one context and one credential submission`,async()=>{
 const f=await collector({contexts:[{form}]});assert.equal(f.error.message,'fixture_after_submit');assert.equal(f.contexts.length,1);
 assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,2);
 assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='click'&&x[2]==='Log in').length,1);
 assert.equal(f.events.filter(x=>x==='launch').length,1);assert.ok(f.closed());
});
for(const value of ['true',1,{},[]])test('actual collector skips legacy submission only for boolean authenticated true',async()=>{
 const f=await collector({authenticatedResult:value});assert.equal(f.error.message,'fixture_after_submit');
 assert.equal(f.events.filter(event=>Array.isArray(event)&&event[0]==='fill').length,2);
 assert.equal(f.events.filter(event=>Array.isArray(event)&&event[0]==='click'&&event[2]==='Log in').length,1);assert.ok(f.closed());
});
test('actual collector recovers a confirmed anonymous loop once and submits only on replacement',async()=>{
 const f=await collector({contexts:[{form:'loop'},{form:'legacy'}]});assert.equal(f.error.message,'fixture_after_submit');assert.equal(f.contexts.length,2);
 const created=f.events.findIndex(x=>Array.isArray(x)&&x[0]==='new_context'&&x[1]===1),disposed=f.events.findIndex(x=>Array.isArray(x)&&x[0]==='close_context'&&x[1]===0);
 assert.ok(disposed<created);assert.ok(f.events.includes('sync_login_context_recovery'));assert.ok(f.events.includes('sync_login_context_recovered'));
 const fills=f.events.filter(x=>Array.isArray(x)&&x[0]==='fill');assert.equal(fills.length,2);assert.ok(fills.every(x=>x[1]===1));
 assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='click'&&x[2]==='Use legacy login').length,2);
 assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='click'&&x[2]==='Log in').length,1);
 assert.equal(f.events.filter(x=>x==='launch').length,1);assert.ok(f.closed());
 for(const event of f.events.filter(x=>Array.isArray(x)&&x[0]==='new_context'))assert.equal(JSON.stringify(event[2]),JSON.stringify({timezoneId:'America/New_York',locale:'en-US'}));
 assert.ok(f.events.filter(x=>Array.isArray(x)&&x[0]==='default_timeout').every(x=>x[2]===15000));
});
test('persistent replacement loop without fallback credentials remains terminal before a third context',async()=>{
 const f=fixture({contexts:[{form:'loop'},{form:'loop'}]});
 try{await assert.rejects(prepareSyncLogin(f.browser,{timeout:200,diagnostic(){}}),/login_legacy_redirect_loop/);assert.equal(f.contexts.length,2);
 assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,0);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='click'&&x[2]==='Use legacy login').length,4);assert.ok(f.contexts.every(context=>context.closed));}
 finally{await f.browser.close();}
});
for(const [name,setting,error] of [
 ['foreign origin',{form:'legacy',origin:'https://evil.invalid'},'login_origin'],
 ['wrong auth path',{form:'legacy',path:'/other'},'login_origin'],
 ['missing credential form',{form:'legacy',missingForm:true},'login_form_timeout'],
 ['credential-bearing URL',{form:'legacy',origin:credentialOrigin()},'login_origin'],
 ['ambiguous form',{form:'legacy',ambiguous:true},'login_form_ambiguous'],
 ['unsafe link',{form:'lookup',href:'https://evil.invalid/login'},'login_legacy_link_invalid'],
 ['duplicate link',{form:'lookup',duplicateLink:true},'login_legacy_link_ambiguous'],
 ['navigation failure',{form:'legacy',navigateError:'synthetic_navigation_failure'},'synthetic_navigation_failure'],
 ['unknown helper failure',{form:'legacy',countError:'synthetic_private_exception'},'synthetic_private_exception'],
 ['form timeout',{form:'lookup',missingLink:true},'login_form_timeout'],
 ['partial fields on lookup',{form:'loop',partial:true},'login_form_ambiguous'],
])test(`actual collector ${name} never replaces context or fills credentials`,async()=>{
 const f=await collector({contexts:[setting]});assert.equal(f.error.message,error);assert.equal(f.contexts.length,1);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,0);assert.ok(f.closed());
});
test('error after credential submission cannot re-enter anonymous recovery',async()=>{
 const f=await collector({afterSubmit:'login_legacy_redirect_loop'});assert.equal(f.error.message,'login_legacy_redirect_loop');assert.equal(f.contexts.length,1);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='click'&&x[2]==='Log in').length,1);assert.ok(!f.events.includes('sync_login_context_recovery'));
});
test('original deadline exhausted by first loop prevents replacement',async()=>{
 const f=await collector({clock:true,timeout:200,contexts:[{form:'loop',clickMs:110}]});assert.equal(f.error.message,'login_form_timeout');assert.equal(f.contexts.length,1);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,0);
});
test('close and creation time consume original deadline; no replacement navigation after exhaustion',async()=>{
 const f=await collector({clock:true,timeout:200,contexts:[{form:'loop',clickMs:50,closeMs:60},{form:'legacy',createMs:50}]});assert.equal(f.error.message,'login_form_timeout');assert.equal(f.contexts.length,2);assert.ok(f.contexts[1].closed);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='goto'&&x[1]===1).length,0);
});
test('replacement navigation and helper use only remaining original budget',async()=>{
 const f=await collector({clock:true,timeout:200,contexts:[{form:'loop',clickMs:40,closeMs:10},{form:'legacy',createMs:10,navigateMs:30,authMs:10}]});assert.equal(f.error.message,'fixture_after_submit');
 const nav=f.events.find(x=>Array.isArray(x)&&x[0]==='goto'&&x[1]===1),auth=f.events.find(x=>Array.isArray(x)&&x[0]==='wait_url'&&x[1]===1);
 assert.equal(nav[3].timeout,100);assert.equal(auth[3].timeout,70);
});
for(const [name,setting,error] of [
 ['old context close',{form:'loop',closeError:'fixture_close_failed'},'fixture_close_failed'],
 ['replacement creation',{form:'legacy',createError:'fixture_create_failed'},'fixture_create_failed'],
 ['replacement page',{form:'legacy',pageError:'fixture_page_failed'},'fixture_page_failed'],
 ['replacement navigation',{form:'legacy',navigateError:'fixture_navigation_failed'},'fixture_navigation_failed'],
])test(`${name} failure is terminal and closes browser`,async()=>{
 const f=await collector({contexts:name==='old context close'?[setting]:[{form:'loop'},setting]});assert.equal(f.error.message,error);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,0);assert.ok(f.closed());
});
test('a context returned after the deadline is disposed rather than leaked',async()=>{
 const f=fixture({contexts:[{form:'loop'},{form:'legacy',createDelay:60}]});
 await assert.rejects(prepareSyncLogin(f.browser,{timeout:20,diagnostic(){}}),/login_form_timeout/);
 await new Promise(resolve=>setTimeout(resolve,80));assert.equal(f.contexts.length,2);assert.ok(f.contexts[0].closed&&f.contexts[1].closed);await f.browser.close();
});

async function chromiumFixture({persistent=false,replacementOrigin='https://auth.gomotive.com'}={}){
 const {chromium}=require('playwright');
 const raw=await chromium.launch({headless:true,args:['--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND']});
 const events=[],contexts=[];
 const browser={async newContext(options){
  const ordinal=contexts.length,context=await raw.newContext(options);contexts.push(context);events.push(['create',ordinal,{...options}]);
  const originalClose=context.close.bind(context);context.close=async()=>{events.push(['close',ordinal]);await originalClose();};
  await context.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(!['https://app.gomotive.com','https://auth.gomotive.com','https://evil.invalid'].includes(url.origin))return route.abort();
   if(url.origin==='https://app.gomotive.com')return route.fulfill({contentType:'text/html',body:`<script>location.replace('${ordinal&& !persistent?replacementOrigin+'/login':'https://auth.gomotive.com/login/lookup'}')</script>`});
   const body=url.pathname==='/login'?'<input name="user_profile[email]"><input type="password" name="user_profile[password]"><button>Log in</button>':`<input name="email"><button>Continue</button><a href="#" onclick="event.preventDefault();location.assign('/login/lookup?returned='+Date.now())">Use legacy login</a>`;
   return route.fulfill({contentType:'text/html',body});
  });return context;
 },close:()=>raw.close()};
 return {browser,events,contexts};
}
test('real Chromium completed lookup loops replace only the anonymous context and preserve options',async()=>{
 const f=await chromiumFixture(),diagnostics=[];
 try{
  const {page,context}=await prepareSyncLogin(f.browser,{timeout:3000,diagnostic:value=>diagnostics.push(value)});
  assert.equal(f.contexts.length,2);assert.equal(context,f.contexts[1]);assert.equal(new URL(page.url()).pathname,'/login');
  assert.equal(await page.locator('input').evaluateAll(es=>es.some(e=>e.value)),false);
  assert.ok(f.events.findIndex(x=>x[0]==='close'&&x[1]===0)<f.events.findIndex(x=>x[0]==='create'&&x[1]===1));
  assert.deepEqual(diagnostics,['sync_login_context_recovery','sync_login_context_recovered']);
  for(const event of f.events.filter(x=>x[0]==='create'))assert.deepEqual(event[2],{timezoneId:'America/New_York',locale:'en-US'});
  assert.equal(page.listenerCount('domcontentloaded'),0);
 }finally{await f.browser.close();}
});
test('real Chromium persistent replacement loop fails without any credential input',async()=>{
 const f=await chromiumFixture({persistent:true});
 try{await assert.rejects(prepareSyncLogin(f.browser,{timeout:3000,diagnostic(){}}),/login_legacy_redirect_loop/);assert.equal(f.contexts.length,2);assert.equal(f.events.filter(x=>x[0]==='close').length,2);}
 finally{await f.browser.close();}
});
test('real Chromium foreign replacement document fails closed and closes both contexts',async()=>{
 const f=await chromiumFixture({replacementOrigin:'https://evil.invalid'});
 try{await assert.rejects(prepareSyncLogin(f.browser,{timeout:600,diagnostic(){}}),error=>error.message==='login_origin'||error.name==='TimeoutError');assert.equal(f.contexts.length,2);assert.equal(f.events.filter(x=>x[0]==='close').length,2);}
 finally{await f.browser.close();}
});

test('replacement ambiguous form remains terminal without a third context or credentials',async()=>{
 const f=await collector({contexts:[{form:'loop'},{form:'legacy',ambiguous:true}]});assert.equal(f.error.message,'login_form_ambiguous');assert.equal(f.contexts.length,2);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,0);assert.ok(f.closed());
});

test('sync grants clipboard permissions only on the ready returned context before credentials',async()=>{
 const f=await collector({contexts:[{form:'loop'},{form:'legacy'}]});
 const permissions=f.events.filter(x=>Array.isArray(x)&&x[0]==='permissions');
 assert.deepEqual(JSON.parse(JSON.stringify(permissions)),[['permissions',1,['clipboard-read','clipboard-write'],{origin:'https://app.gomotive.com'}]]);
 assert.ok(f.events.indexOf(permissions[0])<f.events.findIndex(x=>Array.isArray(x)&&x[0]==='fill'));
});
test('clipboard permission failure is terminal without credential fill or another context',async()=>{
 const f=await collector({contexts:[{form:'legacy',permissionsError:'fixture_permission_failed'}]});
 assert.equal(f.error.message,'fixture_permission_failed');assert.equal(f.contexts.length,1);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,0);assert.ok(f.closed());
});

// Location-native authentication integration cases run in the existing protected CI suite.
{
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const {createRequire}=require('node:module'),{execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const {prepareSyncLogin}=require('./sync_login.cjs');
const AUTH='https://auth.gomotive.com',APP='https://app.gomotive.com';
const credentials={lookupEmail:'location-fixture@example.invalid',lookupPassword:'location-synthetic-only'};
const actualRequire=createRequire(path.join(__dirname,'collect.cjs'));
function auxiliary(){return '<form style="display:none"><input name="firstName"><input name="lastName"><input type="email" name="email"><textarea name="address"></textarea><textarea name="comments"></textarea><button></button><button></button></form>';}
function sso(){return '<form action="/login/sso" method="post"><input type="hidden" name="email"><input type="hidden" name="authenticity_token"><input type="hidden" name="client_id"><input type="hidden" name="client_secret"><button type="submit">Log in with SSO</button></form>';}
async function fixture(options={}){
 const raw=await chromium.launch({headless:true,args:['--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND']});
 const contexts=[],events=[],requests=[],inputs=[],diagnostics=[];
 const browser={async newContext(config){
  const ordinal=contexts.length,context=await raw.newContext(config);contexts.push(context);events.push(['create',ordinal,config]);
  const close=context.close.bind(context);context.close=async()=>{events.push(['closing',ordinal]);await close();events.push(['closed',ordinal]);};
  await context.exposeBinding('fixtureInput',(_source,name)=>inputs.push({ordinal,name}));
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   requests.push({url:request.url(),method:request.method(),body:request.postData()});
   if(![APP,AUTH,'https://evil.invalid'].includes(url.origin))return route.abort();
   const html=body=>route.fulfill({contentType:'text/html',body:'<script>document.addEventListener("input",event=>window.fixtureInput(event.target.name))</script>'+body});
   if(url.origin===APP){
    if(url.pathname==='/en-US/')return html(`<p>${options.wrongCompany?'OTHER FLEET':'77 CARGO LLC'} KT8934277</p>`);
    return html(`<script>location.replace('${AUTH}/login/lookup')</script>`);
   }
   if(ordinal<2)return html('<input name="email"><button>Continue</button><a href="#" onclick="event.preventDefault();location.assign(\'/login/lookup?returned=\'+Date.now())">Use legacy login</a>');
   if(url.origin!==AUTH)return html('<p>Untrusted destination</p>');
   if(url.pathname==='/login/lookup')return html(`<form action="${options.foreignLookupAction?'https://evil.invalid/login/authenticate':'/login/authenticate'}" method="post"><input type="text" name="email"><button type="submit">Continue</button></form>${auxiliary()}${auxiliary()}${options.thirdAuxiliary?auxiliary():''}`);
   if(url.pathname==='/login/authenticate'){
    const values=new URLSearchParams(request.postData()||'');
    if(values.has('user_profile[password]')&&!options.rejectPassword)return html(`<script>location.replace('${APP}/en-US/')</script>`);
    if(options.ssoRedirect)return html('<script>location.replace("/login/sso")</script>');
    const email=options.wrongAccount?'other@example.invalid':credentials.lookupEmail;
    return html(`<form action="${options.foreignPasswordAction?'https://evil.invalid/login/authenticate':'/login/authenticate'}" method="post"><input type="hidden" name="user_profile[email]" value="${email}"><input type="password" name="user_profile[password]">${options.otp?'<input name="otp" autocomplete="one-time-code">':''}<button type="submit">Log in</button></form>${auxiliary()}${auxiliary()}${sso()}`);
   }
   return html('<p>Additional authentication required</p>');
  });
  return context;
 },close:()=>raw.close()};
 return {browser,contexts,events,requests,inputs,diagnostics};
}
const posts=f=>f.requests.filter(request=>request.method==='POST');
function assertCredentialBoundary(f){
 for(const request of f.requests){
  const url=new URL(request.url);
  assert.equal(url.searchParams.has('email'),false);assert.equal(url.searchParams.has('user_profile[password]'),false);
  if(request.method==='POST'){assert.equal(url.origin,AUTH);assert.equal(url.pathname,'/login/authenticate');}
  if(url.origin!==AUTH)assert.equal(request.body,null);
 }
 assert.ok(posts(f).filter(request=>new URLSearchParams(request.body).has('email')).length<=1);
 assert.ok(posts(f).filter(request=>new URLSearchParams(request.body).has('user_profile[password]')).length<=1);
 assert.ok(f.inputs.every(input=>input.ordinal===2));
 assert.ok(!JSON.stringify(f.diagnostics).includes(credentials.lookupEmail));
 assert.ok(!JSON.stringify(f.diagnostics).includes(credentials.lookupPassword));
}
async function collector(options={}){
 const f=await fixture(options),module={exports:{}},saved=[],phases=[];
 const mockedRequire=name=>{
  if(name==='playwright')return {chromium:{launch:async()=>f.browser}};
  if(name==='./tasks.cjs')return {
   phase(value){phases.push(value);if(value==='timezone')throw new Error('fixture_after_company');},
   atomic(_output,value){saved.push(JSON.parse(JSON.stringify(value)));},
   closeBrowser:browser=>browser.close(),
  };
  if(name==='./sync_login.cjs')return {prepareSyncLogin:(browser,options)=>prepareSyncLogin(browser,{...options,timeout:3000,fallbackTimeout:3000,diagnostic:stage=>f.diagnostics.push(stage)})};
  return actualRequire(name);
 };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'collect.cjs'),'utf8'),{require:mockedRequire,module,process:{env:{MOTIVE_EMAIL:credentials.lookupEmail,MOTIVE_PASSWORD:credentials.lookupPassword}},URL,console});
 let error;try{await module.exports.collect('synthetic-location-source');}catch(value){error=value;}
 return {...f,error,saved,phases};
}
test('actual location collector recovers persistent legacy loops once without duplicate credential submission',async()=>{
 const f=await collector();
 try{
  assert.equal(f.error.message,'fixture_after_company');assert.equal(f.contexts.length,3);
  assert.equal(posts(f).length,2);assert.equal(f.inputs.filter(input=>input.name==='email').length,1);assert.equal(f.inputs.filter(input=>input.name==='user_profile[password]').length,1);
  assert.deepEqual(f.diagnostics,['sync_login_context_recovery','sync_login_lookup_recovery','sync_login_lookup_recovered']);
  assert.ok(f.phases.includes('company_before'));assert.equal(f.phases.filter(phase=>phase==='login_submit').length,1);
  assert.ok(f.phases.includes('timezone'));assert.equal(f.saved.length,0);
  const third=f.events.findIndex(event=>event[0]==='create'&&event[1]===2);
  assert.ok(f.events.findIndex(event=>event[0]==='closed'&&event[1]===1)<third);
  assertCredentialBoundary(f);
 }finally{await f.browser.close();}
});
test('actual location collector still rejects wrong source company after successful modern authentication',async()=>{
 const f=await collector({wrongCompany:true});
 try{
  assert.equal(f.error.message,'company_mismatch');assert.equal(posts(f).length,2);
  assert.equal(f.saved.length,0);assert.ok(!f.phases.includes('timezone'));assertCredentialBoundary(f);
 }finally{await f.browser.close();}
});
for(const [name,options,error,postCount,passwordFills] of [
 ['unsafe lookup target',{foreignLookupAction:true},'login_form_target',0,0],
 ['unreviewed third auxiliary form',{thirdAuxiliary:true},'login_form_ambiguous',0,0],
 ['wrong hidden account',{wrongAccount:true},'login_account_mismatch',1,0],
 ['unsafe password target',{foreignPasswordAction:true},'login_form_target',1,0],
 ['visible OTP challenge',{otp:true},'login_form_ambiguous',1,0],
 ['active SSO redirect',{ssoRedirect:true},'origin_or_timeout',1,0],
 ['rejected password',{rejectPassword:true},'timeout',2,1],
])test(`sync modern ${name} is terminal without another authentication attempt`,async()=>{
 const f=await fixture(options);
 try{
  await assert.rejects(prepareSyncLogin(f.browser,{...credentials,timeout:3000,fallbackTimeout:1500,diagnostic:stage=>f.diagnostics.push(stage)}),value=>error==='origin_or_timeout'?['login_origin','login_form_timeout'].includes(value.message)||value.name==='TimeoutError':error==='timeout'?value.message==='login_form_timeout'||value.name==='TimeoutError':value.message===error);
  assert.equal(f.contexts.length,3);assert.equal(posts(f).length,postCount);
  assert.equal(f.inputs.filter(input=>input.name==='user_profile[password]').length,passwordFills);assertCredentialBoundary(f);
 }finally{await f.browser.close();}
});
test('location Docker backend copy includes the exact reused authentication dependency chain',()=>{
 const backend=path.resolve(__dirname,'../..'),root=path.dirname(backend);
 const manifest=JSON.parse(fs.readFileSync(path.join(root,'railway.motive-location.json'),'utf8'));
 const docker=fs.readFileSync(path.join(root,manifest.build.dockerfilePath),'utf8');
 assert.match(docker,/^COPY backend\/ \.\/$/m);
 assert.equal(manifest.deploy.startCommand,'python -m scripts.motive_sync.run_worker');
 assert.equal(manifest.deploy.cronSchedule,'*/5 * * * *');
 const files=['scripts/motive_sync/sync_login.cjs','scripts/motive_health/login.cjs','scripts/motive_sync/login_context.cjs','scripts/motive_sync/login.cjs'];
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'location-auth-artifact-'));
 try{
  for(const file of files){const target=path.join(directory,file);fs.mkdirSync(path.dirname(target),{recursive:true});fs.copyFileSync(path.join(backend,file),target);}
  execFileSync(process.execPath,['-e',`const assert=require('node:assert/strict');const entry=require.resolve('./scripts/motive_sync/sync_login.cjs');assert.equal(typeof require(entry).prepareSyncLogin,'function');const visited=new Set();function walk(id,ancestors=[]){assert.ok(!ancestors.includes(id),'circular authentication dependency');if(visited.has(id))return;visited.add(id);for(const child of require.cache[id].children)walk(child.id,[...ancestors,id]);}walk(entry);assert.equal(visited.size,4);`],{cwd:directory,env:{...process.env,NODE_PATH:''},stdio:'pipe'});
 }finally{fs.rmSync(directory,{recursive:true,force:true});}
});
}
