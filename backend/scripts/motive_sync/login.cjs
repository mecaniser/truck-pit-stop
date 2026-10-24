/* Public rendered auth UI only; never submit the email lookup/SSO flow. */
const AUTH='https://auth.gomotive.com';
const EMAIL='input[name="user_profile[email]"]:visible';
const PASSWORD='input[name="user_profile[password]"]:visible';
function authUrl(raw){
 let url;try{url=new URL(raw);}catch{throw new Error('login_origin');}
 if(url.origin!==AUTH||url.username||url.password||!['/login','/login/lookup'].includes(url.pathname))throw new Error('login_origin');
 return url;
}
async function prepareLegacyLogin(page,{timeout=15000,phase=()=>{}}={}){
 const deadline=Date.now()+timeout;
 const remaining=()=>{const n=deadline-Date.now();if(n<=0)throw new Error('login_form_timeout');return n;};
 let attempts=0, navigationVersion=0, loadedNavigationVersion=0, attemptedVersion=0;
 const navigated=frame=>{if(frame===page.mainFrame())navigationVersion++;};
 const loaded=()=>{loadedNavigationVersion=navigationVersion;};
 page.on('framenavigated',navigated);page.on('domcontentloaded',loaded);
 try{
 phase('login_form_check');
 while(true){
  remaining();const url=authUrl(page.url());
  const email=page.locator(EMAIL),password=page.locator(PASSWORD);
  const ec=await email.count(),pc=await password.count();
  if(ec>1||pc>1)throw new Error('login_form_ambiguous');
  if(url.pathname==='/login'&&ec===1&&pc===1){
   const submit=page.getByRole('button',{name:'Log in',exact:true});
   if(await submit.count()!==1)throw new Error('login_form_ambiguous');
   remaining();if(authUrl(page.url()).pathname!=='/login')throw new Error('login_origin');return;
  }
  // A second click is permitted only after a NEW document completed the
  // provider redirect back to lookup. A hash change or pending click is not proof.
  const returnedLookup=attempts>0&&loadedNavigationVersion>attemptedVersion;
  if(url.pathname==='/login/lookup'&&returnedLookup&&attempts===2)throw new Error('login_legacy_redirect_loop');
  if(url.pathname==='/login/lookup'&&(attempts===0||returnedLookup)){
   const link=page.getByRole('link',{name:'Use legacy login',exact:true});
   const count=await link.count();
   if(count>1)throw new Error('login_legacy_link_ambiguous');
   if(count===1){
    const href=await link.getAttribute('href',{timeout:remaining()});
    if(!href)throw new Error('login_legacy_link_invalid');
    let target;try{target=authUrl(new URL(href,url).href);}catch{throw new Error('login_legacy_link_invalid');}
    // The provider's current '#' anchor switches forms through its own handler.
    if(target.pathname!=='/login'&&href!=='#')throw new Error('login_legacy_link_invalid');
    phase(attempts===0?'login_legacy_link':'login_legacy_retry');
    attempts++;attemptedVersion=navigationVersion;
    await link.click({timeout:remaining()});
    phase('login_legacy_redirect');
   }
  }
  await page.waitForTimeout(Math.min(50,remaining()));
 }
 }finally{page.off('framenavigated',navigated);page.off('domcontentloaded',loaded);}
}
module.exports={prepareLegacyLogin};
