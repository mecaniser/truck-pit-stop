/* Rendered official authentication only; no session copying or credential retries. */
const {prepareLoginContext}=require('../motive_sync/login_context.cjs');
const {performance}=require('node:perf_hooks');
const AUTH='https://auth.gomotive.com',APP='https://app.gomotive.com';
function trusted(raw,path){
 let url;try{url=new URL(raw);}catch{throw new Error('login_origin');}
 if(url.origin!==AUTH||url.username||url.password||url.pathname!==path)throw new Error('login_origin');
 return url;
}
function loginError(category,guard){return Object.assign(new Error(category),{loginGuard:guard});}
async function completelyEmptyStartup(page){
 return page.evaluate(()=>{
  if(!document.body||document.querySelector('form,input,textarea,select,button,iframe,[contenteditable]')||document.body.innerText.trim())return false;
  return !Array.from(document.body.querySelectorAll('*')).some(element=>{
   if(['SCRIPT','STYLE','LINK','META','NOSCRIPT','TEMPLATE'].includes(element.tagName))return false;
   const rect=element.getBoundingClientRect(),style=getComputedStyle(element);
   return rect.width>0&&rect.height>0&&style.display!=='none'&&style.visibility!=='hidden';
  });
 });
}
async function reviewedForm(page,stage,email){
 try{trusted(page.url(),stage==='lookup'?'/login/lookup':'/login/authenticate');}catch{throw loginError('login_origin','origin');}
 const lookup=page.locator('input[name="email"]:visible');
 const password=page.locator('input[name="user_profile[password]"]:visible');
 const lookupCount=await lookup.count(),passwordCount=await password.count(),accountVisible=await page.locator('input[name="user_profile[email]"]:visible').count();
 if(lookupCount!==(stage==='lookup'?1:0)||passwordCount!==(stage==='password'?1:0)||accountVisible)throw loginError('login_form_ambiguous',lookupCount===0&&passwordCount===0&&accountVisible===0?'credential_missing':'credential_ambiguous');
 for(const [name,count] of [['email',stage==='lookup'?1:0],['user_profile[password]',stage==='password'?1:0],['user_profile[email]',stage==='password'?1:0]])if(await page.locator(`input[name="${name}"]`).count()!==count)throw loginError('login_form_ambiguous','credential_count');
 const input=stage==='lookup'?lookup:password;
 const inputType=(await input.getAttribute('type')||'text').toLowerCase();
 if(!(stage==='lookup'?['text','email'].includes(inputType):inputType==='password')||await input.getAttribute('form')!==null)throw loginError('login_form_target','input_target');
 const form=page.locator('form').filter({has:input});
 const name=stage==='lookup'?'Continue':'Log in';
 if(await form.count()!==1)throw loginError('login_form_ambiguous','form_count');
 if(await page.getByRole('button',{name,exact:true}).count()!==1)throw loginError('login_form_ambiguous','button_count');
 const button=form.getByRole('button',{name,exact:true});
 if(await button.count()!==1)throw loginError('login_form_ambiguous','button_count');
 if(await page.locator('input:visible').count()!==1)throw loginError('login_form_ambiguous','visible_control_count');
 if(await page.locator('textarea:visible,select:visible,iframe:visible').count())throw loginError('login_form_ambiguous','challenge_control');
 // Use the browser's effective native action, including document.baseURI.
 const action=await form.evaluate(element=>element.action);
 let target;try{target=trusted(action,'/login/authenticate');}catch{throw loginError('login_form_target','form_action');}
 if(target.search||target.hash||(await form.getAttribute('method')||'get').toLowerCase()!=='post'||!['','_self'].includes(await form.getAttribute('target')||''))throw loginError('login_form_target','form_target');
 if(await page.locator('base[target]').count())throw loginError('login_form_target','base_target');
 for(const attribute of ['formaction','formmethod','formtarget','form'])if(await button.getAttribute(attribute)!==null)throw loginError('login_form_target','submit_override');
 const type=await button.getAttribute('type');if(type&&type.toLowerCase()!=='submit')throw loginError('login_form_target','submit_type');
 if(stage==='password'){
  const hidden=form.locator('input[name="user_profile[email]"]');
  if(await hidden.count()!==1||await hidden.getAttribute('type')!=='hidden'||await hidden.getAttribute('form')!==null||await hidden.inputValue()!==email)throw loginError('login_account_mismatch','account_mismatch');
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
 async function initialForm(page,stage){
  let waitingForEmpty=false;
  try{
   for(;;){
    try{trusted(page.url(),stage==='lookup'?'/login/lookup':'/login/authenticate');}catch{throw loginError('login_origin','origin');}
    waitingForEmpty=false;
    if(!await budget(()=>completelyEmptyStartup(page)))return budget(()=>reviewedForm(page,stage,lookupEmail));
    waitingForEmpty=true;
    await budget(()=>page.waitForTimeout(Math.min(25,remaining())));
   }
  }catch(error){if(waitingForEmpty&&error?.message==='login_form_timeout')error.loginGuard='empty_startup_deadline';throw error;}
 }
 try{
  diagnostic('health_login_lookup_recovery');
  await budget(anonymousCleanup);
  context=await budget(()=>browser.newContext({timezoneId:'America/New_York',locale:'en-US'}),true);
  const page=await budget(()=>context.newPage(),true);page.setDefaultTimeout(15000);
  phase('login_navigate');await budget(()=>page.goto(APP,{waitUntil:'domcontentloaded',timeout:remaining()}));
  phase('login_auth_redirect');await budget(()=>page.waitForURL('https://auth.gomotive.com/login/lookup**',{timeout:remaining()}));
  phase('login_lookup_form_ready');
  let form=await budget(()=>reviewedForm(page,'lookup',lookupEmail));
  phase('login_lookup_email');
  await budget(()=>form.input.fill(lookupEmail,{timeout:remaining()}));
  phase('login_lookup_revalidate');form=await budget(()=>reviewedForm(page,'lookup',lookupEmail));
  if(await budget(()=>form.input.inputValue())!==lookupEmail)throw new Error('login_account_mismatch');
  phase('login_lookup_submit');await budget(()=>form.button.click({timeout:remaining()}));
  await budget(()=>page.waitForURL('https://auth.gomotive.com/login/authenticate**',{timeout:remaining()}));
  phase('login_password_form_ready');form=await initialForm(page,'password');
  phase('login_password');
  await budget(()=>form.input.fill(lookupPassword,{timeout:remaining()}));
  phase('login_password_revalidate');form=await budget(()=>reviewedForm(page,'password',lookupEmail));
  if(await budget(()=>form.input.inputValue())!==lookupPassword)throw loginError('login_form_target','credential_value_changed');
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
