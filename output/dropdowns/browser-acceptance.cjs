const { chromium, expect } = require('../../e2e/node_modules/@playwright/test');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=__dirname;
const fixture=JSON.parse(fs.readFileSync(path.join(out,'../equipment/browser_fixture.json')));
async function menuFits(page){
 const list=page.getByRole('listbox'); await expect(list).toBeVisible();
 const bounds=await list.evaluate(el=>{const r=el.getBoundingClientRect();const hit=document.elementFromPoint(r.left+r.width/2,r.top+Math.min(r.height/2,30));return{left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:innerWidth,height:innerHeight,scroll:el.scrollWidth,client:el.clientWidth,onTop:el.contains(hit)}});
 assert.ok(bounds.left>=0&&bounds.right<=bounds.width+1&&bounds.top>=0&&bounds.bottom<=bounds.height+1,JSON.stringify(bounds));
 assert.ok(bounds.scroll<=bounds.client+1,JSON.stringify(bounds));assert.ok(bounds.onTop,JSON.stringify(bounds));return bounds;
}
(async()=>{
 const browser=await chromium.launch({headless:true}); const results=[];
 try {
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}])for(const mode of ['light','dark','high_contrast']){
  const context=await browser.newContext({viewport}); const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  if(mode==='high_contrast')await page.emulateMedia({forcedColors:'active'});
  const prefs={accent:'cyan',font_family:'inter',font_size:'default',density:'default',notification_position:'top_center',mode};
  const presentation={schema_version:1,resolved_variant:'new',source:'user_override',appearance:prefs,defaults:prefs,revision:4,legacy_migration_status:'complete',updated_at:'2026-10-30T12:00:00Z'};
  await page.route('**/api/v1/auth/me/appearance',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(presentation)}));
  await page.addInitScript(({user,token,presentation})=>localStorage.setItem('auth-storage',JSON.stringify({state:{user:{...user,presentation},token,refreshToken:null,isAuthenticated:true,authProvider:'legacy'},version:0})),{...fixture,presentation});
  await page.goto('http://127.0.0.1:5187/dashboard/customers');await page.getByText('Ellis Logistics Test',{exact:true}).click();
  await page.getByText('T1003130',{exact:true}).click();await page.getByRole('button',{name:/^Edit vehicle$/i}).click();
  await expect(page.getByLabel('Equipment type')).toHaveText('Trailer');await page.getByLabel('Equipment type').click();
  await expect(page.getByRole('option')).toHaveCount(4);const equipment=await menuFits(page);
  await page.screenshot({path:path.join(out,`${mode}-${viewport.width}-equipment-menu.png`),fullPage:true});
  await page.keyboard.press('Escape');await expect(page.getByRole('listbox')).toHaveCount(0);await expect(page.getByLabel('Equipment type')).toBeFocused();
  await expect(page.getByRole('heading',{name:'Edit Equipment',exact:true})).toBeVisible();
  await page.getByLabel('Equipment type').click();await page.getByRole('option',{name:'Other equipment',exact:true}).click();await expect(page.getByLabel('Equipment type')).toHaveText('Other equipment');
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  const asset=fixture.assets.find(item=>item.unit==='T1003130');const response=await page.request.get(`http://127.0.0.1:5187/api/v1/customers/${fixture.company_id}/vehicles/${asset.id}`,{headers:{Authorization:`Bearer ${fixture.token}`}});assert.equal(response.status(),200);assert.equal((await response.json()).equipment_type,'trailer');
  await page.goto(`http://127.0.0.1:5187/dropdown-qa.html?mode=${mode==='light'?'light':'dark'}`);
  await page.getByRole('combobox',{name:'Equipment type',exact:true}).click();const gallery=await menuFits(page);await page.keyboard.press('End');await page.keyboard.press('Enter');await expect(page.getByRole('combobox',{name:'Equipment type',exact:true})).toHaveText('Unclassified');
  await page.getByRole('combobox',{name:'Supplier',exact:true}).click();const long=await menuFits(page);await page.getByRole('option',{name:/AReallyLong/}).click();await expect(page.getByRole('combobox',{name:'Supplier',exact:true})).toContainText('AReallyLong');
  await page.getByRole('combobox',{name:'Payment consent',exact:true}).click();await expect(page.getByRole('option',{name:'Previous authorization unavailable'})).toBeDisabled();await page.getByRole('button',{name:'Toggle fieldset disabled'}).evaluate(button=>button.click());await expect(page.getByRole('listbox')).toHaveCount(0);await expect(page.getByRole('combobox',{name:'Payment consent',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Validate required field'}).click();await expect(page.getByRole('alert')).toBeVisible();await expect(page.getByRole('combobox',{name:'Repeated time occurrence'})).toBeFocused();
  await page.keyboard.press('ArrowDown');await page.keyboard.press('End');await page.keyboard.press('Enter');await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByRole('button',{name:'Open high-layer modal'}).click();await page.getByRole('combobox',{name:'Modal asset'}).click();const modal=await menuFits(page);
  await page.screenshot({path:path.join(out,`${mode}-${viewport.width}-modal-menu.png`),fullPage:true});
  await page.keyboard.press('Escape');await page.getByRole('button',{name:'Close modal'}).click();
  assert.deepEqual(errors,[]);const width=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));assert.ok(width.scroll<=width.width+1,JSON.stringify(width));
  results.push({viewport,mode,equipment,gallery,long,modal,keyboard:true,cancelPreservesStoredValue:true,requiredValidation:true,inheritedDisabled:true,pageErrors:errors});await context.close();
 }
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(results,null,2));console.log(`PASS ${results.length} desktop/mobile theme cases`);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
