/* Private read checkpoints. Importers remain the only authority for database writes. */
const fs=require('node:fs');
const crypto=require('node:crypto');
const path=require('node:path');
const tripDiagnostics=require('./trip_diagnostics.cjs');
let currentPhase='startup';
function phase(name) {currentPhase=name;console.log(JSON.stringify({stage:'collection_phase',phase:name}));}
const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
function transient(error) {
 return error?.name==='TimeoutError'||/^(?:page\.(?:goto|reload): )?net::ERR_(CONNECTION_RESET|CONNECTION_CLOSED|TIMED_OUT|NETWORK_CHANGED)(?:\s|$)/.test(error?.message||'');
}
function safeReason(error) {return tripDiagnostics.category(error)||(transient(error)?'ui_timeout':'collection_failed');}
function atomic(file,value) {
 const temporary=file+'.'+crypto.randomUUID()+'.tmp';
 if(Buffer.byteLength(JSON.stringify(value))>16*1024*1024)throw new Error('checkpoint_limit');
 const fd=fs.openSync(temporary,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL,0o600);
 try {fs.writeFileSync(fd,JSON.stringify(value));fs.fsyncSync(fd);} finally {fs.closeSync(fd);}
 fs.renameSync(temporary,file);
}
async function retry(stage,action,{attempts=3,pause=ms=>new Promise(resolve=>setTimeout(resolve,ms)),log=value=>console.log(JSON.stringify(value))}={}) {
 phase(stage);
 for(let attempt=1;attempt<=attempts;attempt++) {
  const started=Date.now();
  log({stage:'collection_task_started',task:stage,attempt});
  try {const result=await action();log({stage:'collection_task_complete',task:stage,attempt,elapsed_ms:Date.now()-started});return result;}
  catch(error) {
   log({stage:'collection_task_failed',task:stage,attempt,reason:safeReason(error),retryable:transient(error)});
   if(!transient(error)||attempt===attempts)throw error;
   await pause(500*attempt+Math.floor(Math.random()*250));
  }
 }
}
function openTasks(output,scope,{maxAgeMs=15*60*1000,now=()=>Date.now(),log=value=>console.log(JSON.stringify(value))}={}) {
 const file=output+'.tasks.json';
 const binding=digest({version:1,scope,run:path.resolve(output),account:process.env.MOTIVE_EMAIL,tenant:process.env.MOTIVE_SYNC_TENANT_ID,actor:process.env.MOTIVE_SYNC_ACTOR_ID,reviewed:process.env.MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST});
 let state={version:1,binding,created_at:new Date(now()).toISOString(),tasks:{}};
 if(fs.existsSync(file)) {
  const stat=fs.lstatSync(file);
  if(!stat.isFile()||stat.isSymbolicLink()||(stat.mode&0o077)||stat.size>16*1024*1024)throw new Error('checkpoint_invalid');
  const saved=JSON.parse(fs.readFileSync(file,'utf8'));
  const age=now()-Date.parse(saved.created_at);
  const {integrity,...payload}=saved;
  if(saved.version!==1||!saved.tasks||typeof saved.tasks!=='object'||Array.isArray(saved.tasks)||integrity!==digest(payload))throw new Error('checkpoint_invalid');
  if(saved.binding!==binding)throw new Error('checkpoint_scope_changed');
  if(!Number.isFinite(age)||age<0||age>maxAgeMs)throw new Error('checkpoint_expired');
  state=payload;
 }
 const assertFresh=()=>{const age=now()-Date.parse(state.created_at);if(age<0||age>maxAgeMs)throw new Error('checkpoint_expired');};
 return {
  assertFresh,
  startedAt:state.created_at,
  async run(stage,key,action,{validateCached,reuse=true,cacheable=()=>true,attempts=3}={}) {
   assertFresh();
   const id=digest(key);
   if(reuse&&Object.hasOwn(state.tasks,id)) {
    if(validateCached)await validateCached(state.tasks[id]);
    log({stage:'collection_task_resumed',task:stage});
    return state.tasks[id];
   }
   const value=await retry(stage,action,{attempts});
   assertFresh();
   if(reuse&&cacheable(value)) {state.tasks[id]=value;atomic(file,{...state,integrity:digest(state)});}
   return value;
  },
 };
}
const diagnosticPhases=new Set(['trip_reviewed_directory','trip_reviewed_before','trip_reviewed_after','login_navigate','login_auth_redirect','login_origin_check','login_form_check','login_legacy_link','login_legacy_retry','login_legacy_redirect','login_email','login_password','login_submit','login_app_redirect']);
const loginErrors=new Set(['login_form_timeout','login_form_ambiguous','login_legacy_link_ambiguous','login_legacy_link_invalid','login_legacy_redirect_loop']);
function failureDiagnostic(error) {
 const proof=tripDiagnostics.diagnostic(error);
 if(proof)return proof;
 // Only static categories escape the browser. Never serialize error messages or URLs.
 const network=/^(?:page\.(?:goto|reload): )?net::ERR_(CONNECTION_RESET|CONNECTION_CLOSED|TIMED_OUT|NETWORK_CHANGED)(?:\s|$)/.exec(error?.message||'');
 return {phase:diagnosticPhases.has(currentPhase)?currentPhase:'other',
  error_kind:network?'network_'+network[1].toLowerCase():error?.name==='TimeoutError'?'browser_timeout':error?.message==='login_origin'?'unexpected_login_origin':loginErrors.has(error?.message)?error.message:'unclassified'};
}
function failed(output,error) {
 // The supervisor reads only this bounded classification, never raw browser errors.
 console.log(JSON.stringify({stage:'collection_failure_diagnostic',...failureDiagnostic(error)}));
 atomic(output+'.failure.json',{retryable:transient(error),reason:safeReason(error),phase:currentPhase});
}
module.exports={phase,openTasks,retry,transient,safeReason,atomic,failed};

async function closeBrowser(browser,{timeoutMs=3000}={}) {
 let timer;
 try {await Promise.race([browser.close(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('browser_cleanup_failed')),timeoutMs);})]);}
 finally {clearTimeout(timer);}
}
module.exports.closeBrowser=closeBrowser;

module.exports.failureDiagnostic=failureDiagnostic;
