/* Rendered Motive UI observations only; never private APIs or extracted sessions. */
const fs = require('node:fs');
const {readVehicleVin} = require('../motive_sync/collect_trips.cjs');
const ORIGIN = 'https://app.gomotive.com';
const DIRECTORY = '/en-US/#/fleetview/list/drivers';
const RANGES = '/en-US/#/admin/safety/performance-ranges';
const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();
const optional = value => !value || /^(?:—|N\/A|-)$/i.test(clean(value)) ? null : clean(value);
function parseRanges(text) {
 const matches = [...text.matchAll(/\b(Fair|Good|Excellent)\s+(\d+)\s*[–—-]\s*(\d+)/g)];
 const labels = ['Fair', 'Good', 'Excellent'], bands = ['red', 'yellow', 'green'];
 if (matches.length !== 3) throw new Error('performance_ranges_unavailable');
 const ranges = matches.map((m,i) => ({label:m[1],min:Number(m[2]),max:Number(m[3]),band:bands[i]}));
 if (ranges.some((r,i)=>r.label!==labels[i]||r.min>r.max||(i&&r.min!==ranges[i-1].max+1)) || ranges[0].min!==50 || ranges[2].max!==100) throw new Error('performance_ranges_invalid');
 return ranges;
}
function classify(score, ranges) {
 if(score===null) return {band:'unknown',band_label:null};
 const range = ranges.find(r=>score>=r.min&&score<=r.max);
 return range ? {band:range.band,band_label:`${range.label} (${range.min}–${range.max})`} : {band:'unknown',band_label:null};
}
function directoryColumns(headers) {
 if(!Array.isArray(headers)||headers.some(header=>typeof header!=='string'))throw new Error('driver_directory_layout');
 const normalized=headers.map(header=>clean(header).toUpperCase());
 const find=label=>{
  const matches=normalized.flatMap((header,index)=>header===label?[index]:[]);
  if(matches.length!==1)throw new Error('driver_directory_layout');
  return matches[0];
 };
 return {driver:find('DRIVER NAME / ID'),vehicle:find('VEHICLE ID')};
}
function validateDirectory(snapshot) {
 const columns=directoryColumns(snapshot.headers);
 const footer = snapshot.footer?.match(/^Showing ([\d,]+) of ([\d,]+)$/);
 const count = Number(footer?.[2]?.replaceAll(',',''));
 if (!footer || !Array.isArray(snapshot.rows) || Number(footer[1].replaceAll(',',''))!==count || count!==snapshot.rows.length || count<0 || count>250) throw new Error('driver_directory_incomplete');
 const drivers = new Set(), vehicles = new Set();
 return snapshot.rows.map(row=>{
  if(!Array.isArray(row.cells)||row.cells.length!==snapshot.headers.length||row.cells.some(cell=>!cell||!Array.isArray(cell.anchors)||(cell.colspan??1)!==1||(cell.rowspan??1)!==1))throw new Error('driver_directory_layout');
  const driverCell=row.cells[columns.driver],vehicleCell=row.cells[columns.vehicle];
  const driverLinks=driverCell.anchors.filter(link=>typeof link.href==='string'&&link.href.includes('/drivers/summary/'));
  const vehicleLinks=vehicleCell.anchors.filter(link=>typeof link.href==='string'&&link.href.includes('/vehicles/summary/'));
  if(driverLinks.length!==1||vehicleLinks.length>1||(!vehicleLinks.length&&optional(vehicleCell.text)!==null))throw new Error('driver_identity_invalid');
  const driverLink=driverLinks[0],vehicleLink=vehicleLinks[0];
  const driver = driverLink.href.match(/^#\/fleetview\/drivers\/summary\/(\d+)$/);
  const vehicle = vehicleLink?.href.match(/^#\/fleetview\/vehicles\/summary\/(\d+)$/);
  if(!driver||!clean(driverLink.text)||drivers.has(driver[1])||(vehicleLink&&(!vehicle||!clean(vehicleLink.text)))) throw new Error('driver_identity_invalid');
  if(vehicle&&vehicles.has(vehicle[1])) throw new Error('ambiguous_driver_assignment');
  drivers.add(driver[1]); if(vehicle)vehicles.add(vehicle[1]);
  return {provider_driver_id:driver[1],driver_name:clean(driverLink.text),provider_vehicle_id:vehicle?.[1]??null,unit:vehicle?clean(vehicleLink.text):null};
 });
}
function emptyContent(reason) {
 return {safety:{},fuel:{},coaching:{},recent_events:[],sections:{safety:'unavailable',fuel:'unavailable',coaching:'unavailable',recent_events:'unavailable'},coverage:'partial',unavailable_reasons:[reason],source_timezone:'America/New_York'};
}
function parseSummary(snapshot, ranges) {
 const result = emptyContent('Recent safety events are a summary sample; full event history is not collected.');
 const safety = (snapshot.safety_lines??[]).map(clean).filter(Boolean);
 const behaviorIndex = safety.indexOf('Top behaviors impacting score');
 if(safety[0]==='Safety Score' && behaviorIndex>=2) {
  const labels=(snapshot.safety_score_texts??[]).map(clean);
  const scores=labels.length===1&&/^\d+(?:\.\d+)?$/.test(labels[0])?labels.map(Number):[];
  if(scores.length===1&&scores[0]>=0&&scores[0]<=100) {
   const behaviors=[]; const lines=safety.slice(behaviorIndex+1);
   for(let i=0;i<lines.length;i++) {
    const combined=lines[i].match(/^(.+?)\s+(-\d+(?:\.\d+)?)$/);
    if(combined)behaviors.push({behavior:combined[1],score_impact:Number(combined[2])});
    else if(i+1<lines.length && /^-\d+(?:\.\d+)?$/.test(lines[i+1])) behaviors.push({behavior:lines[i++],score_impact:Number(lines[i])});
    else if(!/^(?:No behaviors|No data|—)$/i.test(lines[i])) throw new Error('safety_behavior_layout');
   }
   result.safety={score:scores[0],...classify(scores[0],ranges),period_text:safety[1],coaching_label:snapshot.coaching_annotation?'Coaching':null,top_behaviors:behaviors,history:[]};result.sections.safety='available';
  } else result.unavailable_reasons.push('Safety score unavailable or ambiguous.');
 } else result.unavailable_reasons.push('Safety summary unavailable.');
 const fuel=clean(snapshot.fuel_text);
 const utilization=fuel.match(/(\d+(?:\.\d+)?)\s*%\s*UTILIZATION/i);
 const active=fuel.match(/Active time\s+((?:\d+h\s*)?\d+m|\d+h)/i),idle=fuel.match(/Idle time\s+((?:\d+h\s*)?\d+m|\d+h)/i);
 if(utilization&&Number(utilization[1])<=100&&active&&idle&&/LAST 30 DAYS/i.test(fuel)) {
  result.fuel={period_text:'LAST 30 DAYS',utilization_percent:Number(utilization[1]),active_time_text:active[1],idle_time_text:idle[1],metrics:[]};result.sections.fuel='available';
 } else result.unavailable_reasons.push('Fuel summary unavailable.');
 const coaching=clean(snapshot.coaching_text);
 const needs=coaching.match(/^Driver needs coaching\s+(.+?)\s+(\d+)$/i);
 if(needs){result.coaching={status_label:'Driver needs coaching',last_coached_text:needs[1],open_count:Number(needs[2])};result.sections.coaching='available';}
 else result.unavailable_reasons.push('Coaching status unavailable.');
 const expected=['DATE (MDY EDT) / LOCATION','VEHICLE ID / MMY','STATUS','BEHAVIOR / SEVERITY'];
 const headers=(snapshot.event_headers??[]).map(s=>clean(s).toUpperCase().replace('EST','EDT'));
 const eventColumns=expected.map(label=>headers.flatMap((header,index)=>header===label?[index]:[]));
 if(eventColumns.every(indices=>indices.length===1)) {
  result.recent_events=(snapshot.events??[]).map(cells=>{
   if(!Array.isArray(cells)||cells.length!==headers.length)throw new Error('event_layout');
   const row=eventColumns.map(indices=>cells[indices[0]]);
   const date=row[0].match(/^([A-Za-z]+ \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M)\s*([\s\S]*)$/);
   const parts=row[3].split('\n').map(clean).filter(Boolean);
   if(!date||!parts[0])throw new Error('event_layout');
   return {occurred_at_text:date[1],location:optional(date[2]),vehicle_label:optional(row[1].split('\n')[0]),status:optional(row[2]),behavior:parts[0],severity:optional(parts.slice(1).join(' '))};
  });
  if(result.recent_events.length)result.sections.recent_events='available';
  // Empty table alone is not proof of no events.
 } else result.unavailable_reasons.push('Recent safety events unavailable.');
 return result;
}
function save(output, value) {
 const temp=output+'.tmp';fs.writeFileSync(temp,JSON.stringify(value,null,2),{mode:0o600});fs.chmodSync(temp,0o600);fs.renameSync(temp,output);
}
async function directory(context) {
 const page=await context.newPage();page.setDefaultTimeout(15000);
 try {
  await page.goto(ORIGIN+DIRECTORY,{waitUntil:'domcontentloaded',timeout:45000});
  await page.getByText(/Showing [\d,]+ of [\d,]+/).waitFor({timeout:30000});
  const snapshot=await page.evaluate(()=>{
   const tables=Array.from(document.querySelectorAll('table')).filter(t=>Array.from(t.querySelectorAll('th')).some(th=>/^DRIVER NAME\s*\/\s*ID$/i.test(th.innerText.trim())));
   if(tables.length!==1)return {headers:[],rows:[],footer:null};
   const table=tables[0],headers=Array.from(table.querySelectorAll('th'));
   if(headers.some(th=>th.colSpan!==1||th.rowSpan!==1))return {headers:[],rows:[],footer:null};
   return {headers:headers.map(th=>th.innerText),footer:document.body.innerText.match(/Showing [\d,]+ of [\d,]+/)?.[0],rows:Array.from(table.querySelectorAll('tbody tr')).map(tr=>({
    cells:Array.from(tr.querySelectorAll('td')).map(td=>({text:td.innerText,colspan:td.colSpan,rowspan:td.rowSpan,anchors:Array.from(td.querySelectorAll('a')).map(a=>({href:a.getAttribute('href'),text:a.innerText}))}))
   }))};
  });
  if(page.url()!==ORIGIN+DIRECTORY)throw new Error('driver_source_changed');
  return {rows:validateDirectory(snapshot),terminal_evidence:snapshot.footer};
 }finally{await page.close();}
}
function validateSummaryIdentity(url,breadcrumbs,identity) {
 const expectedUrl=ORIGIN+'/en-US/#/fleetview/drivers/summary/'+identity.provider_driver_id;
 if(url!==expectedUrl||!Array.isArray(breadcrumbs)||breadcrumbs.length!==1)throw new Error('driver_identity_changed');
 const items=breadcrumbs[0];
 if(!Array.isArray(items)||items.length!==3
  ||clean(items[0].text)!=='Fleet View'||items[0].href!=='#/fleetview/map'
  ||clean(items[1].text)!=='Drivers'||items[1].href!=='#/fleetview/list/drivers'
  ||clean(items[2].text)!==clean(identity.driver_name)||items[2].href!==null)throw new Error('driver_identity_changed');
}
function summaryDomReady() {
 const visible=el=>el.getBoundingClientRect().height>0&&getComputedStyle(el).visibility!=='hidden';
 // Action-center/profile loaders are independent of the Ant table spinner.
 // The optional message-button spinner does not gate driver data readiness.
 if(Array.from(document.querySelectorAll('.ant-spin-spinning,.phx-loading-icon,loader.loading')).some(visible))return false;
 const safety=document.querySelector('.safety-score-card');
 return !safety?.querySelector('#score-trend-graph')||Array.from(safety.querySelectorAll('#score-trend-tooltip #score-text')).some(el=>visible(el)&&el.textContent.trim());
}
async function summary(context, identity, ranges) {
 const page=await context.newPage();page.setDefaultTimeout(15000);
 const href=`#/fleetview/drivers/summary/${identity.provider_driver_id}`;
 try {
  await page.goto(ORIGIN+'/en-US/'+href,{waitUntil:'domcontentloaded',timeout:45000});
  await page.locator('.safety-score-card:visible').waitFor({timeout:30000});
  // Breadcrumb identity loads independently of the summary cards and actions.
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('phx-breadcrumb [data-testid="breadcrumb-title"]')).some(el=>el.getBoundingClientRect().height>0&&el.textContent.trim()),{},{timeout:30000});
  let sectionsTimedOut=false;
  try {
   await page.waitForFunction(summaryDomReady,{},{timeout:30000});
  } catch(error) {
   if(error.name!=='TimeoutError')throw error;
   sectionsTimedOut=true;
  }
  const snapshot=await page.evaluate(()=>{
   const visible=el=>el.getBoundingClientRect().height>0;
   const leaves=Array.from(document.querySelectorAll('*')).filter(el=>el.children.length===0&&visible(el));
   function card(label,endLabel) {
    let el=leaves.find(el=>el.textContent.trim()===label);
    while(el&&!el.textContent.includes(endLabel))el=el.parentElement;
    return el;
   }
   function linesWithoutSvg(el) {
    if(!el)return [];
    const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),lines=[];
    for(let node=walker.nextNode();node;node=walker.nextNode())if(!node.parentElement.closest('svg')&&visible(node.parentElement)&&node.textContent.trim())lines.push(node.textContent.trim());
    return lines;
   }
   const safety=card('Safety Score','Top behaviors impacting score'),fuel=card('Fuel performance','Idle time');
   const table=Array.from(document.querySelectorAll('table')).find(t=>/BEHAVIOR\s*\/\s*SEVERITY/i.test(t.innerText));
   const breadcrumbs=Array.from(document.querySelectorAll('phx-breadcrumb')).filter(visible).map(breadcrumb=>Array.from(breadcrumb.querySelectorAll('phx-breadcrumb-item')).map(item=>{
    const label=item.querySelector('a.phx-breadcrumb-link,[data-testid="breadcrumb-title"]');
    return {text:label?.textContent??'',href:label?.getAttribute('href')??null};
   }));
   return {breadcrumbs,safety_lines:linesWithoutSvg(safety),safety_score_texts:safety?Array.from(safety.querySelectorAll('#score-trend-tooltip #score-text')).filter(visible).map(el=>el.textContent.trim()):[],coaching_annotation:safety?.textContent.includes('Coaching')??false,fuel_text:fuel?Array.from(fuel.querySelectorAll('*')).filter(el=>el.children.length===0&&visible(el)).map(el=>el.textContent.trim()).filter(Boolean).join(' '):'',coaching_text:Array.from(document.querySelectorAll('a[href*="/coaching/"]')).map(a=>a.innerText).filter(t=>t.includes('Driver needs coaching'))[0]??'',event_headers:table?Array.from(table.querySelectorAll('th')).map(x=>x.innerText):[],events:table?Array.from(table.querySelectorAll('tbody tr')).slice(0,100).map(tr=>Array.from(tr.querySelectorAll('td')).map(td=>td.innerText)):[]};
  });
  validateSummaryIdentity(page.url(),snapshot.breadcrumbs,identity);
  const result=parseSummary(snapshot,ranges);
  if(sectionsTimedOut)result.unavailable_reasons.push('Some summary sections did not finish loading.');
  return result;
 }finally{await page.close();}
}
async function collect(output) {
 const companyLabel=process.env.MOTIVE_COMPANY_LABEL,companyId=process.env.MOTIVE_COMPANY_ID;
 if(!companyLabel||!companyId||!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw new Error('missing_configuration');
 const {chromium}=require('../motive_sync/node_modules/playwright');
 const result={version:1,company_label:companyLabel,company_id:companyId,company_verified_before:false,company_verified_after:false,complete:false,started_at:new Date().toISOString(),finished_at:null,driver_directory_count:null,terminal_evidence:null,timezone_evidence:null,performance_ranges:[],drivers:[]};save(output,result);
 const browser=await chromium.launch({headless:true});
 try {
  const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US'});
  const page=await context.newPage();page.setDefaultTimeout(15000);
  await page.goto(ORIGIN,{waitUntil:'domcontentloaded',timeout:45000});await page.waitForURL('https://auth.gomotive.com/login**',{timeout:30000});
  if(new URL(page.url()).origin!=='https://auth.gomotive.com')throw new Error('login_origin');
  await page.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);await page.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);
  await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  async function company() {
   await page.goto(ORIGIN+'/en-US/#/admin/company',{waitUntil:'domcontentloaded'});await page.getByText(companyId,{exact:true}).waitFor({timeout:30000});
   const text=await page.locator('body').innerText();
   if(!text.split('\n').map(clean).includes(companyLabel)||!text.split('\n').map(clean).includes(companyId))throw new Error('company_mismatch');
  }
  async function ranges() {
   await page.goto(ORIGIN+RANGES,{waitUntil:'domcontentloaded'});await page.getByText('Each block represents a performance range and the scores that fall within it.',{exact:true}).waitFor({timeout:30000});
   return parseRanges(await page.locator('body').innerText());
  }
  await company();result.company_verified_before=true;
  await page.goto(ORIGIN+'/en-US/#/settings',{waitUntil:'domcontentloaded'});await page.getByText(/Eastern Time - New York/).waitFor({timeout:30000});
  result.timezone_evidence=await page.getByText('Time zone',{exact:true}).evaluate(el=>el.parentElement.innerText);
  if(!result.timezone_evidence.includes('Eastern Time - New York'))throw new Error('timezone_unverified');
  result.performance_ranges=await ranges();
  const before=await directory(context);result.driver_directory_count=before.rows.length;result.terminal_evidence=before.terminal_evidence;save(output,result);
  const vins=new Set();
  for(const identity of before.rows) {
   const row={...identity,vin:null,state:'unavailable',source_read_at:new Date().toISOString(),assignment_verified_before:true,assignment_verified_after:false};
   if(!identity.provider_vehicle_id)row.reason='driver_unassigned';
   else {
    const link={href:`#/fleetview/vehicles/summary/${identity.provider_vehicle_id}`,unit:identity.unit};
    row.vin=await readVehicleVin(context,link);
    if(!row.vin)row.reason='vin_unavailable';
    else {
     if(vins.has(row.vin))throw new Error('duplicate_vin');vins.add(row.vin);
     let content;
     try {content=await summary(context,identity,result.performance_ranges);}catch(error){if(error.message==='driver_identity_changed')throw error;content=emptyContent('Driver summary could not be read.');}
     const verifyVin=await readVehicleVin(context,link);if(row.vin!==verifyVin)throw new Error('vehicle_identity_changed');
     Object.assign(row,content,{state:'captured',source_read_at:new Date().toISOString()});
    }
   }
   result.drivers.push(row);save(output,result);
   console.log(JSON.stringify({stage:'driver_progress',attempted:result.drivers.length,total:before.rows.length}));
  }
  const after=await directory(context);
  const identityKey=rows=>JSON.stringify(rows.map(r=>[r.provider_driver_id,r.driver_name,r.provider_vehicle_id,r.unit]).sort());
  if(identityKey(before.rows)!==identityKey(after.rows))throw new Error('driver_directory_changed');
  if(JSON.stringify(result.performance_ranges)!==JSON.stringify(await ranges()))throw new Error('performance_ranges_changed');
  await company();result.company_verified_after=true;for(const row of result.drivers)row.assignment_verified_after=true;
  result.finished_at=new Date().toISOString();result.complete=true;save(output,result);return result;
 }finally{await browser.close();}
}
function safeReason(error) {
 const known=['missing_configuration','login_origin','company_mismatch','timezone_unverified','driver_directory_incomplete','driver_directory_layout','driver_identity_invalid','ambiguous_driver_assignment','driver_source_changed','driver_identity_changed','driver_directory_changed','vehicle_identity_changed','duplicate_vin','performance_ranges_unavailable','performance_ranges_invalid','performance_ranges_changed'];
 return known.includes(error?.message)?error.message:error?.name==='TimeoutError'?'ui_timeout':'driver_collection_failed';
}
if(require.main===module) {
 if(!process.argv[2]){console.error('Output file required');process.exitCode=1;}
 else collect(process.argv[2]).then(r=>console.log(JSON.stringify({stage:'driver_collection_complete',drivers:r.drivers.length}))).catch(e=>{console.error(JSON.stringify({stage:'driver_collection_failed',reason:safeReason(e),import_permitted:false}));process.exitCode=1;});
}
module.exports={collect,parseRanges,classify,directoryColumns,validateDirectory,validateSummaryIdentity,summaryDomReady,emptyContent,parseSummary,safeReason};
