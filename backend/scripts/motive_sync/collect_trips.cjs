const {readReviewedIdentity,sameIdentity}=require('./vehicle_identity.cjs');
const {prepareLegacyLogin}=require('./login.cjs');
const {spawnSync}=require('node:child_process');
/* Server collection through rendered Motive UI only; no private endpoints or session extraction. */
const fs = require('node:fs');
const {closeBrowser,phase,openTasks,retry,failed}=require('./tasks.cjs');
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
  settled=atBottom&&receipt.status==='partial'&&receipt.rows.length===previousCount?settled+1:0;previousCount=receipt.rows.length;
  // Require nine seconds of consecutive stable observations at the bottom; scrolling
  // through an unchanged loaded page is not terminal evidence for lazy pagination.
  if(atBottom && settled>=12 && receipt.rows.length>0 && Number.isInteger(total) && total===receipt.rows.length) {
   receipt=finalizeWindow(receipt,total,receipt.footer);await checkpoint(receipt);return receipt;
  }
  if(settled>=12 && receipt.status!=='loading') throw new Error('report_incomplete');
  atBottom=await advanceReportViewport(page);
  await page.waitForTimeout(750);
 }
 throw new Error('report_step_limit');
}
async function advanceReportViewport(page) {
 return page.evaluate(()=>{
  const main=document.querySelector('main');
  const tables=main?Array.from(main.querySelectorAll('table')).filter(table=>Array.from(table.querySelectorAll('th')).some(el=>/^Origin \(MDY (?:EDT|EST)\)$/i.test(el.innerText.trim()))):[];
  if(tables.length!==1)throw new Error('report_viewport_unavailable');
  // Live DOM evidence identifies the report's ant-table-body ancestor as its viewport.
  // Walk only this table's ancestors, never unrelated panels or the document window.
  let viewport=tables[0].parentElement;
  while(viewport&&!(viewport.clientHeight>0&&/(auto|scroll)/.test(getComputedStyle(viewport).overflowY)))viewport=viewport.parentElement;
  if(!viewport)throw new Error('report_viewport_unavailable');
  viewport.scrollTop+=Math.max(300,viewport.clientHeight-60);
  return viewport.scrollTop+viewport.clientHeight>=viewport.scrollHeight-2;
 });
}
async function readVehicleVinOnce(context,link) {
 // A hash-only navigation can leave the previous vehicle's rendered summary in place.
 // A fresh document per vehicle prevents a ready old Live/VIN node satisfying the waits.
 const page=await context.newPage();page.setDefaultTimeout(15000);
 try {
  await page.goto(ORIGIN+'/en-US/'+link.href,{waitUntil:'domcontentloaded',timeout:45000});
  await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().waitFor();
  await page.waitForFunction(()=>/\bVIN\s*[:\t ]*\s*[A-HJ-NPR-Z0-9]{17}\b/.test(document.body.innerText),null,{timeout:15000}).catch(()=>{});
  if(new URL(page.url()).origin!==ORIGIN||!page.url().endsWith(link.href))throw new Error('vehicle_source_changed');
  return summaryVin(await page.locator('body').innerText());
 } catch(error) {
  if(error?.name==='TimeoutError'&&page.url()!=='about:blank'&&new URL(page.url()).origin!==ORIGIN)throw new Error('session_lost');
  throw error;
 } finally {await page.close();}
}
async function readVehicleVin(context,link) {return retry('vehicle_identity',()=>readVehicleVinOnce(context,link));}
function dailyWindows(now=new Date()) {
 const range=recentWindow(now), windows=[];
 for(let date=new Date(range.start+'T12:00:00Z');date.toISOString().slice(0,10)<=range.end;date.setUTCDate(date.getUTCDate()+1)) {
  const day=date.toISOString().slice(0,10);windows.push({start:day,end:day});
 }
 return windows;
}

function importDay(output,result,plan,window,receipt,{timeout=600000}={}) {
 // Import only a separately finalized daily artifact; no aggregate checkpoint is eligible.
 const directory=path.join(path.dirname(output),window.start);
 fs.mkdirSync(directory,{mode:0o700});
 const dailySource=path.join(directory,'source.json'), dailyReceipt=path.join(directory,'receipt.json');
 const daily={...result,plan,windows:[receipt],company_verified_after:true,complete:true,finished_at:new Date().toISOString()};
 savePrivate(dailySource,daily);
 const command=['-m','scripts.motive_sync.trip_runner','--input',dailySource,'--receipt',dailyReceipt];
 if(process.env.MOTIVE_TRIPS_COMMIT==='true')command.push('--commit');
 const child=spawnSync(process.env.MOTIVE_TRIPS_PYTHON,command,{stdio:'inherit',timeout});
 if(child.error||child.status!==0)throw new Error('trip_import_failed');
 const saved=JSON.parse(fs.readFileSync(dailyReceipt,'utf8'));
 if(saved.stage!==(process.env.MOTIVE_TRIPS_COMMIT==='true'?'verified':'validated'))throw new Error('trip_import_unverified');
 return saved;
}

function validatePlan(plan) {
 const scope=plan?.scope, today=recentWindow().end;
 if(plan.version!==1||!scope||scope.company_id!==COMPANY_ID||scope.company_label!==COMPANY||scope.timezone!=='America/New_York'||
    scope.tenant_id!==process.env.MOTIVE_SYNC_TENANT_ID||scope.actor_id!==process.env.MOTIVE_SYNC_ACTOR_ID||
    scope.baseline!==(process.env.MOTIVE_TRIPS_BASELINE||'2026-04-01')||
    !/^\d{4}-\d{2}-\d{2}$/.test(scope.baseline)||scope.baseline<'2026-04-01'||
    !Array.isArray(plan.days)||plan.days.length<1||plan.days.length>31||new Set(plan.days).size!==plan.days.length||
    plan.days.some(day=>typeof day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(day)||day<scope.baseline||day>today||new Date(day+'T12:00:00Z').toISOString().slice(0,10)!==day)||
    !process.env.MOTIVE_TRIPS_PYTHON)throw new Error('trip_plan_invalid');
 return plan;
}

async function collect(output) {
 if(!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw new Error('missing_credentials');
 const {chromium}=require('playwright'), adapter=await reportModule();
 const result={company_label:COMPANY,company_id:COMPANY_ID,company_verified_before:false,company_verified_after:false,complete:false,started_at:new Date().toISOString(),vehicles:[],windows:[]};
 const save=()=>savePrivate(output,result);save();
 phase('browser_launch');
 const browser=await chromium.launch({headless:true});
 try {
  const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US'});
  const page=await context.newPage();page.setDefaultTimeout(15000);
  phase('login_navigate');
  await page.goto(ORIGIN,{waitUntil:'domcontentloaded',timeout:45000});
  phase('login_auth_redirect');
  await page.waitForURL('https://auth.gomotive.com/login**',{timeout:30000});
  phase('login_origin_check');
  if(new URL(page.url()).origin!=='https://auth.gomotive.com')throw new Error('login_origin');
  await prepareLegacyLogin(page,{phase});
  phase('login_email');
  await page.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);
  phase('login_password');
  await page.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);
  phase('login_submit');
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  phase('login_app_redirect');
  await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  async function company() {
   await page.goto(ORIGIN+'/en-US/#/admin/company',{waitUntil:'domcontentloaded'});
   await page.getByText(/KT8934277/).waitFor({timeout:30000});
   const text=await page.locator('body').innerText();
   if(!text.includes(COMPANY)||!text.includes(COMPANY_ID))throw new Error('company_mismatch');
  }
  phase('company_before');
  await company();result.company_verified_before=true;save();
  phase('timezone');
  await page.goto(ORIGIN+'/en-US/#/settings',{waitUntil:'domcontentloaded'});
  await page.getByText(/Eastern Time - New York/).waitFor({timeout:30000});
  result.timezone_evidence=await page.getByText('Time zone',{exact:true}).evaluate(el=>el.parentElement.innerText);
  if(!result.timezone_evidence.includes('Eastern Time - New York'))throw new Error('timezone_unverified');
  phase('vehicle_directory');
  await page.goto(ORIGIN+'/en-US/#/admin/vehicles',{waitUntil:'domcontentloaded'});
  await page.getByText(/Showing \d+ of \d+/).waitFor({timeout:30000});
  const total=(await page.locator('body').innerText()).match(/Showing (\d+) of (\d+)/);
  const links=await page.locator('a[href*="/vehicles/summary/"]').evaluateAll(es=>es.map(el=>({unit:el.innerText.trim(),href:el.getAttribute('href')})));
  const directory=validateDirectory(links,Number(total?.[1]),Number(total?.[2]));
  result.directory_count=directory.length;save();const seenVins=new Map();
  for(const link of directory) {
   const proof=link.href==='#/fleetview/vehicles/summary/5981300'?await readReviewedIdentity(context,link):null;
   if(proof?.vin)throw new Error('reviewed_vin_changed');
   const vin=proof?null:await readVehicleVin(context,link);
   if(vin&&seenVins.has(vin)) {
    result.failure={reason:'duplicate_vin',current_provider_vehicle_id:link.href.split('/').pop(),prior_provider_vehicle_id:seenVins.get(vin),unit:link.unit};save();
    throw new Error('duplicate_vin');
   }
   if(vin)seenVins.set(vin,link.href.split('/').pop());
   result.vehicles.push({provider_vehicle_id:link.href.split('/').pop(),unit:link.unit,vin,...(proof?{source_vin_state:proof.source_vin_state}:!vin?{reason:'vin_unavailable'}:{})});save();
  }
  const planFile=process.env.MOTIVE_TRIPS_PLAN_FILE;
  const plan=planFile?JSON.parse(fs.readFileSync(planFile,'utf8')):null;
  if(plan)validatePlan(plan);
  const windows=plan?plan.days.map(day=>({start:day,end:day})):dailyWindows();
  const tasks=openTasks(output,{kind:'trips',company:COMPANY_ID,timezone:'America/New_York',vehicles:result.vehicles,windows},{maxAgeMs:30*60*1000});
  result.started_at=tasks.startedAt;
  for(const window of windows) {
   const reviewed=result.vehicles.find(vehicle=>vehicle.provider_vehicle_id==='5981300');
   const link=directory.find(link=>link.href==='#/fleetview/vehicles/summary/5981300');
   if(reviewed){
    const proof=await readReviewedIdentity(context,link);
    if(proof.vin||proof.source_vin_state!==reviewed.source_vin_state)throw new Error('reviewed_vin_changed');
    reviewed.identity_before={...proof,read_at:new Date().toISOString()};
   }
   const receipt=await tasks.run('trip_window',window,async()=>{
    const reportPage=await context.newPage();reportPage.setDefaultTimeout(15000);
    try{return await collectWindow(reportPage,window,async()=>{},adapter);}
    finally{await reportPage.close();}
   });
   if(reviewed){
    const proof=await readReviewedIdentity(context,link);
    sameIdentity(reviewed.identity_before,proof);
    reviewed.identity_after={...proof,read_at:new Date().toISOString()};
   }
   result.windows.push(receipt);save();
   if(plan) {
    // Finalize and import each exact day before moving on. A later source failure
    // leaves earlier receipts recoverable, without another login or VIN traversal.
    tasks.assertFresh();phase('company_after');await company();tasks.assertFresh();
    importDay(output,result,plan,window,receipt);
   }
  }
  tasks.assertFresh();
  phase('company_after');
  await company();tasks.assertFresh();result.company_verified_after=true;result.complete=true;result.finished_at=new Date().toISOString();save();
  return result;
 } finally {await closeBrowser(browser);}
}
function safeFailure(error) {
 const known=new Set(['missing_credentials','ambiguous_vin','directory_incomplete','vehicle_link_invalid','ambiguous_directory','session_lost','report_incomplete','report_step_limit','login_origin','company_mismatch','timezone_unverified','vehicle_source_changed','duplicate_vin','report_viewport_unavailable']);
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
 else collect(process.argv[2]).then(r=>console.log(JSON.stringify({stage:'trip_collection_complete',complete:r.complete,vehicles:r.vehicles.length,rows:r.windows.reduce((n,w)=>n+w.rows.length,0)}))).catch(error=>{failed(process.argv[2],error);console.error(JSON.stringify({stage:'trip_collection_failed',reason:safeFailure(error),import_permitted:false}));process.exitCode=1;});
}
module.exports={importDay,validatePlan,collect,collectWindow,recentWindow,dailyWindows,summaryVin,validateDirectory,safeFailure,readVehicleVin,readVehicleVinOnce,advanceReportViewport};
