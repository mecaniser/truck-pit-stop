'use strict';
const {createHash,randomUUID}=require('node:crypto');
const diagnostic=require('./trip_populated_diagnostics.cjs');
const ORIGIN='https://api.keeptruckin.com';
const fail=()=>{throw Error('report_populated_proof_invalid');};
const sha=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const id=x=>{if((typeof x!=='string'&&typeof x!=='number')||!/^[1-9]\d*$/.test(String(x))||String(x)==='0'||(typeof x==='number'&&!Number.isSafeInteger(x)))fail();return String(x);};
function wall(timestamp){
 if(typeof timestamp!=='string'||!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(timestamp)||!Number.isFinite(Date.parse(timestamp)))fail();
 const calendar=timestamp.slice(0,10);if(new Date(calendar+'T00:00:00Z').toISOString().slice(0,10)!==calendar)fail();
 const clock=timestamp.slice(11,19).split(':').map(Number);if(clock[0]>23||clock[1]>59||clock[2]>59)fail();
 const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(timestamp)).map(p=>[p.type,p.value]));
 return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
const NUMERIC=/^(\d{1,2})\/(\d{1,2})\/(\d{4})\s+(\d{1,2}):(\d{2})\s+(AM|PM)$/i;
const NAMED=/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s+(\d{4}),\s+(\d{1,2}):(\d{2})\s+(AM|PM)$/i;
function departureText(row){const value=row?.cells?.[1];return typeof value==='string'?value.split('\n')[0].trim():null;}
function rowIdentity(row){
 const links=[...new Set(row?.links||[])];if(links.length!==1)fail();const m=links[0].match(/^#\/fleetview\/vehicles\/summary\/(\d+)$/);if(!m)fail();
 const text=departureText(row);let d=text?.match(NUMERIC),named=false;if(!d){d=text?.match(NAMED);named=true;}
 if(!d)fail();let [,month,day,year,hour,minute,ampm]=d;
 if(named)month=String(['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].indexOf(month.toLowerCase())+1);
 const h=Number(hour),min=Number(minute),mo=Number(month),da=Number(day);if(h<1||h>12||min>59||mo<1||mo>12||da<1||da>31)fail();
 const date=`${year}-${month.padStart(2,'0')}-${day.padStart(2,'0')}`;if(new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date)fail();
 const local=`${date}T${String(h%12+(ampm.toUpperCase()==='PM'?12:0)).padStart(2,'0')}:${minute}`;
 // Derive neighboring NY offsets, then require exactly one round-tripping instant.
 // A fold has two candidates and a spring gap has none, matching the importer.
 const naive=Date.parse(local+':00Z'),candidates=new Set();
 for(const delta of [-12,12]){const reference=naive+delta*3600000;const offset=reference-Date.parse(wall(new Date(reference).toISOString())+':00Z');const instant=naive+offset;if(wall(new Date(instant).toISOString())===local)candidates.add(instant);}
 if(candidates.size!==1)fail();return [id(m[1]),local];
}
function rowShapes(rows){const result={dom_numeric_format:0,dom_named_format:0,dom_unknown_format:0,dom_invalid_links:0,dom_invalid_identities:0,dom_duplicate_identities:0},seen=new Set();
 for(const row of rows.slice(0,20000)){const text=departureText(row);result[NUMERIC.test(text||'')?'dom_numeric_format':NAMED.test(text||'')?'dom_named_format':'dom_unknown_format']++;
 const links=Array.isArray(row?.links)?[...new Set(row.links)]:[];if(links.length!==1||typeof links[0]!=='string'||!/^#\/fleetview\/vehicles\/summary\/[1-9]\d*$/.test(links[0]))result.dom_invalid_links++;
 try{const key=JSON.stringify(rowIdentity(row));if(seen.has(key))result.dom_duplicate_identities++;seen.add(key);}catch{result.dom_invalid_identities++;}}
 return result;}
function identityDigest(rows){const identities=rows.map(rowIdentity).sort((a,b)=>JSON.stringify(a)<JSON.stringify(b)?-1:1);if(new Set(identities.map(x=>JSON.stringify(x))).size!==identities.length)fail();return sha(identities);}
function requestMatches(request,day){
 let u;try{u=new URL(request.url());}catch{return false;}if(u.origin!==ORIGIN)return false;
 let pair=false,conflict=false;const check=o=>{if(!o||typeof o!=='object'||Array.isArray(o)){conflict=true;return;}for(const [s,e]of[['start_date','end_date'],['from_date','to_date']]){if(Object.hasOwn(o,s)&&o[s]!==day||Object.hasOwn(o,e)&&o[e]!==day)conflict=true;if(o[s]===day&&o[e]===day)pair=true;}};
 const keys=['start_date','end_date','from_date','to_date'];for(const k of keys)if(u.searchParams.getAll(k).length>1)conflict=true;check(Object.fromEntries(u.searchParams));
 const post=request.postData();if(post){if(post.length>65536)return false;try{for(const k of keys)if((post.match(new RegExp('"'+k+'"\\s*:','g'))||[]).length>1)conflict=true;check(JSON.parse(post));}catch{return false;}}
 return pair&&!conflict;
}
function createProof(page,window,{epoch=randomUUID(),now=()=>Date.now(),bodyTimeoutMs=10000,maxResponses=400}={}){
 if(window.start!==window.end)fail();const requests=new WeakSet(),pending=new Set(),records=new Map(),identities=new Set();let total=null,perPage=null,count=0,bytes=0,error=null,closed=false,queue=Promise.resolve();const started=now();
 let lastRows=[];let observed=0,provider=0,unbound=0;let reason=null,matched=0,decoded=0,fields={},domRows=null,rendered=null;
 const bad=code=>{error='report_populated_proof_invalid';reason=reason||code;};
 const snapshot=()=>diagnostic.sanitize({...rowShapes(lastRows),reason:reason||(total===null?'no_matching_response':pending.size?'pending_response':records.size!==total?'incomplete_tail':domRows!==total?'dom_count_mismatch':rendered!==total?'rendered_count_mismatch':undefined),observed_requests:observed,provider_requests:provider,unbound_provider_requests:unbound,matched_requests:matched,responses:count,pending:pending.size,decoded_pages:decoded,authoritative_total:total,response_identities:records.size,dom_rows:domRows,rendered_count:rendered,fields});
 const reject=code=>{bad(code);fail();};
 const onRequest=request=>{if(closed)return;observed++;let approved=false;try{approved=new URL(request.url()).origin===ORIGIN;}catch{}if(approved)provider++;if(requestMatches(request,window.start)){matched++;requests.add(request);pending.add(request);}else if(approved)unbound++;};
 const onResponse=response=>{
  if(closed||!requests.has(response.request()))return;
  if(++count>maxResponses){bad('response_limit');return;}
  queue=queue.then(async()=>{
   if(error||closed)return;let timer,raw;
   try{
    if(new URL(response.url()).origin!==ORIGIN)reject('transport');if(response.status()!==200)reject('status');if(!/^application\/(?:[a-z0-9.+-]*\+)?json(?:;|$)/i.test(response.headers()['content-type']||''))reject('content_type');
    const length=response.headers()['content-length'];if(length!==undefined&&(!/^\d+$/.test(length)||Number(length)>2000000))reject('declared_body_limit');
    raw=await Promise.race([response.body(),new Promise((_,reject)=>{timer=setTimeout(()=>{bad('body_timeout');reject(Error('timeout'));},bodyTimeoutMs);})]);
    if(closed||error)return;bytes+=raw.length;if(raw.length>2000000||bytes>16000000)reject('decoded_body_limit');
    let body;try{body=JSON.parse(raw.toString('utf8'));}catch{reject('json');}decoded++;
    fields={total:diagnostic.type(body?.total),per_page:diagnostic.type(body?.per_page),driving_periods:diagnostic.type(body?.driving_periods)};
    if(!body||!Number.isSafeInteger(body.total)||body.total<0||body.total>20000||!Number.isSafeInteger(body.per_page)||body.per_page<1||body.per_page>20000||!Array.isArray(body.driving_periods)||(body.total>0&&body.driving_periods.length<1)||body.driving_periods.length>body.per_page)reject('root_shape');
    if(total!==null&&(total!==body.total||perPage!==body.per_page))reject('total_changed');total=body.total;perPage=body.per_page;
    for(const item of body.driving_periods){
     const trip=item?.driving_period;fields={...fields,record:diagnostic.type(trip),id:diagnostic.type(trip?.id),vehicle:diagnostic.type(trip?.vehicle),vehicle_id:diagnostic.type(trip?.vehicle?.id),start_time:diagnostic.type(trip?.start_time)};if(!trip||typeof trip!=='object')reject('record_shape');
     let record,vehicle,departure;try{record=id(trip.id);}catch{reject('id_invalid');}try{vehicle=id(trip.vehicle?.id);}catch{reject('vehicle_id_invalid');}try{departure=wall(trip.start_time);}catch{reject('timestamp_invalid');}const identity=[vehicle,departure],key=JSON.stringify(identity);
     if(!identity[1].startsWith(window.start+'T'))reject('outside_day');if(records.has(record))reject('duplicate_id');if(identities.has(key))reject('duplicate_identity');
     records.set(record,identity);identities.add(key);
    }
    if(records.size>total)reject('root_shape');
   }catch{bad('transport');}finally{raw=null;pending.delete(response.request());clearTimeout(timer);}
  });
 };
 const onFailed=request=>{if(requests.has(request)){pending.delete(request);bad('request_failed');}};
 const seal=()=>{closed=true;page.off('request',onRequest);page.off('response',onResponse);page.off('requestfailed',onFailed);};
 const drain=async()=>{let current;do{current=queue;await current;}while(current!==queue);if(error)fail();return pending.size===0;};
 page.on('request',onRequest);page.on('response',onResponse);page.on('requestfailed',onFailed);
 return {
  snapshot,
  async empty(){if(!await drain())return false;if(total!==null&&total!==0)reject('dom_count_mismatch');seal();return true;},
  async proof(rows,sourceReadAt,renderedTotal=rows.length){lastRows=rows;domRows=rows.length;rendered=renderedTotal;if(!await drain())return null;if(total===null||records.size!==total||rows.length!==total||renderedTotal!==total)return null;
   const expected=sha([...records.values()].sort((a,b)=>JSON.stringify(a)<JSON.stringify(b)?-1:1));let actual;try{actual=identityDigest(rows);}catch{reject('dom_identity_invalid');}if(actual!==expected)reject('bijection_mismatch');seal();
   return {version:1,kind:'passive_provider_pages',epoch,start:window.start,end:window.end,origin:ORIGIN,total,per_page:perPage,response_count:count,response_identity_count:records.size,dom_identity_count:rows.length,identity_sha256:expected,first_observed_at:new Date(started).toISOString(),last_observed_at:sourceReadAt};
  },
  close(){seal();lastRows=[];pending.clear();records.clear();identities.clear();},
 };
}
function validProof(receipt){
 const p=receipt.populated_proof;if(!p||p.version!==1||p.kind!=='passive_provider_pages'||p.origin!==ORIGIN||p.start!==receipt.start||p.end!==receipt.end||p.start!==p.end||!/^[-0-9a-f]{36}$/.test(p.epoch||''))return false;
 try{return p.total===receipt.rows.length&&p.total>0&&p.total<=20000&&p.response_identity_count===p.total&&p.dom_identity_count===p.total&&Number.isSafeInteger(p.per_page)&&p.per_page>0&&p.per_page<=20000&&Number.isSafeInteger(p.response_count)&&p.response_count>=Math.ceil(p.total/p.per_page)&&p.response_count<=400&&p.identity_sha256===identityDigest(receipt.rows)&&Number.isFinite(Date.parse(p.first_observed_at))&&p.last_observed_at===receipt.source_read_at&&Date.parse(p.last_observed_at)>=Date.parse(p.first_observed_at)&&Date.parse(p.last_observed_at)-Date.parse(p.first_observed_at)<=1800000;}catch{return false;}
}
module.exports={rowShapes,createProof,validProof,identityDigest,rowIdentity,requestMatches};
