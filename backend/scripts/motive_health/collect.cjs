/* Rendered Motive Health UI only. No private endpoints or extracted sessions. */
const fs=require('node:fs');
const {readVehicleVin}=require('../motive_sync/collect_trips.cjs');
const ORIGIN='https://app.gomotive.com', COMPANY='77 CARGO LLC', COMPANY_ID='KT8934277';
const SCOPE='Current fault codes';
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
 const starts=lines.flatMap((line,index)=>/^SPN \d+ FMI \d+\s*·/.test(line)?[index]:[]);
 if(!starts.length||starts.length!==expandedCount||lines.filter(x=>x==='Hide details').length!==starts.length)throw new Error('details_unavailable');
 const codes=starts.map((start,i)=>{
  const part=lines.slice(start,starts[i+1]??lines.length);
  const match=part[0].match(/^SPN (\d+) FMI (\d+)\s*·\s*(.+)$/);
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
  return {code:null,spn:match[1],fmi:match[2],description:match[3],severity:part[hide-1].startsWith('First detected on ')?null:part[hide-1],network:field('Network'),source_address:field('Source address'),source_status:SCOPE,provider_fault_id:null,occurrence_count,first_detected_text:first,last_observed_text:last,first_detected_at:null,last_observed_at:null,timestamp_precision:'unknown',timezone_basis:'unverified'};
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
 const browser=await chromium.launch({headless:true});
 const result={version:1,company_label:COMPANY,company_id:COMPANY_ID,company_verified_before:false,company_verified_after:false,timezone_evidence:null,started_at:new Date().toISOString(),finished_at:null,health_directory_count:null,terminal_evidence:null,complete:false,vehicles:[]};save(output,result);
 try {
  const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US'});
  const page=await context.newPage();page.setDefaultTimeout(15000);
  await page.goto(ORIGIN,{waitUntil:'domcontentloaded',timeout:45000});await page.waitForURL('https://auth.gomotive.com/login**',{timeout:30000});
  if(new URL(page.url()).origin!=='https://auth.gomotive.com')throw new Error('login_origin');
  await page.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);await page.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);
  await page.getByRole('button',{name:'Log in',exact:true}).click();await page.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  async function company(){const p=await context.newPage();try{await p.goto(ORIGIN+'/en-US/#/admin/company',{waitUntil:'domcontentloaded'});await p.getByText(/KT8934277/).waitFor({timeout:30000});const text=await p.locator('body').innerText();if(!text.includes(COMPANY)||!text.includes(COMPANY_ID))throw new Error('company_mismatch');}finally{await p.close();}}
  await company();result.company_verified_before=true;save(output,result);
  await page.goto(ORIGIN+'/en-US/#/settings',{waitUntil:'domcontentloaded'});await page.getByText(/Eastern Time - New York/).waitFor({timeout:30000});result.timezone_evidence=await page.getByText('Time zone',{exact:true}).evaluate(el=>el.parentElement.innerText);
  if(!result.timezone_evidence.includes('Eastern Time - New York'))throw new Error('timezone_unverified');
  const listPage=await healthPage(context);let directory;
  try{directory=await inventory(listPage);}finally{await listPage.close();}
  result.health_directory_count=directory.count;result.terminal_evidence=directory.terminal_evidence;save(output,result);
  const vins=new Set();
  for(const identity of directory.rows) {
   const vin=await readVehicleVin(context,identity);if(vin&&vins.has(vin))throw new Error('duplicate_vin');if(vin)vins.add(vin);
   const observation=vin?await vehicleCodes(context,identity):{state:'unavailable',count_before:null,count_after:null,explicit_empty:false,codes:[],reason:'vin_unavailable'};
   result.vehicles.push({provider_vehicle_id:identity.href.split('/').pop(),unit:identity.unit,vin,source_read_at:new Date().toISOString(),source_scope:SCOPE,...observation});save(output,result);
   console.log(JSON.stringify({stage:'health_progress',attempted:result.vehicles.length,total:directory.count}));
  }
  const checkPage=await healthPage(context);let finalDirectory;
  try{finalDirectory=await inventory(checkPage);}finally{await checkPage.close();}
  if(JSON.stringify(finalDirectory.rows.map(r=>[r.href,r.unit]).sort())!==JSON.stringify(directory.rows.map(r=>[r.href,r.unit]).sort()))throw new Error('health_directory_changed');
  await company();result.company_verified_after=true;result.complete=true;result.finished_at=new Date().toISOString();save(output,result);return result;
 }finally{await browser.close();}
}
function safeReason(error) {
 const known=['count_unavailable','count_invalid','card_scope_invalid','empty_contradiction','details_unavailable','code_layout_changed','occurrence_invalid','duplicate_code','count_mismatch','health_layout_changed','health_count_unavailable','health_directory_changed','health_identity_invalid','duplicate_provider','health_source_changed','health_identity_changed','health_pagination_unavailable','health_directory_incomplete','health_row_missing','code_limit','session_lost','missing_credentials','login_origin','company_mismatch','timezone_unverified','duplicate_vin'];
 return known.includes(error?.message)?error.message:error?.name==='TimeoutError'?'ui_timeout':'health_data_unavailable';
}
if(require.main===module){if(!process.argv[2]){console.error('Output file required');process.exitCode=1;}else collect(process.argv[2]).then(r=>console.log(JSON.stringify({stage:'health_collection_complete',complete:r.complete,vehicles:r.vehicles.length}))).catch(error=>{console.error(JSON.stringify({stage:'health_collection_failed',reason:safeReason(error),import_permitted:false}));process.exitCode=1;});}
module.exports={collect,parseCount,parseCard,validateCounts,validateInventory,vehicleCodes,safeReason};
