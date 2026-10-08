/* Rendered Motive daily fuel reports only. No private endpoints or session extraction. */
const fs=require('node:fs');
const {validateDirectory,readVehicleVin}=require('./collect_trips.cjs');
const ORIGIN='https://app.gomotive.com', COMPANY='77 CARGO LLC', COMPANY_ID='KT8934277';
const HEADERS=['VEHICLE NUMBER','MAKE / MODEL / YEAR','GROUP','AVG. MPG','MOVING MPG','TOTAL DISTANCE (MI)','TOTAL FUEL (GAL)','EST. CARBON EMISSIONS (LBS)','UTILIZATION','DRIVING TIME','DRIVING FUEL (GAL)','IDLING TIME','IDLED FUEL (GAL)','FUEL COST (USD)','ODOMETER (MI)','FUEL TYPE','NUMBER OF OPEN FAULT CODES','OPEN FAULT CODES'];
function dates(now=new Date(),days=3){
 if(!Number.isInteger(days)||days<1||days>7)throw Error('invalid_days');
 const last=new Date(now);last.setUTCHours(0,0,0,0);last.setUTCDate(last.getUTCDate()-(now.getUTCHours()>=12?1:2));
 return Array.from({length:days},(_,i)=>new Date(last.getTime()-(days-1-i)*86400000).toISOString().slice(0,10));
}
function reportUrl(date,id){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!/^\d+$/.test(id))throw Error('invalid_report_identity');
 return `${ORIGIN}/en-US/#/reports/vehicle-fuel-performance;report_id=48;report_type=normal;start_date=${date};end_date=${date};vehicle_ids=${id}`;
}
function verifyUrl(url,date,id){
 const u=new URL(url),parts=u.hash.split(';'),params=new Map(parts.slice(1).map(x=>x.split('=')));
 if(u.origin!==ORIGIN||u.pathname!=='/en-US/'||parts[0]!=='#/reports/vehicle-fuel-performance'||params.size!==parts.length-1||params.size!==5||params.get('report_id')!=='48'||params.get('report_type')!=='normal'||params.get('start_date')!==date||params.get('end_date')!==date||params.get('vehicle_ids')!==id)throw Error('report_identity_changed');
}
function number(text){
 const value=text.trim();if(['','--','—'].includes(value))return null;
 if(!/^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,3})?$/.test(value))throw Error('invalid_numeric_cell');
 return value.replaceAll(',','');
}
function duration(text){
 const value=text.trim();if(['','--','—'].includes(value))return null;
 const match=value.match(/^(?:(\d+)h(?:\s+|$))?(?:(\d+)m(?:\s+|$))?(?:(\d+)s)?$/);
 if(!match||!match.slice(1).some(x=>x!==undefined))throw Error('invalid_duration_cell');
 return (+match[1]||0)*3600+(+match[2]||0)*60+(+match[3]||0);
}
function readings(cells){
 const get=k=>{if(typeof cells[k]!=='string')throw Error('report_layout_changed');return cells[k];};
 return {driving_fuel_gallons:number(get('driving-fuel')),idling_fuel_gallons:number(get('idle-fuel')),reported_total_fuel_gallons:number(get('total-fuel')),source_distance_miles:number(get('total-distance')),source_driving_seconds:duration(get('driving-time')),source_idling_seconds:duration(get('idle-time'))};
}
function validateSnapshot(snapshot,date,vehicle){
 verifyUrl(snapshot.url,date,vehicle.provider_vehicle_id);
 if(!snapshot.headers.length||snapshot.visible_date_text===null||snapshot.selected_unit===null)return null;
 if(JSON.stringify(snapshot.headers.map(s=>s.trim().toUpperCase()))!==JSON.stringify(HEADERS))throw Error('report_layout_changed');
 const label=new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${date}T12:00:00Z`));
 if(snapshot.visible_date_text!==label||snapshot.selected_unit!==vehicle.unit)throw Error('report_filter_changed');
 if(snapshot.rows.length>1)throw Error('report_not_single_vehicle');
 if(!snapshot.rows.length&&!snapshot.explicit_empty)return null;
 if(snapshot.rows.length&&snapshot.explicit_empty)throw Error('report_ambiguous_empty');
 if(snapshot.rows.length&&snapshot.rows[0].vehicle!==vehicle.unit)throw Error('report_vehicle_changed');
 return true;
}
function finalizeReport(snapshot,date,vehicle,sourceRead){
 if(!validateSnapshot(snapshot,date,vehicle))throw Error('report_incomplete');
 const values=snapshot.rows.length?readings(snapshot.rows[0]):{};
 const reported=snapshot.rows.length&&[values.driving_fuel_gallons,values.idling_fuel_gallons,values.reported_total_fuel_gallons].some(x=>x!==null);
 const terminal=snapshot.explicit_empty?'No results found. Please update search criteria.':'Single provider daily report: one stable row';
 return {record:{report_date:date,state:reported?'reported':'source_missing',source_read_at:sourceRead,...values,...(!reported?{reason:snapshot.explicit_empty?'explicit_no_results':'fuel_readings_missing'}:{})},report:{report_date:date,provider_vehicle_id:vehicle.provider_vehicle_id,filter_start:date,filter_end:date,report_url:snapshot.url,visible_date_text:snapshot.visible_date_text,selected_unit:snapshot.selected_unit,headers:snapshot.headers,complete:true,source_read_at:sourceRead,row_count:snapshot.rows.length,explicit_empty:snapshot.explicit_empty,raw_cells:snapshot.rows.map(row=>Object.fromEntries(['vehicle','driving-fuel','idle-fuel','total-fuel','total-distance','driving-time','idle-time'].map(key=>[key,row[key]]))),terminal_evidence:terminal}};
}
function save(output,result){const temp=output+'.tmp';fs.writeFileSync(temp,JSON.stringify(result,null,2),{mode:0o600});fs.chmodSync(temp,0o600);fs.renameSync(temp,output);}
async function readReport(page,date,vehicle){
 const label=new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${date}T12:00:00Z`));
 return page.evaluate(({label,unit})=>{
  const visible=e=>e.getBoundingClientRect().height>0&&getComputedStyle(e).visibility!=='hidden';
  const dateLabels=[...document.querySelectorAll('.phx-date-picker-range-labels .phx-date-picker-label')].filter(visible).map(e=>e.innerText.trim());
  const selectedValues=[...document.querySelectorAll('phx-select[phx-non-default-selected="true"] .phx-select-value')].filter(visible).map(e=>e.innerText.trim());
  const headerTables=[...document.querySelectorAll('table')].filter(t=>visible(t)&&[...t.querySelectorAll('th')].some(e=>e.innerText.trim().toUpperCase()==='VEHICLE NUMBER'));
  const rows=[...document.querySelectorAll('tr[data-e2e="table-row"]')].filter(visible).map(r=>Object.fromEntries([...r.querySelectorAll('td[data-e2e]')].map(c=>[c.getAttribute('data-e2e'),c.innerText.trim()])));
  return {url:location.href,headers:headerTables.length===1?[...headerTables[0].querySelectorAll('th')].map(e=>e.innerText.trim()):[],visible_date_text:dateLabels.length===1?dateLabels[0]:null,selected_unit:selectedValues.length===1?selectedValues[0]:null,rows,explicit_empty:document.body.innerText.includes('No results found. Please update search criteria.')};
 },{label,unit:vehicle.unit});
}
async function collectReport(context,date,vehicle){
 const page=await context.newPage();page.setDefaultTimeout(15000);
 try{
  await page.goto(reportUrl(date,vehicle.provider_vehicle_id),{waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForFunction(()=>[...document.querySelectorAll('th')].some(e=>e.getBoundingClientRect().height>0&&e.innerText.trim().toUpperCase()==='VEHICLE NUMBER'),null,{timeout:45000});
  let previous=null,stable=0;
  for(let i=0;i<60;i++){
   const snapshot=await readReport(page,date,vehicle);
   // Fresh document plus exact provider/date/filter verification prevents old SPA rows.
   const valid=validateSnapshot(snapshot,date,vehicle),key=JSON.stringify(snapshot);
   stable=valid&&key===previous?stable+1:0;previous=key;
   if(stable>=4)return finalizeReport(snapshot,date,vehicle,new Date().toISOString());
   await page.waitForTimeout(750);
  }
  throw Error('report_incomplete');
 }finally{await page.close();}
}
async function collect(output){
 if(!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw Error('missing_credentials');
 const requested=dates(new Date(),Number(process.env.MOTIVE_FUEL_DAYS||3));
 const result={version:1,company_label:COMPANY,company_id:COMPANY_ID,company_verified_before:false,company_verified_after:false,complete:false,started_at:new Date().toISOString(),report_dates:requested,vehicles:[],reports:[]};save(output,result);
 const {chromium}=require('playwright'),browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US'}),page=await context.newPage();page.setDefaultTimeout(15000);
  await page.goto(ORIGIN,{waitUntil:'domcontentloaded',timeout:45000});await page.waitForURL('https://auth.gomotive.com/login**',{timeout:30000});if(new URL(page.url()).origin!=='https://auth.gomotive.com')throw Error('login_origin');
  await page.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);await page.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  async function company(){const p=await context.newPage();try{await p.goto(ORIGIN+'/en-US/#/admin/company');await p.getByText(/KT8934277/).waitFor({timeout:30000});const t=await p.locator('body').innerText();if(!t.includes(COMPANY)||!t.includes(COMPANY_ID))throw Error('company_mismatch');}finally{await p.close();}}
  await company();result.company_verified_before=true;save(output,result);
  await page.goto(ORIGIN+'/en-US/#/settings');await page.getByText(/Eastern Time - New York/).waitFor({timeout:30000});result.timezone_evidence=await page.getByText('Time zone',{exact:true}).evaluate(e=>e.parentElement.innerText);
  await page.goto(ORIGIN+'/en-US/#/admin/vehicles');await page.getByText(/Showing \d+ of \d+/).waitFor({timeout:30000});const total=(await page.locator('body').innerText()).match(/Showing (\d+) of (\d+)/);
  const links=await page.locator('a[href*="/vehicles/summary/"]').evaluateAll(es=>es.map(e=>({unit:e.innerText.trim(),href:e.getAttribute('href')})));const directory=validateDirectory(links,+total?.[1],+total?.[2]);result.directory_count=directory.length;result.terminal_evidence=total[0];
  const vins=new Set();for(const link of directory){const vin=await readVehicleVin(context,link);if(vin&&vins.has(vin))throw Error('duplicate_vin');if(vin)vins.add(vin);result.vehicles.push({provider_vehicle_id:link.href.split('/').pop(),unit:link.unit,vin,records:[]});save(output,result);}
  for(const vehicle of result.vehicles){for(const date of requested){const {record,report}=await collectReport(context,date,vehicle);vehicle.records.push(record);result.reports.push(report);save(output,result);console.log(JSON.stringify({stage:'fuel_collection_progress',reports:result.reports.length,total:directory.length*requested.length}));}}
  await company();result.company_verified_after=true;result.finished_at=new Date().toISOString();result.complete=true;save(output,result);return result;
 }catch(error){result.failure_reason=safeFailure(error);save(output,result);throw error;}finally{await browser.close();}
}
function safeFailure(error){return ['invalid_days','missing_credentials','login_origin','company_mismatch','duplicate_vin','directory_incomplete','ambiguous_directory','vehicle_link_invalid','vehicle_source_changed','ambiguous_vin','report_identity_changed','report_layout_changed','report_filter_changed','report_not_single_vehicle','report_ambiguous_empty','report_vehicle_changed','report_incomplete','invalid_numeric_cell','invalid_duration_cell'].includes(error.message)?error.message:'browser_collection_unavailable';}
if(require.main===module){if(!process.argv[2])throw Error('Output file required');collect(process.argv[2]).then(r=>console.log(JSON.stringify({stage:'fuel_collection_complete',vehicles:r.vehicles.length,reports:r.reports.length}))).catch(e=>{console.error(JSON.stringify({stage:'fuel_collection_failed',reason:safeFailure(e),import_permitted:false}));process.exitCode=1;});}
module.exports={HEADERS,dates,reportUrl,verifyUrl,number,duration,readings,validateSnapshot,finalizeReport,readReport,collectReport,collect,safeFailure};
