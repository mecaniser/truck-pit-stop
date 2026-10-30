/* Bounded anonymous form recovery. Credentials remain in each collector. */
const {performance}=require('node:perf_hooks');
const {prepareLegacyLogin}=require('./login.cjs');
const APP='https://app.gomotive.com',AUTH='https://auth.gomotive.com';
const OPTIONS=Object.freeze({timezoneId:'America/New_York',locale:'en-US'});
function origin(page){
 let url;try{url=new URL(page.url());}catch{throw new Error('login_origin');}
 if(url.origin!==AUTH||url.username||url.password||!['/login','/login/lookup'].includes(url.pathname))throw new Error('login_origin');
 return url;
}
function close(resource){try{Promise.resolve(resource.close()).catch(()=>{});}catch{}}
async function prepareLoginContext(browser,{phase=()=>{},diagnostic=stage=>console.log(JSON.stringify({stage})),timeout=15000,now=()=>performance.now(),recoveryStage='login_context_recovery',recoveredStage='login_context_recovered'}={}){
 if(!Number.isFinite(timeout)||timeout<=0||timeout>15000)throw new Error('login_form_timeout');
 let context,page,deadline;
 const remaining=()=>{const value=deadline-now();if(value<=0)throw new Error('login_form_timeout');return value;};
 // Context/page creation and disposal have no native Playwright timeout. Race
 // them against the same deadline, disposing any resource returned too late.
 async function budget(operation,dispose=false){
  const milliseconds=remaining();let timer,expired=false;
  const pending=Promise.resolve().then(operation);
  pending.then(value=>{if(expired&&dispose)close(value);},()=>{});
  try{
   const value=await Promise.race([pending,new Promise((_,reject)=>{timer=setTimeout(()=>{expired=true;reject(new Error('login_form_timeout'));},milliseconds);})]);
   try{remaining();}catch(error){if(dispose)close(value);throw error;}
   return value;
  }finally{clearTimeout(timer);}
 }
 async function bootstrap(recovery){
  context=recovery?await budget(()=>browser.newContext({...OPTIONS}),true):await browser.newContext({...OPTIONS});
  page=recovery?await budget(()=>context.newPage(),true):await context.newPage();
  page.setDefaultTimeout(15000);
  phase('login_navigate');
  await page.goto(APP,{waitUntil:'domcontentloaded',timeout:recovery?remaining():45000});
  if(recovery)remaining();
  phase('login_auth_redirect');
  await page.waitForURL('https://auth.gomotive.com/login**',{timeout:recovery?remaining():30000});
  if(recovery)remaining();
  phase('login_origin_check');origin(page);
 }
 try{
  await bootstrap(false);
  deadline=now()+timeout;
  try{await budget(()=>prepareLegacyLogin(page,{phase,timeout:remaining()}));}
  catch(error){
   // This catch surrounds only the reviewed helper, before any credentials.
   if(error?.message!=='login_legacy_redirect_loop')throw error;
   if(origin(page).pathname!=='/login/lookup')throw new Error('login_origin');
   const email=await budget(()=>page.locator('input[name="user_profile[email]"]:visible').count());
   const password=await budget(()=>page.locator('input[name="user_profile[password]"]:visible').count());
   if(email||password)throw new Error('login_form_ambiguous');
   remaining();diagnostic(recoveryStage);
   await budget(()=>context.close());context=null;page=null;
   await bootstrap(true);
   await budget(()=>prepareLegacyLogin(page,{phase,timeout:remaining()}));
   remaining();diagnostic(recoveredStage);
  }
  remaining();return {context,page};
 }catch(error){if(context)close(context);throw error;}
}
module.exports={prepareLoginContext};
