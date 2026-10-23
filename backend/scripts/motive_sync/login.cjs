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
 let followed=false;
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
  if(url.pathname==='/login/lookup'&&!followed){
   const link=page.getByRole('link',{name:'Use legacy login',exact:true});
   const count=await link.count();
   if(count>1)throw new Error('login_legacy_link_ambiguous');
   if(count===1){
    const href=await link.getAttribute('href',{timeout:remaining()});
    if(!href)throw new Error('login_legacy_link_invalid');
    let target;try{target=authUrl(new URL(href,url).href);}catch{throw new Error('login_legacy_link_invalid');}
    // The provider's current '#' anchor switches forms through its own handler.
    if(target.pathname!=='/login'&&href!=='#')throw new Error('login_legacy_link_invalid');
    phase('login_legacy_link');followed=true;
    await link.click({timeout:remaining()});
   }
  }
  await page.waitForTimeout(Math.min(50,remaining()));
 }
}
module.exports={prepareLegacyLogin};
