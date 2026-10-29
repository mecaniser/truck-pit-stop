/* Immutable daily import subprocess boundary. No retry after any child ambiguity. */
const {spawnSync}=require('node:child_process');
const fs=require('node:fs');
function readPrivate(file){const stat=fs.lstatSync(file);if(stat.isSymbolicLink()||!stat.isFile()||(stat.mode&0o077)||stat.size>32*1024*1024)throw Error('fuel_plan_invalid');return JSON.parse(fs.readFileSync(file,'utf8'));}
function closed(day,now){if(typeof day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(day))return false;const parsed=new Date(`${day}T00:00:00Z`);return Number.isFinite(+parsed)&&parsed.toISOString().slice(0,10)===day&&+parsed+36*3600000<=+now;}
function validatePlan(plan,now=new Date(),env=process.env){
 const scope=plan?.scope;
 if(plan?.version!==1||!scope||scope.tenant_id!==env.MOTIVE_SYNC_TENANT_ID||scope.actor_id!==env.MOTIVE_SYNC_ACTOR_ID||scope.company_id!==env.MOTIVE_COMPANY_ID||scope.company_label!==env.MOTIVE_COMPANY_LABEL||scope.baseline!==(env.MOTIVE_FUEL_BASELINE||'2026-08-15')||scope.date_policy!=='unverified_zone_conservative_v1'||!['automatic','explicit'].includes(plan.mode)||!/^[-0-9a-f]{36}$/.test(plan.run_id||''))throw Error('fuel_plan_invalid');
 const created=new Date(plan.created_at);
 if(!Number.isFinite(+created)||+created>+now||+now-+created>1800000||!Array.isArray(plan.days)||plan.days.length<1||plan.days.length>7||new Set(plan.days).size!==plan.days.length||plan.days.some(day=>day<scope.baseline||!closed(day,created)))throw Error('fuel_plan_invalid');
 return plan.days;
}
function finalizeDay(source,planPath,day,assertFresh,spawn=spawnSync){
 assertFresh();
 const preparing=process.env.MOTIVE_FUEL_PREPARE_ONLY==='true';
 const command=['-m','scripts.motive_sync.fuel_day','--input',source,'--plan',planPath,'--day',day,...(preparing?['--prepare-only']:[])];
 // The import child validates the actual exact receipt before returning zero.
 // Then an independent read-only child validates it again at the boundary.
 for(const verify of [false,true]){
  const result=spawn(process.env.MOTIVE_FUEL_PYTHON||'python',verify?[...command,'--verify-only']:command,{timeout:600000,stdio:['ignore','ignore','ignore']});
  if(result.error||result.signal||result.status!==0)throw Error('fuel_day_unverified');
 }
 assertFresh();
 console.log(JSON.stringify({stage:preparing?'fuel_day_prepared':'fuel_day_committed',day}));
}
module.exports={readPrivate,closed,validatePlan,finalizeDay};
