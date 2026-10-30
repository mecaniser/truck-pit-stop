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
  if(name==='./sync_login.cjs')return {prepareSyncLogin:(browser,opts)=>prepareSyncLogin(browser,{...opts,diagnostic:value=>f.events.push(value),timeout:options.timeout||200,now:options.clock?f.now:undefined})};
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
test('persistent replacement loop terminates without credentials or a third context',async()=>{
 const f=await collector({contexts:[{form:'loop'},{form:'loop'}]});assert.equal(f.error.message,'login_legacy_redirect_loop');assert.equal(f.contexts.length,2);
 assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='fill').length,0);assert.equal(f.events.filter(x=>Array.isArray(x)&&x[0]==='click'&&x[2]==='Use legacy login').length,4);assert.ok(f.closed());
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
