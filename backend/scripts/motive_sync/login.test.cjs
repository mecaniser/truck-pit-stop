const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const {prepareLegacyLogin}=require('./login.cjs');
const legacy='<input name="user_profile[email]"><input name="user_profile[password]" type="password"><button>Log in</button>';
const lookup='<input name="email"><button>Continue</button>';
async function fixture(body,url='https://auth.gomotive.com/login/lookup?client_id=fixture'){
 const browser=await chromium.launch({headless:true,args:['--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND']});
 const context=await browser.newContext({serviceWorkers:'block'});let requests=0;
 await context.route('**/*',async route=>{requests++;await route.fulfill({contentType:'text/html',body});});
 const page=await context.newPage();await page.goto(url);
 await page.evaluate(()=>{window.fills=0;window.clicks=0;document.addEventListener('input',()=>window.fills++);});
 return {page,browser,requests:()=>requests};
}
async function run(body,expected,url){
 const f=await fixture(body,url);
 try{
  const started=Date.now();
  if(expected)await assert.rejects(prepareLegacyLogin(f.page,{timeout:250}),new RegExp(expected));
  else await prepareLegacyLogin(f.page,{timeout:1000});
  assert.equal(await f.page.evaluate(()=>window.fills),0,'preflight must never fill credentials');
  assert.ok(Date.now()-started<2000,'bounded failure');
  return await f.page.evaluate(()=>({clicks:window.clicks,path:location.pathname}));
 }finally{await f.browser.close();}
}
test('direct legacy remains unchanged',async()=>{
 const r=await run(legacy,null,'https://auth.gomotive.com/login?client_id=fixture');assert.equal(r.path,'/login');assert.equal(r.clicks,0);
});
test('lookup follows provider fragment handler exactly once and preserves query',async()=>{
 const body=lookup+`<a href="#" onclick='event.preventDefault();window.clicks++;history.pushState({},"","/login"+location.search);document.body.insertAdjacentHTML("beforeend",${JSON.stringify(legacy)})'>Use legacy login</a>`;
 const r=await run(body);assert.equal(r.path,'/login');assert.equal(r.clicks,1);
});
test('trusted link may navigate to legacy document',async()=>{
 const f=await fixture(lookup+'<a href="/login?client_id=fixture">Use legacy login</a>');
 try{
  await f.page.route('https://auth.gomotive.com/login?client_id=fixture',r=>r.fulfill({contentType:'text/html',body:legacy}));
  await prepareLegacyLogin(f.page,{timeout:1000});assert.equal(new URL(f.page.url()).pathname,'/login');
 }finally{await f.browser.close();}
});
for(const [name,body,error,url] of [
 ['missing link',lookup,'login_form_timeout'],
 ['duplicate link',lookup+'<a href="#">Use legacy login</a><a href="#">Use legacy login</a>','login_legacy_link_ambiguous'],
 ['evil origin',lookup+'<a href="https://evil.invalid/login">Use legacy login</a>','login_legacy_link_invalid'],
 ['http origin',lookup+'<a href="http://auth.gomotive.com/login">Use legacy login</a>','login_legacy_link_invalid'],
 ['unexpected path',lookup+'<a href="/login/authenticate">Use legacy login</a>','login_legacy_link_invalid'],
 ['data URL',lookup+'<a href="data:text/html,hello">Use legacy login</a>','login_legacy_link_invalid'],
 ['javascript URL',lookup+'<a href="javascript:void(0)">Use legacy login</a>','login_legacy_link_invalid'],
 ['no href',lookup+'<a role="link">Use legacy login</a>','login_legacy_link_invalid'],
 ['unresponsive link',lookup+'<a href="#" onclick="window.clicks++;event.preventDefault()">Use legacy login</a>','login_form_timeout'],
 ['wrong initial origin',legacy,'login_origin','https://evil.invalid/login'],
 ['wrong initial path',legacy,'login_origin','https://auth.gomotive.com/other'],
 ['partial legacy', '<input name="user_profile[email]">','login_form_timeout','https://auth.gomotive.com/login'],
 ['duplicate legacy',legacy+'<input name="user_profile[email]">','login_form_ambiguous','https://auth.gomotive.com/login'],
 ['legacy fields on lookup',legacy,'login_form_timeout'],
 ['handler unexpected path',lookup+'<a href="#" onclick="event.preventDefault();history.pushState({},\'\',\'/other\')">Use legacy login</a>','login_origin'],
])test(name,async()=>{const r=await run(body,error,url);if(name==='unresponsive link')assert.equal(r.clicks,1);});

test('post-click external redirect fails before any credential fill',async()=>{
 const f=await fixture(lookup+'<a href="/login">Use legacy login</a>');
 try{
  await f.page.route('https://auth.gomotive.com/login',r=>r.fulfill({status:302,headers:{location:'https://evil.invalid/login'}}));
  await assert.rejects(prepareLegacyLogin(f.page,{timeout:1000}),/login_origin/);
  assert.equal(await f.page.locator('input').evaluateAll(es=>es.some(e=>e.value)),false);
 }finally{await f.browser.close();}
});
test('caller fills dummy credentials only after verified legacy form',async()=>{
 const f=await fixture(lookup+`<a href="#" onclick='event.preventDefault();history.pushState({},"","/login");document.body.innerHTML=${JSON.stringify(legacy)}'>Use legacy login</a>`);
 try{
  await prepareLegacyLogin(f.page,{timeout:1000});
  assert.equal(new URL(f.page.url()).pathname,'/login');
  await f.page.locator('input[name="user_profile[email]"]').fill('fixture@example.invalid');
  await f.page.locator('input[name="user_profile[password]"]').fill('synthetic-only');
  assert.equal(await f.page.evaluate(()=>window.fills),2);
 }finally{await f.browser.close();}
});

async function redirectChain({persistent=false,delay=0,secondLink='#',foreign=false}={}){
 // Playwright route interception does not cover every HTTP redirect hop. Use a
 // real local TLS server with fail-closed DNS mapping for the entire chain.
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),https=require('node:https');
 const {execFileSync}=require('node:child_process');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'motive-auth-fixture-'));
 execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',path.join(dir,'key.pem'),'-out',path.join(dir,'cert.pem'),'-subj','/CN=fixture.invalid','-days','1'],{stdio:'ignore'});
 let clicks=0;const requests=[];
 const server=https.createServer({key:fs.readFileSync(path.join(dir,'key.pem')),cert:fs.readFileSync(path.join(dir,'cert.pem'))},async(req,res)=>{
  const u=new URL(req.url,'https://'+req.headers.host);requests.push(u.origin+u.pathname);
  const redirect=(status,location)=>{res.writeHead(status,{location});res.end();};
  const html=body=>{res.writeHead(200,{'content-type':'text/html'});res.end(body);};
  if(u.pathname==='/login/legacy_fallback'){
   clicks++;if(delay)await new Promise(resolve=>setTimeout(resolve,delay));
   return redirect(302,'https://account.gomotive.com/log-in');
  }
  if(u.origin==='https://account.gomotive.com')return redirect(303,foreign?'https://evil.invalid/login':'https://auth.gomotive.com/login');
  if(u.origin==='https://evil.invalid')return html(legacy);
  if(u.pathname==='/login'){
   if(persistent||clicks===1)return redirect(303,'https://auth.gomotive.com/login/lookup');
   return html(legacy);
  }
  if(u.pathname!=='/login/lookup'){res.writeHead(404);return res.end();}
  const href=clicks?secondLink:'#';
  return html(lookup+`<a href="${href}" onclick="event.preventDefault();location.assign('/login/legacy_fallback')">Use legacy login</a>`);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const port=server.address().port;
 const rules=['auth.gomotive.com','account.gomotive.com','evil.invalid'].map(host=>`MAP ${host} 127.0.0.1:${port}`).join(',')+',MAP * ~NOTFOUND';
 const browser=await chromium.launch({headless:true,args:['--no-proxy-server','--host-resolver-rules='+rules]});
 const context=await browser.newContext({serviceWorkers:'block',ignoreHTTPSErrors:true}),page=await context.newPage();
 await page.goto('https://auth.gomotive.com/login/lookup');
 const close=async()=>{await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));fs.rmSync(dir,{recursive:true,force:true});};
 return {browser:{close},page,clicks:()=>clicks,requests};
}
test('actual provider redirect chain retries once after new lookup document',async()=>{
 const f=await redirectChain();const phases=[];
 try{await prepareLegacyLogin(f.page,{timeout:2000,phase:x=>phases.push(x)});
  assert.equal(f.clicks(),2);assert.equal(new URL(f.page.url()).pathname,'/login');
  assert.equal(phases.filter(x=>x==='login_legacy_retry').length,1);
  assert.ok(f.requests.includes('https://account.gomotive.com/log-in'));
  assert.equal(await f.page.locator('input').evaluateAll(es=>es.some(e=>e.value)),false);
  assert.equal(f.page.listenerCount('domcontentloaded'),0);
 }finally{await f.browser.close();}
});
test('persistent provider loop stops at two clicks with precise classification',async()=>{
 const f=await redirectChain({persistent:true});try{
  await assert.rejects(prepareLegacyLogin(f.page,{timeout:2000}),/login_legacy_redirect_loop/);assert.equal(f.clicks(),2);
  assert.equal(await f.page.locator('input').evaluateAll(es=>es.some(e=>e.value)),false);
  assert.equal(f.page.listenerCount('domcontentloaded'),0);
 }finally{await f.browser.close();}
});
test('pending slow provider navigation receives no second click',async()=>{
 const f=await redirectChain({delay:500});try{
  await assert.rejects(prepareLegacyLogin(f.page,{timeout:200}));assert.equal(f.clicks(),1);
 }finally{await f.browser.close();}
});
test('returned lookup link is revalidated before retry',async()=>{
 const f=await redirectChain({secondLink:'https://evil.invalid/login'});try{
  await assert.rejects(prepareLegacyLogin(f.page,{timeout:2000}),/login_legacy_link_invalid/);assert.equal(f.clicks(),1);
 }finally{await f.browser.close();}
});
test('foreign provider final document never gets credentials or retry',async()=>{
 const f=await redirectChain({foreign:true});try{
  await assert.rejects(prepareLegacyLogin(f.page,{timeout:2000}),/login_origin/);assert.equal(f.clicks(),1);
  assert.equal(await f.page.locator('input').evaluateAll(es=>es.some(e=>e.value)),false);
 }finally{await f.browser.close();}
});
test('same-document hash navigation is not a completed return to lookup',async()=>{
 const f=await fixture(lookup+'<a href="#" onclick="window.clicks++">Use legacy login</a>');try{
  await assert.rejects(prepareLegacyLogin(f.page,{timeout:250}),/login_form_timeout/);
  assert.equal(await f.page.evaluate(()=>window.clicks),1);
 }finally{await f.browser.close();}
});
