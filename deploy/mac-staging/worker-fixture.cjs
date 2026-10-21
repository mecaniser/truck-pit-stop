/* Staging-only rendered synthetic provider. Never contacts the real provider.
 * Loaded via NODE_OPTIONS in a network-isolated, pinned worker image only.
 * Collector selectors, identity checks, timestamps and importers are unchanged.
 */
'use strict';
const fs = require('node:fs');
const Module = require('node:module');
if (process.env.ENVIRONMENT !== 'staging' || process.env.STAGING_WORKER_FIXTURE !== 'synthetic-v1')
  throw Error('Synthetic worker preload requires explicit staging opt-in');
const db = new URL(process.env.DATABASE_URL || '');
if (db.hostname !== 'postgres' || db.pathname !== '/dieselbridge_worker_fixture')
  throw Error('Synthetic worker preload refuses other databases');
if (process.env.MOTIVE_EMAIL !== 'fixture@example.invalid' || process.env.MOTIVE_PASSWORD !== 'synthetic-not-a-provider-password')
  throw Error('Only dummy provider credentials allowed');
const events = process.env.STAGING_FIXTURE_EVENTS || '/state/fixture-events.jsonl';
function record(event) { fs.appendFileSync(events, JSON.stringify({at:new Date().toISOString(),pid:process.pid,...event})+'\n',{mode:0o600}); }
// No real state is sampled. Six deterministic identities belong solely to seed fixtures.
const vehicles = Array.from({length:6},(_,i)=>({id:String(101+i),unit:`FIX-${i+1}`,vin:`1M8GDM9AXKP04278${i+1}`,driver:String(201+i),name:`Synthetic Driver ${i+1}`}));
function pageScript(vehicles, headers, variant) {
 const app='https://app.gomotive.com';
 const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
 const table=(head,rows)=>`<table><thead><tr>${head.map(x=>`<th>${esc(x)||'&nbsp;'}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;
 const cells=a=>'<tr>'+a.map(x=>`<td>${x}</td>`).join('')+'</tr>';
 const link=v=>`<a href="#/fleetview/vehicles/summary/${v.id}">${v.unit}</a>`;
 const rows=()=>vehicles.map(v=>cells([link(v)]));
 const dateLabel=d=>new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(d+'T12:00:00Z'));
 async function render() {
  const hash=location.hash;
  await window.fixtureEvent({event:'view',hash});
  if(location.hostname==='auth.gomotive.com') {
   document.body.innerHTML='<input name="user_profile[email]"><input name="user_profile[password]" type="password"><button>Log in</button>';
   document.querySelector('button').onclick=()=>location.href=app+'/en-US/';return;
  }
  if(location.pathname==='/') {location.href='https://auth.gomotive.com/login';return;}
  let html='';
  if(hash==='#/admin/company') html=`<div>${variant==='wrong-company'?'Wrong fixture company':'77 CARGO LLC'}</div><div>KT8934277</div>`;
  else if(hash==='#/settings') html='<section><span>Time zone</span><div>Eastern Time - New York</div></section>';
  else if(hash==='#/admin/vehicles') html=table(['Vehicle'],rows())+'<p>Showing 6 of 6</p>';
  else if(hash.startsWith('#/fleetview/vehicles/summary/')) {
   const v=vehicles.find(v=>hash.endsWith('/'+v.id));if(!v)throw Error('unknown fixture vehicle');
   html=`<div>VIN <span>${variant==='wrong-vin'?'4V4WC9EG2LN250024':v.vin}</span></div><a href="#/fleetview/map/vehicle/${v.id}-null-null/${v.id}/live">Live</a>`;
  } else if(hash.includes('/live')) {
   const v=vehicles.find(v=>hash.includes('/'+v.id+'/live'));if(!v)throw Error('unknown fixture live');
   html=`<a href="${hash}">Live</a><div>VIN <span>${v.vin}</span></div><section class="driver-location-info"><div class="current-location"><span data-e2e="speed-info"><span class="value">0</span><span class="symbol">MPH</span></span></div></section><div class="current-location-status">Stationary</div><div class="container mt-4 pos-relative"><span class="grey-70 regular-14">Synthetic staging yard</span></div><button phxcontent="Copy coordinates">Copy</button><div class="phx-tooltip-content" style="display:none"></div>`;
  } else if(hash==='#/maintenance/health') {
   html=table(['vehicle or asset','availability','defects','fault codes','next service','',''],vehicles.map(v=>`<tr>${[link(v),'Available','0','0','—','',''].map((x,i)=>`<td ${i===3?'data-fault="'+v.id+'"':''}>${x||'&nbsp;'}</td>`).join('')}</tr>`))+'<p>Showing 6 of 6</p><div data-testid="section-fault-codes" style="display:none"><div>Current fault codes</div><div>No fault codes</div></div>';
  } else if(hash.startsWith('#/reports/vehicle-fuel-performance;')) {
   const p=Object.fromEntries(hash.split(';').slice(1).map(x=>x.split('='))),v=vehicles.find(v=>v.id===p.vehicle_ids);
   if(!v)throw Error('unknown fuel vehicle');
   html=`<div class="phx-date-picker-range-labels"><span class="phx-date-picker-label">${dateLabel(p.start_date)}</span></div><phx-select phx-non-default-selected="true"><span class="phx-select-value">${v.unit}</span></phx-select>`+table(headers,[`<tr data-e2e="table-row">${Object.entries({vehicle:v.unit,'driving-fuel':'2','idle-fuel':'1','total-fuel':'3','total-distance':'100','driving-time':'1h','idle-time':'10m'}).map(([k,x])=>`<td data-e2e="${k}">${x}</td>`).join('')}</tr>`]);
  } else if(hash.startsWith('#/fleetview/list/trips/trips;')) {
   const p=Object.fromEntries(hash.split(';').slice(1).map(x=>x.split('='))),[year,month,day]=p.start_date.split('-'),date=`${month}/${day}/${year}`;
   html='<main><div style="height:500px;overflow-y:auto">'+table(['','Origin (MDY EDT)','Destination (MDY EDT)','Dist. (mi) / Duration','Vehicle ID / Mode','Driver / ID','','Notes',''],vehicles.map(v=>cells(['',`${date} 01:00 AM<br>Synthetic origin`,`${date} 02:00 AM<br>Synthetic destination`,'100 mi<br>1h 0m 0s',link(v),'','','',''])))+'</div><p>Showing 6 results</p></main>';
  } else if(hash==='#/admin/safety/performance-ranges') html='<p>Each block represents a performance range and the scores that fall within it.</p><p>Fair 50–69</p><p>Good 70–89</p><p>Excellent 90–100</p>';
  else if(hash==='#/fleetview/list/drivers') html=table(['DRIVER NAME / ID','VEHICLE ID'],vehicles.map(v=>cells([`<a href="#/fleetview/drivers/summary/${v.driver}">${v.name}</a>`,link(v)])))+'<p>Showing 6 of 6</p>';
  else if(hash.startsWith('#/fleetview/drivers/summary/')) {
   const v=vehicles.find(v=>hash.endsWith('/'+v.driver));if(!v)throw Error('unknown driver');
   html=`<phx-breadcrumb><phx-breadcrumb-item><a class="phx-breadcrumb-link" href="#/fleetview/map">Fleet View</a></phx-breadcrumb-item><phx-breadcrumb-item><a class="phx-breadcrumb-link" href="#/fleetview/list/drivers">Drivers</a></phx-breadcrumb-item><phx-breadcrumb-item><span data-testid="breadcrumb-title">${v.name}</span></phx-breadcrumb-item></phx-breadcrumb><section class="safety-score-card"><div>Safety Score</div><div>LAST 30 DAYS</div><div id="score-trend-tooltip"><div id="score-text">90</div></div><div>Top behaviors impacting score</div><div>No behaviors</div></section><section><div>Fuel performance</div><div>LAST 30 DAYS</div><div>50%</div><div>UTILIZATION</div><div>Active time</div><div>1h</div><div>Idle time</div><div>10m</div></section><a href="#/coaching/1">Driver needs coaching Never 0</a><div class="ant-table-wrapper">${table(['DATE (MDY EDT) / LOCATION','VEHICLE ID / MMY','STATUS','BEHAVIOR / SEVERITY'],[])}<empty-table><div class="message">There are no safety events for ${v.name}.</div></empty-table></div>`;
  } else if(hash) throw Error('Unhandled fixture route '+hash);
  document.body.innerHTML=html;
  if(hash.includes('/live')) {
   const tip=document.querySelector('.phx-tooltip-content');
   const stamp=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date()).replace(' at',',');
   document.querySelector('.current-location-status').onmouseenter=()=>{tip.textContent=stamp;tip.style.display='block';};
   document.querySelector('a').onmouseenter=()=>{tip.style.display='none';};
   document.querySelector('button').onclick=()=>navigator.clipboard.writeText('35.1, -80.9');
  }
  for(const cell of document.querySelectorAll('[data-fault]'))cell.onclick=async()=>{await window.fixtureEvent({event:'fault_card',id:cell.dataset.fault});document.querySelector('[data-testid="section-fault-codes"]').style.display='block';};
 }
 addEventListener('hashchange',()=>render().catch(e=>window.fixtureEvent({event:'fixture_error',message:e.message})));
 render().catch(e=>window.fixtureEvent({event:'fixture_error',message:e.message}));
}
const fuelHeaders=['VEHICLE NUMBER','MAKE / MODEL / YEAR','GROUP','AVG. MPG','MOVING MPG','TOTAL DISTANCE (MI)','TOTAL FUEL (GAL)','EST. CARBON EMISSIONS (LBS)','UTILIZATION','DRIVING TIME','DRIVING FUEL (GAL)','IDLING TIME','IDLED FUEL (GAL)','FUEL COST (USD)','ODOMETER (MI)','FUEL TYPE','NUMBER OF OPEN FAULT CODES','OPEN FAULT CODES'];
const html=`<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:sans-serif}td,th{padding:5px}phx-breadcrumb,phx-breadcrumb-item,phx-select,empty-table{display:block}</style></head><body><script>(${pageScript})(${JSON.stringify(vehicles)},${JSON.stringify(fuelHeaders)},${JSON.stringify(process.env.STAGING_FIXTURE_VARIANT||'normal')})</script></body></html>`;
const original=Module._load;
let installed=false;
Module._load=function(request,parent,isMain){
 const result=original.apply(this,arguments);
 if(!installed&&result?.chromium&&/playwright/.test(request)) {
  installed=true;const launch=result.chromium.launch.bind(result.chromium);
  result.chromium.launch=async options=>{
   record({event:'browser_launch'});const browser=await launch(options),newContext=browser.newContext.bind(browser);
   browser.newContext=async options=>{
    const context=await newContext({...options,serviceWorkers:'block'});
    await context.exposeBinding('fixtureEvent',async(source,event)=>{
     record(event);
     const target=process.env.STAGING_FIXTURE_KILL_MATCH,marker=process.env.STAGING_FIXTURE_KILL_MARKER;
     if(target&&marker&&JSON.stringify(event).includes(target)&&!fs.existsSync(marker)) {
      fs.writeFileSync(marker,'injected once\n',{flag:'wx',mode:0o600});record({event:'injected_kill',target});process.kill(process.pid,'SIGKILL');
     }
    });
    await context.route('**/*',async route=>{
     const u=new URL(route.request().url());
     if(route.request().resourceType()==='document'&&['https://app.gomotive.com','https://auth.gomotive.com'].includes(u.origin))await route.fulfill({status:200,contentType:'text/html',body:html});
     else {record({event:'blocked_request',origin:u.origin});await route.abort('blockedbyclient');}
    });return context;
   };return browser;
  };
 }
 return result;
};
