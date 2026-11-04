/* Rendered official authentication only; no session copying or credential retries. */
const {prepareLoginContext}=require('../motive_sync/login_context.cjs');
const {performance}=require('node:perf_hooks');
const AUTH='https://auth.gomotive.com',APP='https://app.gomotive.com';
function trusted(raw,path){
 let url;try{url=new URL(raw);}catch{throw new Error('login_origin');}
 if(url.origin!==AUTH||url.username||url.password||url.pathname!==path)throw new Error('login_origin');
 return url;
}
async function reviewedForm(page,stage,email){
 trusted(page.url(),stage==='lookup'?'/login/lookup':'/login/authenticate');
 const lookup=page.locator('input[name="email"]:visible');
 const password=page.locator('input[name="user_profile[password]"]:visible');
 if(await lookup.count()!==(stage==='lookup'?1:0)||await password.count()!==(stage==='password'?1:0)||await page.locator('input[name="user_profile[email]"]:visible').count())throw new Error('login_form_ambiguous');
 for(const [name,count] of [['email',stage==='lookup'?1:0],['user_profile[password]',stage==='password'?1:0],['user_profile[email]',stage==='password'?1:0]])if(await page.locator(`input[name="${name}"]`).count()!==count)throw new Error('login_form_ambiguous');
 const input=stage==='lookup'?lookup:password;
 const inputType=(await input.getAttribute('type')||'text').toLowerCase();
 if(!(stage==='lookup'?['text','email'].includes(inputType):inputType==='password')||await input.getAttribute('form')!==null)throw new Error('login_form_target');
 const form=page.locator('form').filter({has:input});
 const name=stage==='lookup'?'Continue':'Log in';
 if(await form.count()!==1||await page.getByRole('button',{name,exact:true}).count()!==1)throw new Error('login_form_ambiguous');
 const button=form.getByRole('button',{name,exact:true});
 if(await button.count()!==1)throw new Error('login_form_ambiguous');
 if(await page.locator('input:visible').count()!==1||await page.locator('textarea:visible,select:visible,iframe:visible').count())throw new Error('login_form_ambiguous');
 // Use the browser's effective native action, including document.baseURI.
 const action=await form.evaluate(element=>element.action);
 let target;try{target=trusted(action,'/login/authenticate');}catch{throw new Error('login_form_target');}
 if(target.search||target.hash||(await form.getAttribute('method')||'get').toLowerCase()!=='post'||!['','_self'].includes(await form.getAttribute('target')||''))throw new Error('login_form_target');
 if(await page.locator('base[target]').count())throw new Error('login_form_target');
 for(const attribute of ['formaction','formmethod','formtarget','form'])if(await button.getAttribute(attribute)!==null)throw new Error('login_form_target');
 const type=await button.getAttribute('type');if(type&&type.toLowerCase()!=='submit')throw new Error('login_form_target');
 if(stage==='password'){
  const hidden=form.locator('input[name="user_profile[email]"]');
  if(await hidden.count()!==1||await hidden.getAttribute('type')!=='hidden'||await hidden.getAttribute('form')!==null||await hidden.inputValue()!==email)throw new Error('login_account_mismatch');
 }
 return {input,button};
}
async function lookupPasswordLogin(browser,{lookupEmail,lookupPassword,phase=()=>{},diagnostic=stage=>console.log(JSON.stringify({stage})),fallbackTimeout=15000,anonymousCleanup=async()=>{}}={}){
 if(typeof lookupEmail!=='string'||!lookupEmail||typeof lookupPassword!=='string'||!lookupPassword||!Number.isFinite(fallbackTimeout)||fallbackTimeout<=0||fallbackTimeout>15000)throw new Error('login_fallback_config');
 const deadline=performance.now()+fallbackTimeout;
 let context;
 const remaining=()=>{const value=deadline-performance.now();if(value<=0)throw new Error('login_form_timeout');return value;};
 const close=resource=>{try{Promise.resolve(resource.close()).catch(()=>{});}catch{}};
 async function budget(operation,dispose=false){
  const milliseconds=remaining();let timer,expired=false;
  const pending=Promise.resolve().then(operation);pending.then(value=>{if(expired&&dispose)close(value);},()=>{});
  try{
   const value=await Promise.race([pending,new Promise((_,reject)=>{timer=setTimeout(()=>{expired=true;reject(new Error('login_form_timeout'));},milliseconds);})]);
   try{remaining();}catch(error){if(dispose)close(value);throw error;}return value;
  }finally{clearTimeout(timer);}
 }
 try{
  diagnostic('health_login_lookup_recovery');
  await budget(anonymousCleanup);
  context=await budget(()=>browser.newContext({timezoneId:'America/New_York',locale:'en-US'}),true);
  const page=await budget(()=>context.newPage(),true);page.setDefaultTimeout(15000);
  phase('login_navigate');await budget(()=>page.goto(APP,{waitUntil:'domcontentloaded',timeout:remaining()}));
  phase('login_auth_redirect');await budget(()=>page.waitForURL('https://auth.gomotive.com/login/lookup**',{timeout:remaining()}));
  phase('login_lookup_email');
  let form=await budget(()=>reviewedForm(page,'lookup',lookupEmail));
  await budget(()=>form.input.fill(lookupEmail,{timeout:remaining()}));
  form=await budget(()=>reviewedForm(page,'lookup',lookupEmail));
  if(await budget(()=>form.input.inputValue())!==lookupEmail)throw new Error('login_account_mismatch');
  phase('login_lookup_submit');await budget(()=>form.button.click({timeout:remaining()}));
  await budget(()=>page.waitForURL('https://auth.gomotive.com/login/authenticate**',{timeout:remaining()}));
  phase('login_password');form=await budget(()=>reviewedForm(page,'password',lookupEmail));
  await budget(()=>form.input.fill(lookupPassword,{timeout:remaining()}));
  form=await budget(()=>reviewedForm(page,'password',lookupEmail));
  phase('login_submit');await budget(()=>form.button.click({timeout:remaining()}));
  phase('login_app_redirect');await budget(()=>page.waitForURL('https://app.gomotive.com/**',{timeout:remaining()}));
  remaining();diagnostic('health_login_lookup_recovered');return {context,page,authenticated:true};
 }catch(error){if(context)close(context);throw error;}
}
async function prepareHealthLogin(browser,options={}){
 const disposals=[];
 const anonymousBrowser=options.lookupEmail&&options.lookupPassword?{async newContext(config){
  const context=await browser.newContext(config),close=context.close.bind(context);let pending;
  context.close=(...args)=>{if(!pending){pending=Promise.resolve().then(()=>close(...args));disposals.push(pending);}return pending;};
  return context;
 }}:browser;
 try{return await prepareLoginContext(anonymousBrowser,{...options,recoveryStage:'health_login_context_recovery',recoveredStage:'health_login_context_recovered'});}
 catch(error){
  // Finish every initiated anonymous disposal inside the modern budget before
  // creating a credential-bearing context. Other errors remain terminal.
  if(error?.message!=='login_legacy_redirect_loop'||!options.lookupEmail||!options.lookupPassword)throw error;
  return lookupPasswordLogin(browser,{...options,anonymousCleanup:()=>Promise.all(disposals)});
 }
}
module.exports={prepareHealthLogin,lookupPasswordLogin,reviewedForm};
