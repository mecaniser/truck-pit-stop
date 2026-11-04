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
 const input=stage==='lookup'?lookup:password;
 const inputType=(await input.getAttribute('type')||'text').toLowerCase();
 if(!(stage==='lookup'?['text','email'].includes(inputType):inputType==='password')||await input.getAttribute('form')!==null)throw loginError('login_form_target','input_target');
 const form=page.locator('form').filter({has:input});
 const name=stage==='lookup'?'Continue':'Log in';
 if(await form.count()!==1)throw loginError('login_form_ambiguous','form_count');
 const nativeForm=await form.elementHandle();
 if(!nativeForm)throw loginError('login_form_ambiguous','form_count');
 try{
 if(!await input.evaluate((element,owner)=>element.form===owner,nativeForm))throw loginError('login_form_target','input_target');
 if(stage==='password'){
  const account=form.locator('input[name="user_profile[email]"]');
  if(await account.count()===1&&(await account.getAttribute('form')!==null||!await account.evaluate((element,owner)=>element.form===owner,nativeForm)))throw loginError('login_account_mismatch','account_mismatch');
 }
 const ownership=await form.evaluate((nativeForm,stage)=>{
  const visible=element=>{const rect=element.getBoundingClientRect(),style=getComputedStyle(element);return rect.width>0&&rect.height>0&&style.visibility!=='hidden'&&style.display!=='none';};
  const names=['email','user_profile[password]','user_profile[email]'];
  const associated=Array.from(new Set([...nativeForm.elements,...document.querySelectorAll('input,textarea,select,button,fieldset,object,output')]));
  const credentials=associated.filter(element=>names.includes(element.getAttribute('name')||''));
  const owned=credentials.filter(element=>element.form===nativeForm);
  const counts=names.map(name=>owned.filter(element=>element.name===name).length);
  const expected=stage==='lookup'?[1,0,0]:[0,1,1];
  if(counts.some((count,index)=>count!==expected[index]))return false;
  const outsiders=credentials.filter(element=>element.form!==nativeForm),seen=new Set(),ssoForms=new Set();let auxiliary=0,sso=0;
  const noOverrides=element=>['form','formaction','formmethod','formtarget'].every(attribute=>!element.hasAttribute(attribute));
  for(const email of outsiders){
   if(email.tagName!=='INPUT'||email.name!=='email'||!noOverrides(email)||visible(email))return false;
   const other=email.closest('form');
   if(!other||other===nativeForm||email.form!==other||seen.has(other))return false;
   seen.add(other);
   const controls=Array.from(other.elements);
   const descendants=Array.from(other.querySelectorAll('input,textarea,select,button,fieldset,object,output'));
   if(descendants.some(element=>element.form!==other||!noOverrides(element)))return false;
   if(controls.some(element=>!noOverrides(element))||other.querySelector('iframe,select,[contenteditable]'))return false;
   if(controls.filter(element=>element.tagName==='INPUT'&&element.name==='email').length!==1)return false;
   if(controls.some(element=>element.tagName==='INPUT'&&['user_profile[password]','user_profile[email]'].includes(element.name)))return false;
   if(controls.some(element=>(element.getAttribute('autocomplete')||'').toLowerCase().split(/\s+/).includes('one-time-code')))return false;
   const target=other.getAttribute('target')||'';
   if(!['','_self'].includes(target))return false;
   if(email.getAttribute('type')?.toLowerCase()==='email'){
    if(++auxiliary>2||['action','method','target'].some(attribute=>other.hasAttribute(attribute))||other.method.toLowerCase()!=='get'||other.action!==location.href||controls.length!==7||controls.some(visible)||controls.some(element=>element.hasAttribute('autocomplete')))return false;
    const shape=controls.map(element=>[element.tagName,element.type.toLowerCase(),element.name].join('|')).sort();
    const expectedShape=['INPUT|text|firstName','INPUT|text|lastName','INPUT|email|email','TEXTAREA|textarea|address','TEXTAREA|textarea|comments','BUTTON|submit|','BUTTON|submit|'].sort();
    if(shape.some((signature,index)=>signature!==expectedShape[index]))return false;
   }else if(stage==='password'&&email.getAttribute('type')?.toLowerCase()==='hidden'){
    if(++sso>1||other.method.toLowerCase()!=='post')return false;
    let action;try{action=new URL(other.action);}catch{return false;}
    if(action.origin!=='https://auth.gomotive.com'||action.pathname!=='/login/sso'||action.search||action.hash||action.username||action.password)return false;
    const buttons=controls.filter(element=>element.tagName==='BUTTON');
    if(controls.length!==5||buttons.length!==1)return false;
    ssoForms.add(other);
    const submit=buttons[0],extras=controls.filter(element=>element!==email&&element!==submit);
    const reserved=name=>['email','userprofilepassword','userprofileemail','password','otp','totp','otpcode','totpcode','verificationcode','onetimecode','onetimepassword'].includes(name.toLowerCase().replace(/[_\-\[\]]/g,''));
    if(extras.length!==3||extras.some(element=>element.tagName!=='INPUT'||element.type!=='hidden'||reserved(element.name)))return false;
    if(submit.form!==other||submit.closest('form')!==other||submit.type!=='submit'||!visible(submit)||submit.textContent.trim().replace(/\s+/g,' ')!=='Log in with SSO'||submit.hasAttribute('aria-labelledby')||(submit.hasAttribute('aria-label')&&submit.getAttribute('aria-label')!=='Log in with SSO'))return false;
   }else return false;
  }
  const alternatives=Array.from(document.querySelectorAll('button,[role=button]')).filter(element=>visible(element)&&(element.textContent.trim().replace(/\s+/g,' ')==='Log in with SSO'||element.getAttribute('aria-label')==='Log in with SSO'));
  if(alternatives.length!==ssoForms.size||alternatives.some(element=>element.tagName!=='BUTTON'||!ssoForms.has(element.form)))return false;
  return true;
 },stage);
 if(!ownership)throw loginError('login_form_ambiguous','credential_count');
 if(await page.getByRole('button',{name,exact:true}).count()!==1)throw loginError('login_form_ambiguous','button_count');
 const button=form.getByRole('button',{name,exact:true});
 if(await button.count()!==1)throw loginError('login_form_ambiguous','button_count');
 if(!await button.evaluate((element,owner)=>['BUTTON','INPUT'].includes(element.tagName)&&element.form===owner,nativeForm))throw loginError('login_form_target','form_target');
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
  if(await hidden.count()!==1||await hidden.getAttribute('type')!=='hidden'||await hidden.getAttribute('form')!==null||!await hidden.evaluate((element,owner)=>element.form===owner,nativeForm)||await hidden.inputValue()!==email)throw loginError('login_account_mismatch','account_mismatch');
 }
 return {input,button};
 }finally{await nativeForm.dispose();}
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
    const empty=await budget(()=>completelyEmptyStartup(page));
    if(!empty){waitingForEmpty=false;return budget(()=>reviewedForm(page,stage,lookupEmail));}
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
