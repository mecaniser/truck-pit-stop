/* Server collection through rendered Motive UI only; no private endpoints or session extraction. */
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const ORIGIN = 'https://app.gomotive.com';
const COMPANY = '77 CARGO LLC', COMPANY_ID = 'KT8934277';
function recentWindow(now = new Date()) {
 const today = new Intl.DateTimeFormat('en-CA', {timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
 const start = new Date(`${today}T12:00:00Z`); start.setUTCDate(start.getUTCDate()-2);
 return {start:start.toISOString().slice(0,10),end:today};
}
function summaryVin(text) {
 const values=[...new Set(Array.from(text.matchAll(/\bVIN\s*[:\t ]*\s*([A-HJ-NPR-Z0-9]{17})\b/g),m=>m[1]))];
 if(values.length>1) throw new Error('ambiguous_vin');
 return values[0] || null;
}
function validateDirectory(links, shown, total) {
 const vehicles=[...new Map(links.map(x=>[x.href,x])).values()];
 if(!Number.isInteger(total)||shown!==total||vehicles.length!==total||total<1||total>250) throw new Error('directory_incomplete');
 for(const row of vehicles) if(!/^#\/fleetview\/vehicles\/summary\/\d+$/.test(row.href)||!row.unit) throw new Error('vehicle_link_invalid');
 // A repeated link with different labels is ambiguous, not a harmless duplicate anchor.
 for(const row of links) if(vehicles.find(x=>x.href===row.href).unit!==row.unit) throw new Error('ambiguous_directory');
 return vehicles;
}
function savePrivate(output, data) {
 const temporary=output+'.tmp';
 fs.writeFileSync(temporary,JSON.stringify(data,null,2),{mode:0o600});fs.chmodSync(temporary,0o600);fs.renameSync(temporary,output);
}
async function reportModule() {
 const installed=path.resolve(__dirname,'../../collectors/collect_motive_trips.mjs');
 const local=path.resolve(__dirname,'../../../scripts/collect_motive_trips.mjs');
 return import(pathToFileURL(fs.existsSync(installed)?installed:local).href);
}
async function collectWindow(page, window, checkpoint, adapter, {maxSteps=120}={}) {
 const {reportUrl,newWindow,captureStep,finalizeWindow}=adapter;
 await page.goto(reportUrl(window.start,window.end),{waitUntil:'domcontentloaded',timeout:45000});
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('main table th')).some(el=>/^Origin \(MDY (?:EDT|EST)\)$/i.test(el.innerText.trim())&&el.getBoundingClientRect().height>0),null,{timeout:45000});
 let receipt=newWindow(window.start,window.end), settled=0, previousCount=-1, atBottom=false;
 for(let step=0;step<maxSteps;step++) {
  if(new URL(page.url()).origin!==ORIGIN) throw new Error('session_lost');
  receipt=await captureStep(page,receipt,{verifiedTimezone:'America/New_York'});await checkpoint(receipt);
  if(receipt.status==='empty') { receipt=finalizeWindow(receipt,0,receipt.terminal_evidence);await checkpoint(receipt);return receipt; }
  const total=Number(receipt.footer?.match(/^Showing ([\d,]+) results$/)?.[1]?.replaceAll(',',''));
  settled=receipt.rows.length===previousCount?settled+1:0;previousCount=receipt.rows.length;
  // Read to the end, then require repeated stable rendered observations and exact visible count.
  if(atBottom && settled>=3 && receipt.rows.length>0 && Number.isInteger(total) && total===receipt.rows.length) {
   receipt=finalizeWindow(receipt,total,receipt.footer);await checkpoint(receipt);return receipt;
  }
  if(settled>=12 && receipt.status!=='loading') throw new Error('report_incomplete');
  // DOM-backed scroll geometry only. No framework state, network calls or hidden data.
  atBottom=await page.evaluate(()=>{
   const main=document.querySelector('main'); if(!main)return false;
   const nodes=[main,...main.querySelectorAll('*')].filter(el=>el.scrollHeight>el.clientHeight+10&&el.clientHeight>80&&/(auto|scroll)/.test(getComputedStyle(el).overflowY));
   for(const el of nodes)el.scrollTop+=Math.max(300,el.clientHeight-60);
   window.scrollBy(0,Math.max(300,innerHeight-60));
   const scrolling=document.scrollingElement;
   return nodes.every(el=>el.scrollTop+el.clientHeight>=el.scrollHeight-2)&&(!scrolling||scrolling.scrollTop+innerHeight>=scrolling.scrollHeight-2);
  });
  await page.waitForTimeout(750);
 }
 throw new Error('report_step_limit');
}
async function readVehicleVin(context,link) {
 // A hash-only navigation can leave the previous vehicle's rendered summary in place.
 // A fresh document per vehicle prevents a ready old Live/VIN node satisfying the waits.
 const page=await context.newPage();page.setDefaultTimeout(15000);
 try {
  await page.goto(ORIGIN+'/en-US/'+link.href,{waitUntil:'domcontentloaded',timeout:45000});
  await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().waitFor();
  await page.waitForFunction(()=>/\bVIN\s*[:\t ]*\s*[A-HJ-NPR-Z0-9]{17}\b/.test(document.body.innerText),null,{timeout:15000}).catch(()=>{});
  if(new URL(page.url()).origin!==ORIGIN||!page.url().endsWith(link.href))throw new Error('vehicle_source_changed');
  return summaryVin(await page.locator('body').innerText());
 } finally {await page.close();}
}
async function collect(output) {
 if(!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw new Error('missing_credentials');
 const {chromium}=require('playwright'), adapter=await reportModule();
 const result={company_label:COMPANY,company_id:COMPANY_ID,company_verified_before:false,company_verified_after:false,complete:false,started_at:new Date().toISOString(),vehicles:[],windows:[]};
 const save=()=>savePrivate(output,result);save();
 const browser=await chromium.launch({headless:true});
 try {
  const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US'});
  const page=await context.newPage();page.setDefaultTimeout(15000);
  await page.goto(ORIGIN,{waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForURL('https://auth.gomotive.com/login**',{timeout:30000});
  if(new URL(page.url()).origin!=='https://auth.gomotive.com')throw new Error('login_origin');
  await page.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);
  await page.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  async function company() {
   await page.goto(ORIGIN+'/en-US/#/admin/company',{waitUntil:'domcontentloaded'});
   await page.getByText(/KT8934277/).waitFor({timeout:30000});
   const text=await page.locator('body').innerText();
   if(!text.includes(COMPANY)||!text.includes(COMPANY_ID))throw new Error('company_mismatch');
  }
  await company();result.company_verified_before=true;save();
  await page.goto(ORIGIN+'/en-US/#/settings',{waitUntil:'domcontentloaded'});
  await page.getByText(/Eastern Time - New York/).waitFor({timeout:30000});
  result.timezone_evidence=await page.getByText('Time zone',{exact:true}).evaluate(el=>el.parentElement.innerText);
  if(!result.timezone_evidence.includes('Eastern Time - New York'))throw new Error('timezone_unverified');
  await page.goto(ORIGIN+'/en-US/#/admin/vehicles',{waitUntil:'domcontentloaded'});
  await page.getByText(/Showing \d+ of \d+/).waitFor({timeout:30000});
  const total=(await page.locator('body').innerText()).match(/Showing (\d+) of (\d+)/);
  const links=await page.locator('a[href*="/vehicles/summary/"]').evaluateAll(es=>es.map(el=>({unit:el.innerText.trim(),href:el.getAttribute('href')})));
  const directory=validateDirectory(links,Number(total?.[1]),Number(total?.[2]));
  result.directory_count=directory.length;save();const seenVins=new Map();
  for(const link of directory) {
   const vin=await readVehicleVin(context,link);
   if(vin&&seenVins.has(vin)) {
    result.failure={reason:'duplicate_vin',current_provider_vehicle_id:link.href.split('/').pop(),prior_provider_vehicle_id:seenVins.get(vin),unit:link.unit};save();
    throw new Error('duplicate_vin');
   }
   if(vin)seenVins.set(vin,link.href.split('/').pop());
   result.vehicles.push({provider_vehicle_id:link.href.split('/').pop(),unit:link.unit,vin,...(!vin?{reason:'vin_unavailable'}:{})});save();
  }
  const reportPage=await context.newPage();reportPage.setDefaultTimeout(15000);
  try {await collectWindow(reportPage,recentWindow(),async receipt=>{result.windows=[receipt];save();},adapter);}
  finally {await reportPage.close();}
  await company();result.company_verified_after=true;result.complete=true;result.finished_at=new Date().toISOString();save();
  return result;
 } finally {await browser.close();}
}
function safeFailure(error) {
 const known=new Set(['missing_credentials','ambiguous_vin','directory_incomplete','vehicle_link_invalid','ambiguous_directory','session_lost','report_incomplete','report_step_limit','login_origin','company_mismatch','timezone_unverified','vehicle_source_changed','duplicate_vin']);
 const adapterFailures=new Map([
  ['Motive report unavailable: check login','report_unavailable'],
  ['New York timezone verification required','timezone_unverified'],
  ['Motive table layout or timezone changed','report_layout_changed'],
  ['Report timezone changed during collection','report_timezone_changed'],
  ['Unexpected source page','report_source_changed'],
  ['Source filters do not match requested window','report_filter_mismatch'],
  ['Source became empty during collection','report_changed'],
  ['Collection row limit reached','report_row_limit'],
  ['Conflicting or ambiguous source identities','report_identity_conflict'],
  ['Incomplete source window','report_incomplete'],
 ]);
 if(known.has(error?.message))return error.message;
 if(adapterFailures.has(error?.message))return adapterFailures.get(error.message);
 return error?.name==='TimeoutError'?'ui_timeout':'collection_failed';
}
if(require.main===module) {
 if(!process.argv[2]){console.error('Output file required');process.exitCode=1;}
 else collect(process.argv[2]).then(r=>console.log(JSON.stringify({stage:'trip_collection_complete',complete:r.complete,vehicles:r.vehicles.length,rows:r.windows.reduce((n,w)=>n+w.rows.length,0)}))).catch(error=>{console.error(JSON.stringify({stage:'trip_collection_failed',reason:safeFailure(error),import_permitted:false}));process.exitCode=1;});
}
module.exports={collect,collectWindow,recentWindow,summaryVin,validateDirectory,safeFailure,readVehicleVin};
