'use strict';
const {createHash,randomUUID}=require('node:crypto');
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
function rowIdentity(row){
 const links=[...new Set(row?.links||[])];if(links.length!==1)fail();const m=links[0].match(/^#\/fleetview\/vehicles\/summary\/(\d+)$/);if(!m)fail();
 const text=row.cells?.[1]?.split('\n')[0]?.trim();let d=text?.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})\s+(\d{1,2}):(\d{2})\s+(AM|PM)$/i);
 if(!d)fail();const [,month,day,year,hour,minute,ampm]=d;const h=Number(hour),min=Number(minute),mo=Number(month),da=Number(day);if(h<1||h>12||min>59||mo<1||mo>12||da<1||da>31)fail();
 const date=`${year}-${month.padStart(2,'0')}-${day.padStart(2,'0')}`;if(new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date)fail();
 return [id(m[1]),`${date}T${String(h%12+(ampm.toUpperCase()==='PM'?12:0)).padStart(2,'0')}:${minute}`];
}
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
 const bad=()=>{error='report_populated_proof_invalid';};
 const onRequest=request=>{if(!closed&&requestMatches(request,window.start)){requests.add(request);pending.add(request);}};
 const onResponse=response=>{
  if(closed||!requests.has(response.request()))return;
  if(++count>maxResponses){bad();return;}
  queue=queue.then(async()=>{
   if(error||closed)return;let timer,raw;
   try{
    if(new URL(response.url()).origin!==ORIGIN||response.status()!==200||!/^application\/(?:[a-z0-9.+-]*\+)?json(?:;|$)/i.test(response.headers()['content-type']||''))fail();
    const length=response.headers()['content-length'];if(length!==undefined&&(!/^\d+$/.test(length)||Number(length)>2000000))fail();
    raw=await Promise.race([response.body(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('timeout')),bodyTimeoutMs);})]);
    if(closed||error)return;bytes+=raw.length;if(raw.length>2000000||bytes>16000000)fail();
    const body=JSON.parse(raw.toString('utf8'));
    if(!Number.isSafeInteger(body.total)||body.total<0||body.total>20000||!Number.isSafeInteger(body.per_page)||body.per_page<1||body.per_page>20000||!Array.isArray(body.driving_periods)||(body.total>0&&body.driving_periods.length<1)||body.driving_periods.length>body.per_page)fail();
    if(total!==null&&(total!==body.total||perPage!==body.per_page))fail();total=body.total;perPage=body.per_page;
    for(const item of body.driving_periods){
     const trip=item?.driving_period;if(!trip||typeof trip!=='object')fail();
     const record=id(trip.id),identity=[id(trip.vehicle?.id),wall(trip.start_time)],key=JSON.stringify(identity);
     if(!identity[1].startsWith(window.start+'T')||records.has(record)||identities.has(key))fail();
     records.set(record,identity);identities.add(key);
    }
    if(records.size>total)fail();
   }catch{bad();}finally{raw=null;pending.delete(response.request());clearTimeout(timer);}
  });
 };
 const onFailed=request=>{if(requests.has(request)){pending.delete(request);bad();}};
 const seal=()=>{closed=true;page.off('request',onRequest);page.off('response',onResponse);page.off('requestfailed',onFailed);};
 const drain=async()=>{let current;do{current=queue;await current;}while(current!==queue);if(error)fail();return pending.size===0;};
 page.on('request',onRequest);page.on('response',onResponse);page.on('requestfailed',onFailed);
 return {
  async empty(){if(!await drain())return false;if(total!==null&&total!==0)fail();seal();return true;},
  async proof(rows,sourceReadAt,renderedTotal=rows.length){if(!await drain())return null;if(total===null||records.size!==total||rows.length!==total||renderedTotal!==total)return null;
   const expected=sha([...records.values()].sort((a,b)=>JSON.stringify(a)<JSON.stringify(b)?-1:1));if(identityDigest(rows)!==expected)fail();seal();
   return {version:1,kind:'passive_provider_pages',epoch,start:window.start,end:window.end,origin:ORIGIN,total,per_page:perPage,response_count:count,response_identity_count:records.size,dom_identity_count:rows.length,identity_sha256:expected,first_observed_at:new Date(started).toISOString(),last_observed_at:sourceReadAt};
  },
  close(){seal();pending.clear();records.clear();identities.clear();},
 };
}
function validProof(receipt){
 const p=receipt.populated_proof;if(!p||p.version!==1||p.kind!=='passive_provider_pages'||p.origin!==ORIGIN||p.start!==receipt.start||p.end!==receipt.end||p.start!==p.end||!/^[-0-9a-f]{36}$/.test(p.epoch||''))return false;
 try{return p.total===receipt.rows.length&&p.total>0&&p.total<=20000&&p.response_identity_count===p.total&&p.dom_identity_count===p.total&&Number.isSafeInteger(p.per_page)&&p.per_page>0&&p.per_page<=20000&&Number.isSafeInteger(p.response_count)&&p.response_count>=Math.ceil(p.total/p.per_page)&&p.response_count<=400&&p.identity_sha256===identityDigest(receipt.rows)&&Number.isFinite(Date.parse(p.first_observed_at))&&p.last_observed_at===receipt.source_read_at&&Date.parse(p.last_observed_at)>=Date.parse(p.first_observed_at)&&Date.parse(p.last_observed_at)-Date.parse(p.first_observed_at)<=1800000;}catch{return false;}
}
module.exports={createProof,validProof,identityDigest,rowIdentity,requestMatches};
