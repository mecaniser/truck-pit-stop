const {prepareHealthLogin}=require('./login.cjs');
const {closeBrowser,phase,openTasks,failed,transient}=require('../motive_sync/tasks.cjs');
/* Rendered Motive Health UI only. No private endpoints or extracted sessions. */
const fs=require('node:fs');
const {readVehicleVin}=require('../motive_sync/collect_trips.cjs');
const ORIGIN='https://app.gomotive.com', COMPANY='77 CARGO LLC', COMPANY_ID='KT8934277';
const SCOPE='Current fault codes';
const {readReviewedPageIdentity,readReviewedIdentity,summarySnapshot,summaryIdentity,allowlist,isReviewed,sameIdentity,assertNoLiveVin}=require('../motive_sync/vehicle_identity.cjs');
function parseVitals(fields) {
 const value=(label,max,unit)=>{
  const matches=fields.filter(f=>String(f.label).trim().toLowerCase()===label);
  if(matches.length!==1)return null;
  const raw=String(matches[0].value).trim();
  const pattern=unit==='mi'?/^(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(mi|km)$/i:/^(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:\s*(?:h|hrs?|hours?))?$/i;
  const match=raw.match(pattern);if(!match)return null;
  let number=Number((match[1]+(match[2]||'')).replaceAll(',',''));
  if(unit==='mi'&&match[3].toLowerCase()==='km')number/=1.609344;
  return Number.isFinite(number)&&number>=0&&number<=max?number:null;
 };
 return {odometer_miles:value('odometer',100000000,'mi'),engine_hours:value('engine hours',10000000,'h')};
}
function liveVitals(snapshot,identity,vin) {
 const {assertLiveProvider}=require('../motive_sync/collect.cjs');
 try{assertLiveProvider(snapshot.url,identity.href.split('/').pop());}catch{throw new Error('vehicle_source_changed');}
 if(snapshot.table_count!==undefined&&snapshot.table_count!==1)throw new Error('vehicle_vitals_layout_changed');
 for(const label of ['ODOMETER','ENGINE HOURS'])if(snapshot.fields.filter(f=>f.label.trim().toUpperCase()===label).length>1)throw new Error('vehicle_vitals_layout_changed');
 const vins=snapshot.fields.filter(f=>f.label.trim().toUpperCase()==='VIN');
 if(vins.length!==1||vins[0].value.trim()!==vin)throw new Error('vehicle_identity_changed');
 return parseVitals(snapshot.fields);
}
function liveVitalsSnapshot() {
 const visible=el=>el.getClientRects().length>0&&getComputedStyle(el).visibility!=='hidden';
 const tables=Array.from(document.querySelectorAll('table.detail-table')).filter(visible).filter(table=>Array.from(table.querySelectorAll('tr')).some(row=>row.querySelector('td')?.textContent.trim().toUpperCase()==='VIN'));
 const fields=tables.length===1?Array.from(tables[0].querySelectorAll('tr')).filter(visible).flatMap(row=>{
  const cells=row.querySelectorAll(':scope > td');
  return cells.length===2?[{label:cells[0].textContent.trim(),value:cells[1].textContent.trim()}]:[];
 }):[];
 return {url:location.href,fields,table_count:tables.length};
}
async function assertNoSourceAuthentication(page) {
 // Read only presence and attributes; never inspect credential/challenge values.
 const controls=await page.locator('input:visible,textarea:visible,select:visible').evaluateAll(elements=>elements.map(element=>({type:element.getAttribute('type')||'',name:element.getAttribute('name')||'',autocomplete:element.getAttribute('autocomplete')||''})));
 if(controls.some(control=>control.type.toLowerCase()==='password'||control.autocomplete.toLowerCase().split(/\s+/).includes('one-time-code')||/^(?:otp|totp|verification[-_]?code)$/i.test(control.name)))throw new Error('source_authentication_required');
 const frames=await page.locator('iframe:visible').evaluateAll(elements=>elements.flatMap(element=>{
  try{const url=new URL(element.src);return [{origin:url.origin,pathname:url.pathname,credentialed:!!(url.username||url.password)}];}catch{return [];}
 }));
 for(const url of frames){
  if(url.credentialed)continue;
  const recaptcha=['https://www.google.com','https://www.recaptcha.net','https://recaptcha.google.com'].includes(url.origin)&&url.pathname.startsWith('/recaptcha/');
  const hcaptcha=['https://hcaptcha.com','https://newassets.hcaptcha.com'].includes(url.origin)&&url.pathname.startsWith('/captcha/');
  const cloudflare=url.origin==='https://challenges.cloudflare.com'&&url.pathname.startsWith('/cdn-cgi/challenge-platform/');
  if(recaptcha||hcaptcha||cloudflare)throw new Error('source_authentication_required');
 }
}
async function readVitals(context,identity,vin,{timeoutMs=90000,liveTimeoutMs=15000}={}) {
 if(!Number.isFinite(timeoutMs)||timeoutMs<=0||timeoutMs>90000||!Number.isFinite(liveTimeoutMs)||liveTimeoutMs<=0||liveTimeoutMs>15000)throw new Error('vehicle_vitals_budget_invalid');
 const {performance}=require('node:perf_hooks');
 const {assertLiveProvider}=require('../motive_sync/collect.cjs');
 const deadline=performance.now()+timeoutMs,provider=identity.href.split('/').pop();
 let summary,expectedLive,exhausted=false;
 const timeout=()=>Object.assign(new Error('vehicle_vitals_timeout'),{name:'TimeoutError'});
 const remaining=()=>{const ms=deadline-performance.now();if(exhausted||ms<=0)throw timeout();return ms;};
 const dispose=page=>{try{return Promise.resolve(page.close()).catch(()=>{});}catch{return Promise.resolve();}};
 async function budget(operation,latePage=false){
  const ms=remaining();let timer,expired=false;
  const pending=Promise.resolve().then(operation);
  pending.then(page=>{if(expired&&latePage)dispose(page);},()=>{});
  try{
   const value=await Promise.race([pending,new Promise((_,reject)=>{timer=setTimeout(()=>{expired=true;exhausted=true;reject(timeout());},ms);})]);
   try{remaining();}catch(error){if(latePage)dispose(value);throw error;}return value;
  }finally{clearTimeout(timer);}
 }
 function source(page,navigating,allowSummary=true){
  const url=new URL(page.url());
  if(navigating&&url.href==='about:blank')return 'loading';
  if(url.origin!==ORIGIN)throw new Error('session_lost');
  if(url.username||url.password||url.pathname!=='/en-US/'||url.search)throw new Error('vehicle_source_changed');
  if(url.hash===identity.href){if(!allowSummary)throw new Error('vehicle_source_changed');return 'summary';}
  try{assertLiveProvider(url.href,provider);}catch{throw new Error('vehicle_source_changed');}
  if(!expectedLive||url.href!==expectedLive)throw new Error('vehicle_source_changed');
  return 'live';
 }
 function liveIdentityReady(snapshot){
  if(snapshot.table_count>1)throw new Error('vehicle_vitals_layout_changed');
  for(const label of ['ODOMETER','ENGINE HOURS'])if(snapshot.fields.filter(field=>field.label.trim().toUpperCase()===label).length>1)throw new Error('vehicle_vitals_layout_changed');
  const vins=snapshot.fields.filter(field=>field.label.trim().toUpperCase()==='VIN');
  if(vins.length>1)throw new Error('vehicle_identity_changed');
  if(!vins.length)return false;
  const value=vins[0].value.trim();
  if(value&&value!==vin)throw new Error('vehicle_identity_changed');
  return value===vin;
 }
 for(let attempt=0;attempt<2;attempt++){
  let page,navigating=true,liveStarted=false,liveReached=false;
  try{
   page=await budget(()=>context.newPage(),true);page.setDefaultTimeout(Math.min(liveTimeoutMs,remaining()));
   await budget(()=>page.goto(ORIGIN+'/en-US/'+identity.href,{waitUntil:'domcontentloaded',timeout:Math.min(45000,remaining())}));navigating=false;
   phase('health_vitals_summary');
   const before=await budget(()=>readReviewedPageIdentity(page,identity));
   if(before.vin!==vin)throw new Error('vehicle_identity_changed');
   const summaryEvidence=await budget(()=>page.evaluate(summarySnapshot));
   sameIdentity(before,summaryIdentity(summaryEvidence,identity));
   const fields=summaryEvidence.fields;
   const after=await budget(()=>readReviewedPageIdentity(page,identity));
   if(after.vin!==vin)throw new Error('vehicle_identity_changed');
   summary={...parseVitals(fields),source_read_at:new Date().toISOString()};
   expectedLive=new URL(summaryEvidence.live_links[0],ORIGIN+'/en-US/').href;
   // A fresh page retries only transient rendered reads in this same session.
   await budget(()=>assertNoSourceAuthentication(page));
   liveStarted=true;
   await budget(()=>page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().click({timeout:Math.min(liveTimeoutMs,remaining())}));
   phase('health_vitals_live_readiness');
   const readyDeadline=performance.now()+Math.min(liveTimeoutMs,remaining());
   for(;;){
    const state=source(page,false,!liveReached);
    await budget(()=>assertNoSourceAuthentication(page));
    if(state==='live'){
     liveReached=true;
     const snapshot=await budget(()=>page.evaluate(liveVitalsSnapshot));
     if(snapshot.url!==expectedLive)throw new Error('vehicle_source_changed');
     const ready=liveIdentityReady(snapshot);
     if(ready&&snapshot.fields.some(field=>field.label.trim().toUpperCase()==='ENGINE HOURS')){
      const values=liveVitals(snapshot,identity,vin);
      await budget(()=>assertNoSourceAuthentication(page));
      source(page,false,false);remaining();
      if(values.odometer_miles===null&&values.engine_hours===null)return summary;
      return {...values,source_read_at:new Date().toISOString()};
     }
    }
    const liveRemaining=readyDeadline-performance.now();
    if(liveRemaining<=0)throw Object.assign(new Error('vehicle_live_readiness_timeout'),{name:'TimeoutError'});
    await budget(()=>page.waitForTimeout(Math.min(25,liveRemaining,remaining())));
   }
  }catch(error){
   if(page){source(page,navigating,!liveReached);if(!navigating&&!exhausted&&deadline>performance.now())await budget(()=>assertNoSourceAuthentication(page));}
   if(!transient(error)||attempt===0&&!liveStarted)throw error;
   remaining();
   // A timed-out wait can leave newly rendered contradictory identity behind.
   if(page&&new URL(page.url()).origin===ORIGIN&&new URL(page.url()).hash!==identity.href){
    const latest=await budget(()=>page.evaluate(liveVitalsSnapshot));
    liveIdentityReady(latest);
   }
   if(attempt===1){if(summary)return summary;throw error;}
  }finally{
   if(page){if(!exhausted&&deadline>performance.now())await budget(()=>page.close());else dispose(page);}
  }
 }
}
function boundLiveVitals(snapshot,identity,proof) {
 const {assertLiveProvider}=require('../motive_sync/collect.cjs');
 try{assertLiveProvider(snapshot.url,identity.href.split('/').pop());}catch{throw new Error('vehicle_source_changed');}
 if(proof.vin!==null||!['not_displayed','explicitly_empty'].includes(proof.source_vin_state))throw new Error('vehicle_identity_changed');
 const vins=snapshot.vin_fields??snapshot.fields.filter(f=>f.label.trim().toUpperCase()==='VIN');
 if(vins.length>1||vins.some(f=>f.value.trim()&&!/^(?:—|–|--|N\/A)$/i.test(f.value.trim())))throw new Error('vehicle_identity_changed');
 for(const label of ['ODOMETER','ENGINE HOURS'])if(snapshot.fields.filter(f=>f.label.trim().toUpperCase()===label).length!==1)throw new Error('vehicle_vitals_layout_changed');
 return parseVitals(snapshot.fields);
}
// Grounded Nov4 authenticated truck26 Live DOM. Unlike VIN-based Live tables,
// this reviewed provider profile has ODOMETER/ENGINE HOURS but no VIN row.
function boundLiveVitalsSnapshot() {
 const visible=el=>el.getClientRects().length>0&&getComputedStyle(el).visibility!=='hidden';
 const tables=Array.from(document.querySelectorAll('table.detail-table')).filter(visible);
 const rows=table=>Array.from(table.querySelectorAll('tr')).flatMap(row=>{
  const cells=row.querySelectorAll(':scope > td');
  if(cells.length!==2)return [];
  const field={label:cells[0].textContent.trim(),value:cells[1].textContent.trim()};
  return visible(row)||(field.label.toUpperCase()==='VIN'&&field.value)?[field]:[];
 });
 const candidates=tables.map(rows).filter(fields=>['ODOMETER','ENGINE HOURS'].every(label=>fields.filter(f=>f.label.toUpperCase()===label).length===1));
 return {url:location.href,fields:candidates.length===1?candidates[0]:[],vin_fields:tables.flatMap(rows).filter(f=>f.label.toUpperCase()==='VIN')};
}
async function readBoundVitals(context,identity,proof) {
 const page=await context.newPage();page.setDefaultTimeout(15000);
 let summary={odometer_miles:null,engine_hours:null,source_read_at:new Date().toISOString()},candidate;
 try {
  await page.goto(ORIGIN+'/en-US/'+identity.href,{waitUntil:'domcontentloaded',timeout:45000});
  const before=await readReviewedPageIdentity(page,identity);sameIdentity(proof,before);
  if(before.vin!==null)throw new Error('vehicle_identity_changed');
  const summaryEvidence=await page.evaluate(summarySnapshot);
  sameIdentity(before,summaryIdentity(summaryEvidence,identity));
  summary={...parseVitals(summaryEvidence.fields),source_read_at:new Date().toISOString()};
  try {
   await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().click();
   await page.locator('table.detail-table').filter({visible:true}).first().waitFor();
   await page.getByText('ENGINE HOURS',{exact:true}).filter({visible:true}).first().waitFor();
   assertNoLiveVin(await page.locator('body').innerText());
   candidate={...boundLiveVitals(await page.evaluate(boundLiveVitalsSnapshot),identity,before),source_read_at:new Date().toISOString()};
  }catch(error) {
   if(['vehicle_identity_changed','vin_changed','vehicle_source_changed','ambiguous_vin','vehicle_identity_unavailable'].includes(error.message))throw error;
   if(new URL(page.url()).origin!==ORIGIN)throw new Error('session_lost');
   candidate=summary;
  }
  // A loaded fresh summary after Live independently proves continuing absence.
  sameIdentity(before,await readReviewedIdentity(context,identity));
  if(candidate.odometer_miles===null&&candidate.engine_hours===null)return summary;
  return candidate;
 }finally{await page.close();}
}
const HEADERS=['vehicle or asset','availability','defects','fault codes','next service','',''];
function parseCount(text) {
 if(!/^\d+$/.test(text.trim()))throw new Error('count_unavailable');
 const value=Number(text.trim());if(!Number.isSafeInteger(value)||value>1000)throw new Error('count_invalid');return value;
}
function parseCard(text,expandedCount) {
 const lines=text.split('\n').map(s=>s.trim()).filter(Boolean);
 if(lines[0]!==SCOPE)throw new Error('card_scope_invalid');
 if(lines.length===2&&lines[1]==='No fault codes') {
  if(expandedCount!==0)throw new Error('empty_contradiction');
  return {explicit_empty:true,codes:[]};
 }
 if(lines.includes('Show details')||lines.includes('No fault codes'))throw new Error('details_unavailable');
 const starts=lines.flatMap((line,index)=>/^(?:SPN|SID|PID) \d+ FMI \d+\s*·/.test(line)?[index]:[]);
 if(!starts.length||starts.length!==expandedCount||lines.filter(x=>x==='Hide details').length!==starts.length)throw new Error('details_unavailable');
 const codes=starts.map((start,i)=>{
  const part=lines.slice(start,starts[i+1]??lines.length);
  const match=part[0].match(/^(SPN|SID|PID) (\d+) FMI (\d+)\s*·\s*(.+)$/);
  const hide=part.indexOf('Hide details');
  if(!match||hide<2)throw new Error('code_layout_changed');
  const labels=new Set(['Network','Source address','First detected','Last observed','Occurrence count','Hide details','Show details']);
  function field(label) {
   const positions=part.flatMap((v,n)=>v===label?[n]:[]);if(positions.length>1)throw new Error('code_layout_changed');
   const value=positions.length?part[positions[0]+1]??null:null;
   return value===null||labels.has(value)||value==='—'?null:value;
  }
  const occurrences=field('Occurrence count');
  if(occurrences!==null&&occurrences!=='—'&&!/^\d+$/.test(occurrences))throw new Error('occurrence_invalid');
  const occurrence_count=occurrences===null||occurrences==='—'?null:Number(occurrences);
  if(occurrence_count!==null&&!Number.isSafeInteger(occurrence_count))throw new Error('occurrence_invalid');
  const first=field('First detected'),last=field('Last observed');
  return {code:match[1]==='SPN'?null:`${match[1]} ${match[2]}`,spn:match[1]==='SPN'?match[2]:null,fmi:match[3],description:match[4],severity:part[hide-1].startsWith('First detected on ')?null:part[hide-1],network:field('Network'),source_address:field('Source address'),source_status:SCOPE,provider_fault_id:null,occurrence_count,first_detected_text:first,last_observed_text:last,first_detected_at:null,last_observed_at:null,timestamp_precision:'unknown',timezone_basis:'unverified'};
 });
 const identities=codes.map(c=>JSON.stringify([c.code,c.spn,c.fmi,c.network,c.source_address]));
 if(new Set(identities).size!==codes.length)throw new Error('duplicate_code');
 return {explicit_empty:false,codes};
}
function validateCounts(before,after,parsed) {
 if(before!==after||before!==parsed.codes.length||(before===0)!==parsed.explicit_empty)throw new Error('count_mismatch');
 return parsed;
}
function validateInventory(snapshot,priorTotal=null) {
 const clean=s=>s.replace(/\s+/g,' ').trim().toLowerCase();
 if(JSON.stringify(snapshot.headers.map(clean))!==JSON.stringify(HEADERS))throw new Error('health_layout_changed');
 const total=snapshot.footer?.match(/^Showing ([\d,]+) of ([\d,]+)$/);
 if(!total)throw new Error('health_count_unavailable');
 const shown=Number(total[1].replaceAll(',','')),expected=Number(total[2].replaceAll(',',''));
 if(expected>250||expected<1||shown>expected||priorTotal!==null&&priorTotal!==expected)throw new Error('health_directory_changed');
 const found=new Map();
 for(const row of snapshot.rows) {
  if(!/^#\/fleetview\/vehicles\/summary\/\d+$/.test(row.href)||!row.unit)throw new Error('health_identity_invalid');
  if(found.has(row.href))throw new Error('duplicate_provider');found.set(row.href,row);
  parseCount(row.count);
 }
 if(snapshot.rows.length>expected)throw new Error('health_directory_changed');
 return {shown,expected};
}
async function healthPage(context) {
 const page=await context.newPage();page.setDefaultTimeout(15000);
 try {
  await page.goto(ORIGIN+'/en-US/#/maintenance/health',{waitUntil:'domcontentloaded',timeout:45000});
  await page.getByText(/Showing [\d,]+ of [\d,]+/).waitFor({timeout:30000});
  return page;
 }catch(error){await page.close();throw error;}
}
async function inventory(page) {
 const seen=new Map();let expected=null,lastFooter=null;
 for(let step=0;step<120;step++) {
  if(page.url()!==ORIGIN+'/en-US/#/maintenance/health')throw new Error('health_source_changed');
  const snapshot=await page.evaluate(()=>{
   const table=Array.from(document.querySelectorAll('table')).find(t=>Array.from(t.querySelectorAll('th')).some(h=>h.innerText.trim().toLowerCase()==='vehicle or asset'));
   if(!table)return {headers:[],rows:[],footer:null};
   const rows=Array.from(table.querySelectorAll('tbody tr')).flatMap(tr=>{
    const links=Array.from(tr.querySelectorAll('a[href*="/fleetview/vehicles/summary/"]'));
    if(!links.length)return [];if(links.length!==1)throw new Error('health_identity_invalid');
    const cells=tr.querySelectorAll('td');return [{href:links[0].getAttribute('href'),unit:links[0].innerText.trim(),count:cells[3]?.innerText.trim()??''}];
   });
   return {headers:Array.from(table.querySelectorAll('th')).map(h=>h.innerText.trim()),rows,footer:document.body.innerText.match(/Showing [\d,]+ of [\d,]+/)?.[0]??null};
  });
  const counts=validateInventory(snapshot,expected);expected=counts.expected;lastFooter=snapshot.footer;
  for(const row of snapshot.rows) {
   if(seen.has(row.href)&&seen.get(row.href).unit!==row.unit)throw new Error('health_identity_changed');seen.set(row.href,row);
  }
  if(counts.shown===expected&&seen.size===expected)return {rows:[...seen.values()],count:expected,terminal_evidence:lastFooter};
  await page.evaluate(()=>{
   const table=Array.from(document.querySelectorAll('table')).find(t=>Array.from(t.querySelectorAll('th')).some(h=>h.innerText.trim().toLowerCase()==='vehicle or asset'));
   let viewport=table?.parentElement;
   while(viewport&&!(viewport.clientHeight>0&&/(auto|scroll)/.test(getComputedStyle(viewport).overflowY)))viewport=viewport.parentElement;
   if(!viewport)throw new Error('health_pagination_unavailable');viewport.scrollTop+=Math.max(300,viewport.clientHeight-60);
  });
  await page.waitForTimeout(750);
 }
 throw new Error('health_directory_incomplete');
}
async function vehicleCodes(context,identity) {
 let lastReason='health_data_unavailable';
 for(let attempt=0;attempt<2;attempt++) {
  const page=await healthPage(context);
  try {
   const row=page.locator('tr').filter({has:page.locator(`a[href="${identity.href}"]`)});
   if(await row.count()!==1)throw new Error('health_row_missing');
   const before=parseCount(await row.locator('td').nth(3).innerText());
   await row.locator('td').nth(3).click();
   const card=page.locator('[data-testid="section-fault-codes"]');await card.waitFor();
   await card.getByText(SCOPE,{exact:true}).waitFor();
   if(before===0)await card.getByText('No fault codes',{exact:true}).waitFor();
   else await card.locator('.phx-collapse-item-header').first().waitFor();
   const details=card.locator('.phx-collapse-item-header');
   const detailCount=await details.count();
   if(detailCount>1000)throw new Error('code_limit');
   for(let i=0;i<detailCount;i++) {
    const detail=details.nth(i);const label=(await detail.innerText()).trim();
    if(label==='Show details')await detail.click();else if(label!=='Hide details')throw new Error('details_unavailable');
    await detail.getByText('Hide details',{exact:true}).waitFor();
   }
   await page.waitForFunction(()=>Array.from(document.querySelectorAll('[data-testid="section-fault-codes"] .phx-collapse-item-content')).every(el=>el.getBoundingClientRect().height>0));
   const parsed=parseCard(await card.innerText(),detailCount);
   const after=parseCount(await row.locator('td').nth(3).innerText());validateCounts(before,after,parsed);
   // A fresh report read catches count changes hidden behind a stale drawer table.
   const verify=await healthPage(context);
   try {
    const current=verify.locator('tr').filter({has:verify.locator(`a[href="${identity.href}"]`)});
    if(await current.count()!==1)throw new Error('health_row_missing');
    validateCounts(before,parseCount(await current.locator('td').nth(3).innerText()),parsed);
   }finally{await verify.close();}
   return {state:'captured',count_before:before,count_after:after,...parsed};
  }catch(error) {
   if(new URL(page.url()).origin!==ORIGIN)throw new Error('session_lost');lastReason=safeReason(error);
  }finally{await page.close();}
 }
 return {state:'unavailable',count_before:null,count_after:null,explicit_empty:false,codes:[],reason:lastReason};
}
function save(output,value){const tmp=output+'.tmp';fs.writeFileSync(tmp,JSON.stringify(value,null,2),{mode:0o600});fs.chmodSync(tmp,0o600);fs.renameSync(tmp,output);}
async function collect(output) {
 if(!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw new Error('missing_credentials');
 const {chromium}=require('../motive_sync/node_modules/playwright');
 phase('browser_launch');
 const browser=await chromium.launch({headless:true});
 const result={version:1,company_label:COMPANY,company_id:COMPANY_ID,company_verified_before:false,company_verified_after:false,timezone_evidence:null,started_at:new Date().toISOString(),finished_at:null,health_directory_count:null,terminal_evidence:null,complete:false,vehicles:[]};save(output,result);
 try {
  const {context,page,authenticated}=await prepareHealthLogin(browser,{phase,lookupEmail:process.env.MOTIVE_EMAIL,lookupPassword:process.env.MOTIVE_PASSWORD});
  if(!authenticated){
  phase('login_email');
  await page.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);phase('login_password');
  await page.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);
  phase('login_submit');
  await page.getByRole('button',{name:'Log in',exact:true}).click();phase('login_app_redirect');
  await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  }
  async function company(){const p=await context.newPage();try{await p.goto(ORIGIN+'/en-US/#/admin/company',{waitUntil:'domcontentloaded'});await p.getByText(/KT8934277/).waitFor({timeout:30000});const text=await p.locator('body').innerText();if(!text.includes(COMPANY)||!text.includes(COMPANY_ID))throw new Error('company_mismatch');}finally{await p.close();}}
  phase('company_before');
  await company();result.company_verified_before=true;save(output,result);
  phase('timezone');
  await page.goto(ORIGIN+'/en-US/#/settings',{waitUntil:'domcontentloaded'});await page.getByText(/Eastern Time - New York/).waitFor({timeout:30000});result.timezone_evidence=await page.getByText('Time zone',{exact:true}).evaluate(el=>el.parentElement.innerText);
  if(!result.timezone_evidence.includes('Eastern Time - New York'))throw new Error('timezone_unverified');
  const listPage=await healthPage(context);let directory;
  try{directory=await inventory(listPage);}finally{await listPage.close();}
  result.health_directory_count=directory.count;result.terminal_evidence=directory.terminal_evidence;save(output,result);
  const tasks=openTasks(output,{kind:'health',company:COMPANY_ID,timezone:'America/New_York',directory:directory.rows},{maxAgeMs:30*60*1000});result.started_at=tasks.startedAt;
  const vins=new Set(),reviewed=allowlist();
  for(const identity of directory.rows) {
   const provider=identity.href.split('/').pop(),boundReviewed=isReviewed(reviewed,COMPANY_ID,provider);
   const proof=boundReviewed?await readReviewedIdentity(context,identity):{vin:await readVehicleVin(context,identity)};
   const vin=proof.vin;if(vin&&vins.has(vin))throw new Error('duplicate_vin');if(vin)vins.add(vin);
   const vitals=vin?await readVitals(context,identity,vin):boundReviewed?await readBoundVitals(context,identity,proof):null;
   const observation=vin?await tasks.run('health_vehicle',[identity.href,vin],async()=>({...(await vehicleCodes(context,identity)),source_read_at:new Date().toISOString()}),{cacheable:row=>row.state==='captured'}):{state:'unavailable',count_before:null,count_after:null,explicit_empty:false,codes:[],reason:'vin_unavailable'};
   result.vehicles.push({provider_vehicle_id:provider,unit:identity.unit,vin,...(!vin&&boundReviewed?{source_vin_state:proof.source_vin_state}:{}),source_read_at:new Date().toISOString(),source_scope:SCOPE,...observation,vitals});save(output,result);
   console.log(JSON.stringify({stage:'health_progress',attempted:result.vehicles.length,total:directory.count}));
  }
  tasks.assertFresh();phase('health_directory_after');
  const checkPage=await healthPage(context);let finalDirectory;
  try{finalDirectory=await inventory(checkPage);}finally{await checkPage.close();}
  if(JSON.stringify(finalDirectory.rows.map(r=>[r.href,r.unit]).sort())!==JSON.stringify(directory.rows.map(r=>[r.href,r.unit]).sort()))throw new Error('health_directory_changed');
  tasks.assertFresh();
  phase('company_after');
  await company();tasks.assertFresh();result.company_verified_after=true;result.complete=true;result.finished_at=new Date().toISOString();save(output,result);return result;
 }finally{await closeBrowser(browser);}
}
function safeReason(error) {
 const known=['count_unavailable','count_invalid','card_scope_invalid','empty_contradiction','details_unavailable','code_layout_changed','occurrence_invalid','duplicate_code','count_mismatch','health_layout_changed','health_count_unavailable','health_directory_changed','health_identity_invalid','duplicate_provider','health_source_changed','health_identity_changed','health_pagination_unavailable','health_directory_incomplete','health_row_missing','code_limit','session_lost','missing_credentials','login_origin','company_mismatch','timezone_unverified','duplicate_vin','vehicle_identity_changed','vehicle_source_changed','vehicle_vitals_layout_changed','source_authentication_required','vehicle_vitals_budget_invalid','vehicle_vitals_timeout','vehicle_live_readiness_timeout','vin_changed','ambiguous_vin','vehicle_identity_unavailable'];
 return known.includes(error?.message)?error.message:error?.name==='TimeoutError'?'ui_timeout':'health_data_unavailable';
}
if(require.main===module){if(!process.argv[2]){console.error('Output file required');process.exitCode=1;}else collect(process.argv[2]).then(r=>console.log(JSON.stringify({stage:'health_collection_complete',complete:r.complete,vehicles:r.vehicles.length}))).catch(error=>{failed(process.argv[2],error);console.error(JSON.stringify({stage:'health_collection_failed',reason:safeReason(error),import_permitted:false}));process.exitCode=1;});}
module.exports={parseVitals,liveVitals,liveVitalsSnapshot,readVitals,boundLiveVitals,boundLiveVitalsSnapshot,readBoundVitals,collect,parseCount,parseCard,validateCounts,validateInventory,vehicleCodes,safeReason};
