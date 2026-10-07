/* Visible Motive UI only. No application internals, cookies or private endpoints. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const {normalize}=require('./timestamp.cjs');
const {coordinates,copyFresh}=require('./copy_coordinates.cjs');
const ORIGIN='https://app.gomotive.com';
const COMPANY='77 CARGO LLC', COMPANY_ID='KT8934277';
const stampPattern=/^(?:[A-Z][a-z]{2} \d{1,2}, \d{4}|\d{1,2}\/\d{1,2}\/\d{4}), \d{1,2}:\d{2}(?::\d{2})? [AP]M$/;
function vinFrom(text){
 const values=Array.from(text.matchAll(/\bVIN\s*[:\t ]*\s*([A-HJ-NPR-Z0-9]{17})\b/g),m=>m[1]);
 const unique=[...new Set(values)];return unique.length===1?unique[0]:null;
}
async function collect(output){
 if(!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw new Error('missing_credentials');
 const browser=await chromium.launch({headless:true});
 const result={company_label:COMPANY,company_id:COMPANY_ID,company_verified_before:false,company_verified_after:false,complete:false,started_at:new Date().toISOString(),vehicles:[]};
 const save=()=>fs.writeFileSync(output,JSON.stringify(result,null,2),{mode:0o600});
 try{
  const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US'});
  await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:ORIGIN});
  const page=await context.newPage();page.setDefaultTimeout(15000);
  await page.goto(ORIGIN,{waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForURL('https://auth.gomotive.com/login**',{timeout:30000});
  if(new URL(page.url()).origin!=='https://auth.gomotive.com')throw new Error('login_origin');
  await page.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);
  await page.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  async function company(){
   await page.goto(ORIGIN+'/en-US/#/admin/company',{waitUntil:'domcontentloaded'});
   await page.getByText(/KT8934277/).waitFor({timeout:30000});
   const text=await page.locator('body').innerText();
   if(!text.includes(COMPANY)||!text.includes(COMPANY_ID))throw new Error('company_mismatch');
  }
  await company();result.company_verified_before=true;
  await page.goto(ORIGIN+'/en-US/#/settings',{waitUntil:'domcontentloaded'});
  await page.getByText(/Eastern Time - New York/).waitFor({timeout:30000});
  result.timezone_evidence=await page.getByText('Time zone',{exact:true}).evaluate(e=>e.parentElement.innerText);
  if(!/Eastern Time - New York/.test(result.timezone_evidence))throw new Error('timezone_unverified');
  await page.goto(ORIGIN+'/en-US/#/admin/vehicles',{waitUntil:'domcontentloaded'});
  await page.getByText(/Showing \d+ of \d+/).waitFor({timeout:30000});
  const directory=await page.locator('body').innerText();
  const total=directory.match(/Showing (\d+) of (\d+)/);
  const links=await page.locator('a[href*="/vehicles/summary/"]').evaluateAll(es=>es.map(e=>({unit:e.innerText.trim(),href:e.getAttribute('href')})));
  const vehicles=[...new Map(links.map(x=>[x.href,x])).values()];
  // Fail closed on pagination/filters rather than silently call one page fleet-wide.
  if(!total||+total[1]!==+total[2]||vehicles.length!==+total[2]||vehicles.length===0||vehicles.length>250)throw new Error('directory_incomplete');
  result.directory_count=vehicles.length;save();
  for(const link of vehicles){
   if(!/^#\/fleetview\/vehicles\/summary\/\d+$/.test(link.href))throw new Error('vehicle_link_invalid');
   const row={provider_vehicle_id:link.href.split('/').pop(),unit:link.unit,status:'unavailable',vin:null};
   try{
    await page.goto(ORIGIN+'/en-US/'+link.href,{waitUntil:'domcontentloaded'});
    await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().waitFor();
    await page.waitForFunction(()=>/\bVIN\s*[:\t ]*\s*[A-HJ-NPR-Z0-9]{17}\b/.test(document.body.innerText),null,{timeout:15000}).catch(()=>{});
    row.vin=vinFrom(await page.locator('body').innerText());
    if(!row.vin)throw new Error('vin_unavailable');
    await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().click();
    await page.getByText(row.vin,{exact:true}).first().waitFor();
    await page.locator('.current-location-status').waitFor();
    const lines=(await page.locator('body').innerText()).split('\n').map(s=>s.trim()).filter(Boolean);
    const driver=lines.indexOf('CURRENT DRIVER');
    if(driver<1)throw new Error('address_unavailable');
    const address=lines[driver-1];
    async function timestamp(){
     await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().hover();
     const prior=page.locator('.phx-tooltip-content:visible').filter({hasText:stampPattern});
     if(await prior.count())await prior.last().waitFor({state:'hidden',timeout:5000});
     // Require the date tooltip to appear only after hovering this status.
     if(await page.locator('.phx-tooltip-content:visible').filter({hasText:stampPattern}).count())throw new Error('unowned_timestamp_tooltip');
     await page.locator('.current-location-status').hover();
     const tip=page.locator('.phx-tooltip-content:visible').filter({hasText:stampPattern}).last();
     await tip.waitFor();return (await tip.innerText()).trim();
    }
    async function point(){
     await page.mouse.move(0,0);
     await page.getByText(address,{exact:true}).click();
     return copyFresh({clear:()=>page.evaluate(()=>navigator.clipboard.writeText('')),click:()=>page.locator('[phxcontent="Copy coordinates"]').click(),read:()=>page.evaluate(()=>navigator.clipboard.readText()),pause:ms=>page.waitForTimeout(ms)});
    }
    const before=await timestamp(),a=await point(),after=await timestamp(),b=await point();
    if(before!==after||JSON.stringify(a)!==JSON.stringify(b))throw new Error('source_changed_during_capture');
    if(vinFrom(await page.locator('body').innerText())!==row.vin)throw new Error('vin_changed');
    const time=normalize(after,true);if(time.reason)throw new Error(time.reason);
    Object.assign(row,{status:'located',lat:a[0],lng:a[1],address,rawTimestamp:after,sourceAge:await page.locator('.current-location-status').innerText(),sourceReadTime:new Date().toISOString(),...time});
   }catch(e){
    if(new URL(page.url()).origin!==ORIGIN)throw new Error('session_lost');
    const safe=['vin_unavailable','address_unavailable','invalid_coordinates','source_changed_during_capture','vin_changed','unowned_timestamp_tooltip'];
    row.reason=safe.includes(e.message)?e.message:'ui_data_unavailable';
   }
   row.sourceReadTime=row.sourceReadTime||new Date().toISOString();
   result.vehicles.push(row);save();
   console.log(JSON.stringify({stage:'progress',attempted:result.vehicles.length,total:vehicles.length,located:result.vehicles.filter(x=>x.status==='located').length}));
  }
  await company();result.company_verified_after=true;result.complete=true;result.finished_at=new Date().toISOString();save();
  return result;
 }finally{await browser.close();}
}
if(require.main===module){
 const output=process.argv[2];
 if(!output){console.error('Output file required');process.exitCode=1;}
 else collect(output).then(r=>console.log(JSON.stringify({stage:'collection_complete',complete:r.complete,count:r.vehicles.length,located:r.vehicles.filter(x=>x.status==='located').length}))).catch(()=>{console.error('Motive collection failed; no import permitted');process.exitCode=1;});
}
module.exports={collect,vinFrom,coordinates};
