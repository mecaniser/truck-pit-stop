/* Visible Motive UI only. No application internals, cookies or private endpoints. */
const fs=require('node:fs');
const {normalize}=require('./timestamp.cjs');
const {coordinates,copyFresh}=require('./copy_coordinates.cjs');
const ORIGIN='https://app.gomotive.com';
const COMPANY='77 CARGO LLC', COMPANY_ID='KT8934277';
function vinFrom(text){
 const values=Array.from(text.matchAll(/\bVIN\s*[:\t ]*\s*([A-HJ-NPR-Z0-9]{17})\b/g),m=>m[1]);
 const unique=[...new Set(values)];return unique.length===1?unique[0]:null;
}
function addressFrom(text){
 const lines=text.split('\n').map(s=>s.trim()).filter(Boolean);
 const boundary=lines.includes('CURRENT DRIVER')?lines.indexOf('CURRENT DRIVER'):lines.indexOf('Telematics');
 const candidate=boundary>0?lines[boundary-1]:'';
 return /,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?$/.test(candidate)?candidate:null;
}
function bindVin(expected,text){
 const values=[...new Set(Array.from(text.matchAll(/\bVIN\s*[:\t ]*\s*([A-HJ-NPR-Z0-9]{17})\b/g),m=>m[1]))];
 if(values.length>1)throw new Error('ambiguous_vin');
 if(!values.length)throw new Error('vin_unavailable');
 if(expected&&expected!==values[0])throw new Error('vin_changed');return values[0];
}
function observationTime(raw){
 if(raw){const parsed=normalize(raw,true);if(!parsed.reason)return {...parsed,timestampReason:null};}
 return {observed_at:null,observed_minute_start:null,observed_minute_end:null,precision:'unknown',timezone:null,timestampReason:raw?normalize(raw,true).reason:'timestamp_unavailable'};
}
async function stableObservation({timestamp,point,verifyVin,address}){
 const before=await timestamp(),a=await point(),after=await timestamp(),b=await point();
 if(before.rawTimestamp!==after.rawTimestamp||before.timestampReason!==after.timestampReason||(!before.rawTimestamp&&before.sourceAge!==after.sourceAge)||JSON.stringify(a)!==JSON.stringify(b))throw new Error('source_changed_during_capture');
 await verifyVin();
 return {status:'located',lat:a[0],lng:a[1],address:address||null,rawTimestamp:after.rawTimestamp,sourceAge:after.sourceAge,sourceReadTime:new Date().toISOString(),...observationTime(after.rawTimestamp),timestampReason:after.timestampReason||observationTime(after.rawTimestamp).timestampReason};
}
async function collectWithRetries(context,link,readPage=readVehiclePage){
 let expected=null,reason='ui_data_unavailable',fallback=null;
 const row={provider_vehicle_id:link.href.split('/').pop(),unit:link.unit,status:'unavailable',vin:null};
 for(let attempt=0;attempt<2;attempt++){
  const page=await context.newPage();page.setDefaultTimeout(15000);
  try{
   const bind=text=>{expected=bindVin(expected,text);row.vin=expected;return expected;};
   const captured={...row,...await readPage(page,link,bind),vin:expected};
   if(captured.status==='located'&&captured.precision==='unknown'&&attempt===0){fallback=captured;continue;}
   return captured;
  }catch(error){
   if(!['about:blank',ORIGIN].includes(page.url()==='about:blank'?'about:blank':new URL(page.url()).origin))throw new Error('session_lost');
   const fatal=['vin_changed','ambiguous_vin','session_lost','vehicle_source_changed'];
   if(fatal.includes(error.message))throw error;
   const safe=['provider_location_unavailable','vin_unavailable','invalid_coordinates','source_changed_during_capture','unowned_timestamp_tooltip','location_control_unavailable','clipboard_clear_failed','clipboard_write_timeout','vehicle_summary_unavailable','live_vin_unavailable','copy_control_unavailable'];
   reason=safe.includes(error.message)?error.message:'ui_data_unavailable';
  }finally{await page.close();}
 }
 return fallback?{...fallback,retryReason:reason}:{...row,reason,sourceReadTime:new Date().toISOString()};
}
function assertLiveProvider(url,providerId){
 const source=new URL(url),match=source.hash.match(/^#\/fleetview\/map\/vehicle\/([^/]+)\/(\d+)\/live$/);
 if(source.origin!==ORIGIN||!match||match[2]!==providerId||!match[1].startsWith(providerId+'-'))throw new Error('vehicle_source_changed');
}
async function locationControl(page){
 // Grounded 531/6/609/77 UI probes: this unique container opens Copy coordinates,
 // including state-only labels and absent status timestamps. Label parsing is optional.
 const control=page.locator('.container.mt-4.pos-relative').filter({visible:true});
 await control.first().waitFor().catch(()=>{throw new Error('location_control_unavailable');});
 if(await control.count()!==1)throw new Error('location_control_unavailable');
 const label=control.locator(':scope > span.grey-70.regular-14');
 const count=await label.count();
 return {control,address:count===1?(await label.innerText()).trim()||null:null};
}
async function readVehiclePage(page,link,bind){
 await page.goto(ORIGIN+'/en-US/'+link.href,{waitUntil:'domcontentloaded',timeout:45000});
 await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().waitFor().catch(()=>{throw new Error('vehicle_summary_unavailable');});
 await page.waitForFunction(()=>/\bVIN\s*[:\t ]*\s*[A-HJ-NPR-Z0-9]{17}\b/.test(document.body.innerText),null,{timeout:15000}).catch(()=>{});
 if(!page.url().endsWith(link.href))throw new Error('vin_changed');
 const vin=bind(await page.locator('body').innerText());
 await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().click();
 await page.getByText(vin,{exact:true}).first().waitFor().catch(()=>{throw new Error('live_vin_unavailable');});
 const liveText=await page.locator('body').innerText();bind(liveText);
 assertLiveProvider(page.url(),link.href.split('/').pop());
 if(liveText.includes('Add Vehicle Gateway to see location data'))throw new Error('provider_location_unavailable');
 const {control,address}=await locationControl(page);
 async function timestamp(){
  const status=page.locator('.current-location-status').filter({visible:true});
  if(await status.count()===0)return {rawTimestamp:null,sourceAge:null,timestampReason:'status_unavailable'};
  if(await status.count()!==1)throw new Error('unowned_timestamp_tooltip');
  const sourceAge=(await status.innerText()).trim()||null;
  await page.mouse.move(0,0);
  const prior=page.locator('.phx-tooltip-content:visible');
  if(await prior.count())await prior.last().waitFor({state:'hidden',timeout:5000});
  if(await prior.count())throw new Error('unowned_timestamp_tooltip');
  await status.hover();
  const tip=page.locator('.phx-tooltip-content:visible');
  try{await tip.first().waitFor({timeout:5000});}catch(error){if(error.name!=='TimeoutError')throw error;return {rawTimestamp:null,sourceAge,timestampReason:'timestamp_tooltip_unavailable'};}
  if(await tip.count()!==1)throw new Error('unowned_timestamp_tooltip');
  return {rawTimestamp:(await tip.innerText()).trim(),sourceAge,timestampReason:null};
 }
 async function point(){
  assertLiveProvider(page.url(),link.href.split('/').pop());bind(await page.locator('body').innerText());
  await page.mouse.move(0,0);await control.click();
  return copyFresh({clear:()=>page.evaluate(()=>navigator.clipboard.writeText('')),click:async()=>{const copy=page.locator('[phxcontent="Copy coordinates"]').filter({visible:true});await copy.first().waitFor().catch(()=>{throw new Error('copy_control_unavailable');});if(await copy.count()!==1)throw new Error('copy_control_unavailable');await copy.click();},read:()=>page.evaluate(()=>navigator.clipboard.readText()),pause:ms=>page.waitForTimeout(ms)});
 }
 return stableObservation({timestamp,point,verifyVin:async()=>{assertLiveProvider(page.url(),link.href.split('/').pop());bind(await page.locator('body').innerText());},address});
}
async function collect(output){
 if(!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw new Error('missing_credentials');
 const {chromium}=require('playwright');
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
   const row=await collectWithRetries(context,link);
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
module.exports={collect,vinFrom,coordinates,addressFrom,bindVin,observationTime,stableObservation,collectWithRetries,assertLiveProvider,locationControl};
