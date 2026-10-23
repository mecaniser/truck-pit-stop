const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const {prepareLegacyLogin}=require('./login.cjs');
const legacy='<input name="user_profile[email]"><input name="user_profile[password]" type="password"><button>Log in</button>';
const lookup='<input name="email"><button>Continue</button>';
async function fixture(body,url='https://auth.gomotive.com/login/lookup?client_id=fixture'){
 const browser=await chromium.launch({headless:true});
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
