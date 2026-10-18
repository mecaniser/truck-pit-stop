/* Reviewed provider binding permits honest VIN-not-displayed evidence, never a fabricated VIN. */
const ORIGIN='https://app.gomotive.com';
const ALLOWLIST='MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST';
const clean=value=>String(value??'').replace(/\s+/g,' ').trim();
function allowlist(raw=process.env[ALLOWLIST]||'[]'){
 const entries=JSON.parse(raw);
 if(!Array.isArray(entries)||entries.length>50)throw new Error('invalid_vehicle_allowlist');
 const seen=new Set();
 for(const entry of entries){
  if(!entry||Object.keys(entry).sort().join(',')!=='company_id,provider_vehicle_id'||typeof entry.company_id!=='string'||!/^KT\d{1,118}$/.test(entry.company_id)||typeof entry.provider_vehicle_id!=='string'||!/^\d{1,120}$/.test(entry.provider_vehicle_id))throw new Error('invalid_vehicle_allowlist');
  const key=entry.company_id+':'+entry.provider_vehicle_id;if(seen.has(key))throw new Error('invalid_vehicle_allowlist');seen.add(key);
 }
 return seen;
}
function isReviewed(entries,companyId,providerId){return entries.has(companyId+':'+providerId);}
function sourceIdentity(text){
 const values=[...new Set(Array.from(text.matchAll(/\bVIN\s*[:\t ]*\s*([A-HJ-NPR-Z0-9]{17})\b/g),m=>m[1]))];
 if(values.length>1)throw new Error('ambiguous_vin');
 if(values.length===1)return {vin:values[0],source_vin_state:null};
 if(/(?:^|\n)\s*VIN\s*[:\t ]*\s*(?:—|–|--|N\/A)\s*(?:\n|$)/i.test(text))return {vin:null,source_vin_state:'explicitly_empty'};
 throw new Error('vehicle_identity_unavailable');
}
function summaryIdentity(snapshot,link){
 const match=link.href.match(/^#\/fleetview\/vehicles\/summary\/(\d+)$/);
 let url;try{url=new URL(snapshot.url);}catch{throw new Error('vehicle_source_changed');}
 if(!match||url.origin!==ORIGIN||url.hash!==link.href)throw new Error('vehicle_source_changed');
 if(!Array.isArray(snapshot.units)||snapshot.units.length===0)throw new Error('vehicle_overview_not_ready');
 if(snapshot.units.length!==1||clean(snapshot.units[0])!==clean(link.unit))throw new Error('vehicle_identity_changed');
 if(!Array.isArray(snapshot.breadcrumbs)||snapshot.breadcrumbs.length===0)throw new Error('vehicle_overview_not_ready');
 // The profile and exact Live route can load before Angular fills this node.
 // Wait only for one blank title; contradictory or duplicate titles still fail.
 if(snapshot.breadcrumbs.length===1&&!clean(snapshot.breadcrumbs[0]))throw new Error('vehicle_overview_not_ready');
 if(snapshot.breadcrumbs.length!==1||!(clean(snapshot.breadcrumbs[0])===clean(link.unit)||(clean(snapshot.breadcrumbs[0]).startsWith(clean(link.unit)+' (')&&clean(snapshot.breadcrumbs[0]).endsWith(')'))))throw new Error('vehicle_identity_changed');
 if(!Array.isArray(snapshot.live_links)||snapshot.live_links.length!==1)throw new Error('vehicle_source_changed');
 const live=new URL(snapshot.live_links[0],ORIGIN+'/en-US/');
 const liveMatch=live.hash.match(/^#\/fleetview\/map\/vehicle\/([^/]+)\/(\d+)\/live$/);
 if(live.origin!==ORIGIN||!liveMatch||liveMatch[2]!==match[1]||!liveMatch[1].startsWith(match[1]+'-'))throw new Error('vehicle_source_changed');
 if(snapshot.loading!==false||!Array.isArray(snapshot.fields))throw new Error('vehicle_overview_not_ready');
 const required=['fuel type','regulated','availability','groups','data source','odometer'];
 for(const label of required){
  const fields=snapshot.fields.filter(f=>clean(f.label).toLowerCase()===label);
  if(fields.length!==1||!clean(fields[0].value))throw new Error('vehicle_overview_not_ready');
  if(label==='odometer'&&!/^(?:[\d,]+(?:\.\d+)?\s*(?:mi|km)|—|–|--|N\/A)$/i.test(clean(fields[0].value)))throw new Error('vehicle_overview_not_ready');
 }
 const vins=snapshot.fields.filter(f=>clean(f.label).toLowerCase()==='vin');
 if(vins.length>1)throw new Error('ambiguous_vin');
 if(!vins.length)return {vin:null,source_vin_state:'not_displayed'};
 const value=clean(vins[0].value);
 if(/^[A-HJ-NPR-Z0-9]{17}$/.test(value))return {vin:value,source_vin_state:null};
 if(!value||/^(?:—|–|--|N\/A)$/i.test(value))return {vin:null,source_vin_state:'explicitly_empty'};
 throw new Error('vehicle_identity_unavailable');
}
function sameIdentity(before,after){
 if(before.vin!==after.vin||before.source_vin_state!==after.source_vin_state)throw new Error('vin_changed');
 return after;
}
// Grounded Oct16 authenticated truck26 DOM; reads only rendered document nodes.
function summarySnapshot(){
 const visible=el=>!!el&&el.getClientRects().length>0&&getComputedStyle(el).visibility!=='hidden'&&getComputedStyle(el).display!=='none';
 const profiles=Array.from(document.querySelectorAll('vehicle-profile-v2-summary > phx-card.vehicle-profile-card')).filter(visible);
 const profile=profiles.length===1?profiles[0]:null;
 const containers=profile?Array.from(profile.querySelectorAll('.cells-container')).filter(visible):[];
 const fields=[];
 if(containers.length===1)for(const cell of containers[0].querySelectorAll(':scope > .cell')){
  const header=cell.querySelector(':scope > .header');if(!header)continue;
  const label=header.textContent.trim();
  const value=Array.from(cell.children).filter(child=>child!==header).map(child=>child.textContent.trim()).filter(Boolean).join(' ');
  // A hidden responsive empty VIN cell is not a displayed empty field. A
  // nonempty responsive VIN must still stop placeholder identity collection.
  if(visible(cell)||(label.toUpperCase()==='VIN'&&value))fields.push({label,value});
 }
 return {url:location.href,units:profiles.flatMap(card=>Array.from(card.querySelectorAll('section[phx-card-header] [phxcardtitle]')).filter(visible).map(el=>el.textContent.trim())),breadcrumbs:Array.from(document.querySelectorAll('phx-breadcrumb [data-testid="breadcrumb-title"]')).filter(visible).map(el=>el.textContent.trim()),live_links:Array.from(document.querySelectorAll('a[href*="/fleetview/map/vehicle/"]')).filter(el=>visible(el)&&el.textContent.trim()==='Live').map(el=>el.getAttribute('href')),fields,loading:containers.length!==1||Array.from(containers[0].querySelectorAll('.ant-spin-spinning,.phx-loading-icon,loader.loading,[aria-busy="true"]')).some(visible)};
}
async function readReviewedPageIdentity(page,link){
 await page.getByRole('link',{name:'Live',exact:true}).filter({visible:true}).first().waitFor();
 for(let attempt=0;attempt<60;attempt++){
  const snapshot=await page.evaluate(summarySnapshot);
  try{return summaryIdentity(snapshot,link);}catch(error){
   if(error.message!=='vehicle_overview_not_ready')throw error;
   if(attempt===59){const timeout=new Error('vehicle_overview_timeout');timeout.name='TimeoutError';throw timeout;}
  }
  await page.waitForTimeout(250);
 }
}
async function readReviewedIdentity(context,link){
 const page=await context.newPage();page.setDefaultTimeout(15000);
 try{await page.goto(ORIGIN+'/en-US/'+link.href,{waitUntil:'domcontentloaded',timeout:45000});return await readReviewedPageIdentity(page,link);}finally{await page.close();}
}
function assertNoLiveVin(text){
 // Absence proof comes from the fully loaded fresh summaries on either side.
 // Live text is only an additional contradiction guard, never absence proof.
 if(/\bVIN\s*[:\t ]*\s*[A-HJ-NPR-Z0-9]{17}\b/.test(text))throw new Error('vin_changed');
 const field=text.match(/(?:^|\n)\s*VIN\s*[:\t ]*\n([^\n]*)/i);
 if(field&&field[1].trim()&&!/^(?:—|–|--|N\/A)$/i.test(field[1].trim()))throw new Error('vehicle_identity_unavailable');
}
module.exports={ALLOWLIST,allowlist,isReviewed,sourceIdentity,summaryIdentity,sameIdentity,summarySnapshot,readReviewedPageIdentity,readReviewedIdentity,assertNoLiveVin};
