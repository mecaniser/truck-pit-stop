const {prepareSyncLogin}=require('./sync_login.cjs');
const {readVehicleVin}=require('./collect_trips.cjs');
const {closeBrowser,phase,openTasks,failed,atomic}=require('./tasks.cjs');
/* Visible Motive UI only. No application internals, cookies or private endpoints. */
const fs=require('node:fs');
const {allowlist,isReviewed,readReviewedPageIdentity,readReviewedIdentity,sameIdentity,assertNoLiveVin}=require('./vehicle_identity.cjs');
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
function speedFromParts(value,unit){
 const speedText=[value,unit].filter(x=>typeof x==='string'&&x.trim()).map(x=>x.trim()).join(' ').slice(0,120)||null;
 const unavailable=reason=>({speed_mph:null,speedText,speedReason:reason});
 if(!speedText)return unavailable('speed_unavailable');
 if(typeof unit!=='string'||unit.trim().toUpperCase()!=='MPH')return unavailable('speed_unit_unsupported');
 if(typeof value!=='string'||!/^\d+(?:\.\d+)?$/.test(value.trim()))return unavailable('speed_invalid');
 const speed=Number(value.trim());
 return Number.isFinite(speed)&&speed>=0&&speed<=250?{speed_mph:speed,speedText,speedReason:null}:unavailable('speed_invalid');
}
async function readSpeed(page){
 // Live 02 DOM, Oct 15: the vehicle's status panel owns this speed value/unit.
 // Road speed limits and trip averages elsewhere on the page are never candidates.
 const section=page.locator('section.driver-location-info').filter({visible:true});
 const sections=await section.count();
 if(sections!==1)return {speed_mph:null,speedText:null,speedReason:sections?'speed_ambiguous':'speed_unavailable'};
 const speed=section.locator('.current-location [data-e2e="speed-info"]').filter({visible:true});
 const count=await speed.count();
 if(count!==1)return {speed_mph:null,speedText:null,speedReason:count?'speed_ambiguous':'speed_unavailable'};
 const value=speed.locator('.value'),unit=speed.locator('.symbol');
 if(await value.count()!==1||await unit.count()!==1)return {speed_mph:null,speedText:null,speedReason:'speed_ambiguous'};
 return speedFromParts(await value.innerText(),await unit.innerText());
}
async function stableObservation({timestamp,point,verifyVin,address,allowUnstableSpeed=false,speed=async()=>({speed_mph:null,speedText:null,speedReason:'speed_unavailable'})}){
 const firstSpeed=await speed(),before=await timestamp(),a=await point(),after=await timestamp(),b=await point(),lastSpeed=await speed();
 if(before.rawTimestamp!==after.rawTimestamp||before.timestampReason!==after.timestampReason||(!before.rawTimestamp&&before.sourceAge!==after.sourceAge)||JSON.stringify(a)!==JSON.stringify(b))throw new Error('source_changed_during_capture');
 const speedChanged=JSON.stringify(firstSpeed)!==JSON.stringify(lastSpeed);
 if(speedChanged&&!allowUnstableSpeed)throw new Error('source_changed_during_capture');
 await verifyVin();
 const observed=observationTime(after.rawTimestamp);
 const retainedSpeed=speedChanged?{speed_mph:null,speedText:null,speedReason:'speed_ambiguous'}:observed.precision==='unknown'&&lastSpeed.speed_mph!==null?{...lastSpeed,speed_mph:null,speedReason:'speed_timestamp_unavailable'}:lastSpeed;
 return {status:'located',lat:a[0],lng:a[1],address:address||null,rawTimestamp:after.rawTimestamp,sourceAge:after.sourceAge,sourceReadTime:new Date().toISOString(),...observed,...retainedSpeed,timestampReason:after.timestampReason||observed.timestampReason};
}
async function collectWithRetries(context,link,readPage=readVehiclePage,{reviewed=false}={}){
 let expected,reason='ui_data_unavailable',fallback=null;
 const row={provider_vehicle_id:link.href.split('/').pop(),unit:link.unit,status:'unavailable',vin:null};
 for(let attempt=0;attempt<2;attempt++){
  const page=await context.newPage();page.setDefaultTimeout(15000);
  try{
   const bind=value=>{const vin=reviewed?value:bindVin(expected,value);if(expected!==undefined&&vin!==expected)throw new Error('vin_changed');expected=vin;row.vin=expected;return expected;};
   const captured={...row,...await readPage(page,link,bind,attempt,{reviewed,context}),vin:expected};
   if(captured.status==='located'&&captured.precision==='unknown'&&attempt===0){fallback=captured;continue;}
   return captured;
  }catch(error){
   if(!['about:blank',ORIGIN].includes(page.url()==='about:blank'?'about:blank':new URL(page.url()).origin))throw new Error('session_lost');
   const fatal=['vin_changed','ambiguous_vin','session_lost','vehicle_source_changed','vehicle_identity_changed','vehicle_identity_unavailable'];
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
function leafTooltipTexts(elements){
 // Motive nests .phx-tooltip-content inside a wrapper with the same class.
 // Retain the actual text leaf so one rendered tooltip is counted once.
 return elements.filter(e=>!e.querySelector('.phx-tooltip-content')).map(e=>e.innerText);
}
function newTooltip(before,after){
 const prior=new Set(before.map(t=>t.trim()).filter(Boolean));
 const added=after.map(t=>t.trim()).filter(t=>t&&!prior.has(t));
 if(added.length>1)throw new Error('unowned_timestamp_tooltip');
 return added[0]||null;
}
async function readVehiclePage(page,link,bind,attempt=0,{reviewed=false,context}={}){
 await page.goto(ORIGIN+'/en-US/'+link.href,{waitUntil:'domcontentloaded',timeout:45000});
 await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().waitFor().catch(()=>{throw new Error('vehicle_summary_unavailable');});
 if(!reviewed)await page.waitForFunction(()=>/\bVIN\s*[:\t ]*\s*[A-HJ-NPR-Z0-9]{17}\b/.test(document.body.innerText),null,{timeout:15000}).catch(()=>{});
 if(!page.url().endsWith(link.href))throw new Error('vin_changed');
 const beforeIdentity=reviewed?await readReviewedPageIdentity(page,link):null;
 const vin=bind(reviewed?beforeIdentity.vin:await page.locator('body').innerText());
 const verifyLive=text=>{if(reviewed){if(vin===null)assertNoLiveVin(text);else if(bindVin(vin,text)!==vin)throw new Error('vin_changed');}else bind(text);};
 await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().click();
 if(vin)await page.getByText(vin,{exact:true}).first().waitFor().catch(()=>{throw new Error('live_vin_unavailable');});
 else await page.locator('section.driver-location-info').filter({visible:true}).first().waitFor();
 const liveText=await page.locator('body').innerText();verifyLive(liveText);
 assertLiveProvider(page.url(),link.href.split('/').pop());
 if(liveText.includes('Add Vehicle Gateway to see location data'))throw new Error('provider_location_unavailable');
 const {control,address}=await locationControl(page);
 async function timestamp(){
  const status=page.locator('.current-location-status').filter({visible:true});
  if(await status.count()===0)return {rawTimestamp:null,sourceAge:null,timestampReason:'status_unavailable'};
  if(await status.count()!==1)throw new Error('unowned_timestamp_tooltip');
  const sourceAge=(await status.innerText()).trim()||null;
  // Ignore unchanged unrelated tooltips; only a unique newly rendered tooltip
  // following this exact status hover can supply its source timestamp.
  await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().hover();
  await page.waitForTimeout(350);
  const tips=page.locator('.phx-tooltip-content:visible');
  const prior=await tips.evaluateAll(leafTooltipTexts);
  await status.hover();
  for(let i=0;i<30;i++){
   const rawTimestamp=newTooltip(prior,await tips.evaluateAll(leafTooltipTexts));
   if(rawTimestamp)return {rawTimestamp,sourceAge,timestampReason:null};
   await page.waitForTimeout(100);
  }
  return {rawTimestamp:null,sourceAge,timestampReason:'timestamp_tooltip_unavailable'};
 }
 async function point(){
  assertLiveProvider(page.url(),link.href.split('/').pop());verifyLive(await page.locator('body').innerText());
  await page.mouse.move(0,0);await control.click();
  return copyFresh({clear:()=>page.evaluate(()=>navigator.clipboard.writeText('')),click:async()=>{const copy=page.locator('[phxcontent="Copy coordinates"]').filter({visible:true});await copy.first().waitFor().catch(()=>{throw new Error('copy_control_unavailable');});if(await copy.count()!==1)throw new Error('copy_control_unavailable');await copy.click();},read:()=>page.evaluate(()=>navigator.clipboard.readText()),pause:ms=>page.waitForTimeout(ms)});
 }
 const observation=await stableObservation({timestamp,point,allowUnstableSpeed:attempt>0,speed:()=>readSpeed(page),verifyVin:async()=>{assertLiveProvider(page.url(),link.href.split('/').pop());verifyLive(await page.locator('body').innerText());},address});
 if(reviewed){sameIdentity(beforeIdentity,await readReviewedIdentity(context,link));if(vin===null)observation.source_vin_state=beforeIdentity.source_vin_state;}
 return observation;
}
async function collect(output){
 if(!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw new Error('missing_credentials');
 const reviewedProviders=allowlist();
 const {chromium}=require('playwright');
 phase('browser_launch');
 const browser=await chromium.launch({headless:true});
 const result={company_label:COMPANY,company_id:COMPANY_ID,company_verified_before:false,company_verified_after:false,complete:false,started_at:new Date().toISOString(),vehicles:[]};
 const save=()=>atomic(output,result);
 try{
  const {context,page}=await prepareSyncLogin(browser,{phase});
  await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:ORIGIN});
  phase('login_email');
  await page.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);
  phase('login_password');
  await page.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);
  phase('login_submit');
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  phase('login_app_redirect');
  await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  async function company(){
   await page.goto(ORIGIN+'/en-US/#/admin/company',{waitUntil:'domcontentloaded'});
   await page.getByText(/KT8934277/).waitFor({timeout:30000});
   const text=await page.locator('body').innerText();
   if(!text.includes(COMPANY)||!text.includes(COMPANY_ID))throw new Error('company_mismatch');
  }
  phase('company_before');
  await company();result.company_verified_before=true;
  phase('timezone');
  await page.goto(ORIGIN+'/en-US/#/settings',{waitUntil:'domcontentloaded'});
  await page.getByText(/Eastern Time - New York/).waitFor({timeout:30000});
  result.timezone_evidence=await page.getByText('Time zone',{exact:true}).evaluate(e=>e.parentElement.innerText);
  if(!/Eastern Time - New York/.test(result.timezone_evidence))throw new Error('timezone_unverified');
  phase('vehicle_directory');
  await page.goto(ORIGIN+'/en-US/#/admin/vehicles',{waitUntil:'domcontentloaded'});
  await page.getByText(/Showing \d+ of \d+/).waitFor({timeout:30000});
  const directory=await page.locator('body').innerText();
  const total=directory.match(/Showing (\d+) of (\d+)/);
  const links=await page.locator('a[href*="/vehicles/summary/"]').evaluateAll(es=>es.map(e=>({unit:e.innerText.trim(),href:e.getAttribute('href')})));
  const vehicles=[...new Map(links.map(x=>[x.href,x])).values()];
  // Fail closed on pagination/filters rather than silently call one page fleet-wide.
  if(!total||+total[1]!==+total[2]||vehicles.length!==+total[2]||vehicles.length===0||vehicles.length>250)throw new Error('directory_incomplete');
  result.directory_count=vehicles.length;save();
  const tasks=openTasks(output,{kind:'location',company:COMPANY_ID,timezone:'America/New_York',vehicles},{maxAgeMs:10*60*1000});result.started_at=tasks.startedAt;
  for(const link of vehicles){
   if(!/^#\/fleetview\/vehicles\/summary\/\d+$/.test(link.href))throw new Error('vehicle_link_invalid');
   const reviewed=isReviewed(reviewedProviders,COMPANY_ID,link.href.split('/').pop());
   const row=await tasks.run('location_vehicle',link,()=>collectWithRetries(context,link,readVehiclePage,{reviewed}),{attempts:1,cacheable:row=>row.status==='located',validateCached:async cached=>{
    const proof=reviewed?await readReviewedIdentity(context,link):{vin:await readVehicleVin(context,link)};
    if(proof.vin!==cached.vin||(cached.vin===null&&proof.source_vin_state!==cached.source_vin_state))throw new Error('vehicle_identity_changed');
   }});
   result.vehicles.push(row);save();
   console.log(JSON.stringify({stage:'progress',attempted:result.vehicles.length,total:vehicles.length,located:result.vehicles.filter(x=>x.status==='located').length}));
  }
  tasks.assertFresh();
  phase('company_after');
  await company();tasks.assertFresh();result.company_verified_after=true;result.complete=true;result.finished_at=new Date().toISOString();save();
  return result;
 }finally{await closeBrowser(browser);}
}
if(require.main===module){
 const output=process.argv[2];
 if(!output){console.error('Output file required');process.exitCode=1;}
 else collect(output).then(r=>console.log(JSON.stringify({stage:'collection_complete',complete:r.complete,count:r.vehicles.length,located:r.vehicles.filter(x=>x.status==='located').length}))).catch(error=>{failed(output,error);console.error(JSON.stringify({stage:'collection_failed',reason:error?.name==='TimeoutError'?'ui_timeout':'collection_failed',import_permitted:false}));process.exitCode=1;});
}
module.exports={collect,vinFrom,coordinates,addressFrom,bindVin,observationTime,stableObservation,collectWithRetries,assertLiveProvider,locationControl,newTooltip,leafTooltipTexts,speedFromParts,readSpeed};
