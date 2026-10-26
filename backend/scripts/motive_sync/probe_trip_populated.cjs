'use strict';
// Explicit read-only release canary: never invoke collect(), importDay or a DB client.
const {prepareLegacyLogin}=require('./login.cjs');
const {collectWindow}=require('./collect_trips.cjs');
const {spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const path=require('node:path'),fs=require('node:fs');
const ORIGIN='https://app.gomotive.com',COMPANY='77 CARGO LLC',ID='KT8934277';
async function main(){
 let browser,timer,stage='preflight';
 try{
  const day=process.argv[3];
  if(process.argv[2]!=='--read-only'||!/^\d{4}-\d\d-\d\d$/.test(day||'')||new Date(day+'T00:00:00Z').toISOString().slice(0,10)!==day||process.env.MOTIVE_COMPANY_ID!==ID||process.env.MOTIVE_COMPANY_LABEL!==COMPANY||!process.env.MOTIVE_SYNC_TENANT_ID||!process.env.MOTIVE_SYNC_ACTOR_ID||!process.env.MOTIVE_EMAIL||!process.env.MOTIVE_PASSWORD)throw Error('preflight');
  timer=setTimeout(()=>{console.log(JSON.stringify({kind:'trip_populated_canary',failed:true,stage:'deadline',import_permitted:false}));process.exit(1);},300000);
  stage='dependencies';const {chromium}=require('playwright');
  stage='browser';browser=await chromium.launch({headless:true});const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US',acceptDownloads:false});const control=await context.newPage();control.setDefaultTimeout(15000);
  stage='login';await control.goto(ORIGIN,{waitUntil:'domcontentloaded',timeout:45000});await control.waitForURL('https://auth.gomotive.com/login**',{timeout:30000});
  if(new URL(control.url()).origin!=='https://auth.gomotive.com')throw Error('origin');await prepareLegacyLogin(control,{phase:()=>{}});
  if(new URL(control.url()).origin!=='https://auth.gomotive.com')throw Error('origin');
  await control.locator('input[name="user_profile[email]"]').fill(process.env.MOTIVE_EMAIL);await control.locator('input[name="user_profile[password]"]').fill(process.env.MOTIVE_PASSWORD);await control.getByRole('button',{name:'Log in',exact:true}).click();await control.waitForURL('https://app.gomotive.com/**',{timeout:45000});
  async function gates(){
   await control.goto(ORIGIN+'/en-US/#/admin/company',{waitUntil:'domcontentloaded',timeout:45000});await control.getByText(/KT8934277/).waitFor({timeout:30000});const text=await control.locator('body').innerText();if(new URL(control.url()).origin!==ORIGIN||!text.includes(ID)||!text.includes(COMPANY))throw Error('company');
   await control.goto(ORIGIN+'/en-US/#/settings',{waitUntil:'domcontentloaded',timeout:45000});await control.getByText(/Eastern Time - New York/).waitFor({timeout:30000});const zone=await control.getByText('Time zone',{exact:true}).evaluate(e=>e.parentElement.innerText);if(new URL(control.url()).origin!==ORIGIN||!zone.includes('Eastern Time - New York'))throw Error('timezone');
  }
  stage='gates_before';await gates();
  const installed=path.resolve(__dirname,'../../collectors/collect_motive_trips.mjs');const adapter=await import(pathToFileURL(fs.existsSync(installed)?installed:path.resolve(__dirname,'../../../scripts/collect_motive_trips.mjs')).href);
  const report=await context.newPage();report.setDefaultTimeout(15000);stage='populated_capture';
  const window=await collectWindow(report,{start:day,end:day},async()=>{},adapter);
  if(window.status!=='captured'||!window.populated_proof)throw Error('populated_required');
  stage='python_proof';
  const validated=spawnSync(process.env.MOTIVE_TRIPS_PYTHON||'python',['-c','import json,sys; from scripts.motive_sync.trip_populated_proof import valid_populated_proof; sys.exit(0 if valid_populated_proof(json.load(sys.stdin)) else 1)'],{input:JSON.stringify(window),encoding:'utf8',timeout:10000,maxBuffer:4096});
  if(validated.status!==0||validated.error)throw Error('python_proof');
  stage='gates_after';await gates();
  console.log(JSON.stringify({kind:'trip_populated_canary',day,read_only:true,import_permitted:false,company_verified_before:true,company_verified_after:true,python_validated:true,proof_version:window.populated_proof.version,total:window.populated_proof.total,captured:window.rows.length,response_count:window.populated_proof.response_count,identity_count:window.populated_proof.response_identity_count}));
 }catch{console.log(JSON.stringify({kind:'trip_populated_canary',failed:true,stage,import_permitted:false}));process.exitCode=1;}
 finally{try{if(browser)await browser.close();}finally{clearTimeout(timer);}}
}
if(require.main===module)main();
