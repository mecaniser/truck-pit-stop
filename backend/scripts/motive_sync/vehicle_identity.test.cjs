const test=require('node:test');
const assert=require('node:assert/strict');
const {allowlist,isReviewed,sourceIdentity,summaryIdentity,sameIdentity,readReviewedIdentity,readReviewedPageIdentity,summarySnapshot,assertNoLiveVin}=require('./vehicle_identity.cjs');
const {collectWithRetries}=require('./collect.cjs');
const vin='1FUJGLDR9CLBU2344';
const link={href:'#/fleetview/vehicles/summary/123',unit:'26'};
function ready(){return {url:'https://app.gomotive.com/en-US/'+link.href,units:['26'],breadcrumbs:['26 (2021 Volvo Truck Vnl)'],live_links:['#/fleetview/map/vehicle/123-null-null/123/live'],loading:false,fields:[{label:'FUEL TYPE',value:'Diesel'},{label:'REGULATED',value:'Yes'},{label:'AVAILABILITY',value:'In service'},{label:'GROUPS',value:'0 Groups'},{label:'DATA SOURCE',value:'AI Dashcam Plus'},{label:'ODOMETER',value:'540,892 mi'}]};}
test('only an explicit exact company/provider allowlist enables the additional reader',()=>{
 const list=allowlist('[{"company_id":"KT123","provider_vehicle_id":"123"}]');
 assert.equal(isReviewed(list,'KT123','123'),true);
 assert.equal(isReviewed(list,'KT124','123'),false);assert.equal(isReviewed(list,'KT123','124'),false);
 for(const raw of ['null','{}','[{"company_id":"KT123","provider_vehicle_id":123}]','[{"company_id":"KT123","provider_vehicle_id":"123","unit":"26"}]','[{"company_id":"KT123","provider_vehicle_id":"123"},{"company_id":"KT123","provider_vehicle_id":"123"}]'])assert.throws(()=>allowlist(raw));
});
test('completed overview honestly distinguishes not displayed, explicitly empty and real VIN',()=>{
 assert.deepEqual(summaryIdentity(ready(),link),{vin:null,source_vin_state:'not_displayed'});
 for(const value of ['','—','N/A']){const snapshot=ready();snapshot.fields.push({label:'VIN',value});assert.deepEqual(summaryIdentity(snapshot,link),{vin:null,source_vin_state:'explicitly_empty'});}
 const snapshot=ready();snapshot.fields.push({label:'VIN',value:vin});assert.deepEqual(summaryIdentity(snapshot,link),{vin,source_vin_state:null});
});
test('incomplete, loading, wrong-source or ambiguous summary never proves VIN state',()=>{
 for(const mutation of [s=>s.units=[],s=>s.units.push('26'),s=>s.units=['27'],s=>s.breadcrumbs=['27 (Volvo)'],s=>s.breadcrumbs.push('26 (Volvo)'),s=>s.loading=true,s=>s.fields.pop(),s=>s.fields.push({...s.fields[0]}),s=>s.fields[5].value='Loading',s=>s.fields[2].value='',s=>s.live_links=[],s=>s.live_links.push(s.live_links[0]),s=>s.live_links=['#/fleetview/map/vehicle/124-null-null/123/live'],s=>s.live_links=['#/fleetview/map/vehicle/123-null-null/124/live'],s=>s.url='https://evil.example/'+link.href,s=>s.url='https://app.gomotive.com/en-US/#/fleetview/vehicles/summary/124',s=>s.fields.push({label:'VIN',value:'PENDING-26'}),s=>s.fields.push({label:'VIN',value:vin},{label:'VIN',value:vin})]){const snapshot=ready();mutation(snapshot);assert.throws(()=>summaryIdentity(snapshot,link));}
});
test('missing generic text is not source proof; a changed VIN display state fails',()=>{
 for(const text of ['Loading','VIN\nPENDING-26','VIN\ninvalid','No VIN','VIN'])assert.throws(()=>sourceIdentity(text));
 assert.throws(()=>sourceIdentity('VIN '+vin+'\nVIN 1M8GDM9AXKP042788'),/ambiguous_vin/);
 const missing={vin:null,source_vin_state:'not_displayed'};
 assert.deepEqual(sameIdentity(missing,{...missing}),missing);
 assert.throws(()=>sameIdentity(missing,{vin,source_vin_state:null}),/vin_changed/);
 assert.throws(()=>sameIdentity(missing,{vin:null,source_vin_state:'explicitly_empty'}),/vin_changed/);
 assert.throws(()=>assertNoLiveVin('VIN '+vin),/vin_changed/);
});
test('fresh source reader preserves navigation timeout instead of inventing absent VIN',async()=>{
 let closed=0;const error=Object.assign(new Error('bounded'),{name:'TimeoutError'});
 const context={newPage:async()=>({setDefaultTimeout(){},goto:async()=>{throw error},close:async()=>closed++})};
 await assert.rejects(readReviewedIdentity(context,link),e=>e===error);assert.equal(closed,1);
});
test('only reviewed location path retains null source VIN; real VIN transition fails across retries',async()=>{
 const context={newPage:async()=>({setDefaultTimeout(){},url:()=> 'https://app.gomotive.com',close:async()=>{}})};
 const capture=await collectWithRetries(context,link,async(page,link,bind)=>{bind(null);return {status:'located',precision:'second',source_vin_state:'not_displayed'};},{reviewed:true});
 assert.equal(capture.vin,null);assert.equal(capture.source_vin_state,'not_displayed');
 await assert.rejects(collectWithRetries(context,link,async(page,link,bind,attempt)=>{bind(attempt?vin:null);return {status:'located',precision:'unknown'};},{reviewed:true}),/vin_changed/);
});

test('Live can precede overview; empty startup retries but timeouts and ambiguity never become missing VIN',async()=>{
 function pageFor(snapshots){let reads=0,waits=0;const locator={filter(){return this},first(){return this},async waitFor(){}};return {getByRole:()=>locator,evaluate:async()=>snapshots[Math.min(reads++,snapshots.length-1)],waitForTimeout:async()=>{waits++},counts:()=>({reads,waits})};}
 const loading={...ready(),units:[],breadcrumbs:[],fields:[],loading:true};
 const page=pageFor([loading,ready()]);
 assert.deepEqual(await readReviewedPageIdentity(page,link),{vin:null,source_vin_state:'not_displayed'});assert.deepEqual(page.counts(),{reads:2,waits:1});
 const timed=pageFor([loading]);await assert.rejects(readReviewedPageIdentity(timed,link),e=>e.name==='TimeoutError'&&e.message==='vehicle_overview_timeout');assert.deepEqual(timed.counts(),{reads:60,waits:59});
 const duplicate=pageFor([{...ready(),units:['26','26']}]);await assert.rejects(readReviewedPageIdentity(duplicate,link),/vehicle_identity_changed/);assert.deepEqual(duplicate.counts(),{reads:1,waits:0});
});
test('DOM reader scopes the overview title and treats hidden responsive VIN honestly',()=>{
 const vm=require('node:vm');
 const el=(text,shown=true)=>({textContent:text,getClientRects:()=>shown?[{}]:[],children:[],querySelectorAll:()=>[]});
 const cells=ready().fields.map(f=>{const header=el(f.label),value=el(f.value),cell=el('');cell.children=[header,value];cell.querySelector=()=>header;return cell;});
 const vinHeader=el('VIN',false),vinValue=el('',false),vinCell=el('',false);vinCell.children=[vinHeader,vinValue];vinCell.querySelector=()=>vinHeader;cells.push(vinCell);
 const container=el('');container.querySelectorAll=selector=>selector===':scope > .cell'?cells:[];
 const profile=el('');profile.querySelectorAll=selector=>selector==='.cells-container'?[container]:[el('26')];
 const live=el('Live');live.getAttribute=()=>ready().live_links[0];
 let profiles=[profile];
 const document={querySelectorAll:selector=>{
  if(selector==='vehicle-profile-v2-summary > phx-card.vehicle-profile-card')return profiles;
  if(selector==='phx-breadcrumb [data-testid="breadcrumb-title"]')return [el('26 (2021 Volvo Truck Vnl)')];
  if(selector==='a[href*="/fleetview/map/vehicle/"]')return [live];
  if(selector==='section[phx-card-header] [phxcardtitle]')return ['26','Fuel trend','Fuel performance','Inspections','Recent activity'].map(t=>el(t));
  throw new Error('Unexpected ungrounded selector '+selector);
 }};
 const snapshot=()=>JSON.parse(JSON.stringify(vm.runInNewContext('('+summarySnapshot.toString()+')()', {document,location:{href:ready().url},getComputedStyle:()=>({visibility:'visible',display:'block'})})));
 assert.deepEqual(summaryIdentity(snapshot(),link),{vin:null,source_vin_state:'not_displayed'});
 vinValue.textContent=vin;assert.deepEqual(summaryIdentity(snapshot(),link),{vin,source_vin_state:null});
 vinValue.textContent='invalid';assert.throws(()=>summaryIdentity(snapshot(),link),/vehicle_identity_unavailable/);
 profiles=[profile,profile];assert.throws(()=>summaryIdentity(snapshot(),link),/vehicle_identity_changed/);
});
