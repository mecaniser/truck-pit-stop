const { chromium, expect } = require('../../e2e/node_modules/@playwright/test');
const fs=require('fs'), path=require('path'), assert=require('assert/strict');
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'browser_fixture.json')));
 const browser=await chromium.launch({headless:true});
 const results=[];
 try {
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
  const tag=viewport.width===1440?'desktop':'mobile';
  const run=Date.now();
  const context=await browser.newContext({viewport});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400 && r.url().includes('/api/') && !(r.status()===409 && r.url().endsWith('/settlement'))) errors.push(`${r.status()} ${new URL(r.url()).pathname}`)});
  await page.addInitScript(({user,token})=>{
   localStorage.clear();sessionStorage.clear();
   localStorage.setItem('auth-storage',JSON.stringify({state:{user,token,refreshToken:null,isAuthenticated:true,authProvider:'legacy'},version:0}));
  },fixture);
  await page.goto('http://127.0.0.1:5187/dashboard/customers');
  await page.getByText('Ellis Logistics Test',{exact:true}).click();
  await expect(page.getByText('Equipment relationships',{exact:true})).toBeVisible();
  await page.getByText('T1003130',{exact:true}).click();
  await expect(page.getByText('#TEST-T1003130',{exact:true})).toBeVisible();
  await expect(page.getByText('#TEST-603',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Edit Vehicle',exact:true}).click();
  const type=page.getByLabel('Equipment type',{exact:true});
  await expect(type).toHaveValue('trailer');
  await page.locator('textarea[name="notes"]').fill(`DB097 ${tag} isolated edit`);
  await page.screenshot({path:path.join(__dirname,`${tag}-edit-trailer.png`),fullPage:true});
  const updated=page.waitForResponse(r=>r.request().method()==='PUT' && r.url().includes('/vehicles/'));
  await page.getByRole('button',{name:'Save Changes',exact:true}).click();
  const saved=await (await updated).json();assert.equal(saved.equipment_type,'trailer');assert.equal(saved.unit_number,'T1003130');
  await page.getByText('#TEST-T1003130',{exact:true}).click();
  await expect(page.getByText('Invoice TEST-INV-T1003130',{exact:true})).toBeVisible();
  await page.waitForTimeout(300);
  fs.writeFileSync(path.join(__dirname,`${tag}-repair-workspace.txt`),await page.locator('body').innerText());
  await page.screenshot({path:path.join(__dirname,`${tag}-repair-workspace.png`),fullPage:true});
  await page.goto('http://127.0.0.1:5187/dashboard/customers');
  await page.getByText('Ellis Logistics Test',{exact:true}).click();
  await page.getByRole('button',{name:'Add / Link',exact:true}).click();
  await expect(type).toHaveValue('tractor');
  await type.selectOption(tag==='desktop'?'trailer':'other');
  await page.locator('input[name="make"]').fill('DB097');
  await page.locator('input[name="model"]').fill(tag==='desktop'?'Test Trailer':'Test Generator');
  await page.locator('input[name="unit_number"]').fill(`DB097-${tag}-${run}`);
  const vinBounds=await page.locator('input[name="vin"]').evaluate(el=>{const row=el.parentElement;return {scroll:row.scrollWidth,width:row.clientWidth}});assert.ok(vinBounds.scroll<=vinBounds.width,JSON.stringify(vinBounds));
  await page.screenshot({path:path.join(__dirname,`${tag}-create-equipment.png`),fullPage:true});
  const created=page.waitForResponse(r=>r.request().method()==='POST' && r.url().endsWith(`/customers/${fixture.company_id}/vehicles`));
  await page.getByRole('button',{name:'Add Equipment',exact:true}).click();
  const response=await created;assert.equal(response.status(),201);
  const asset=await response.json();assert.equal(asset.equipment_type,tag==='desktop'?'trailer':'other');assert.equal(asset.customer_id,fixture.company_id);
  await expect(page.getByText(`DB097-${tag}-${run}`,{exact:true})).toBeVisible();
  const width=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));assert.ok(width.scroll<=width.viewport,JSON.stringify(width));
  await page.screenshot({path:path.join(__dirname,`${tag}-company-equipment.png`),fullPage:true});
  // Real authenticated invoice/RO APIs establish billing and asset identity.
  for(const asset of fixture.assets) {
   const opts={headers:{Authorization:`Bearer ${fixture.token}`}};
   const ro=await page.request.get(`http://127.0.0.1:5187/api/v1/repair-orders/${asset.order_id}`,opts);
   assert.equal(ro.status(),200);assert.equal((await ro.json()).vehicle_id,asset.id);
   const invoice=await page.request.get(`http://127.0.0.1:5187/api/v1/invoices/${asset.invoice_id}`,opts);
   assert.equal(invoice.status(),200);assert.equal((await invoice.json()).repair_order_id,asset.order_id);
  }
  assert.deepEqual(errors,[]);
  results.push({viewport,tag,pass:true,realJwtAuth:true,create:asset.equipment_type,editTrailerPreserved:true,isolatedTrailerHistory:true,repairWorkspaceInvoiceVisible:true,invoiceLinksVerified:fixture.assets.length,horizontalOverflow:false,runtimeErrors:errors});
  await context.close();
 }
 fs.writeFileSync(path.join(__dirname,'browser-results.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify(results));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
