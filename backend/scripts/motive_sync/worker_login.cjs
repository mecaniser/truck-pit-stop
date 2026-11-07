/* Daily collectors reuse the already-reviewed native/legacy login flow. */
const {prepareHealthLogin}=require('../motive_health/login.cjs');
const WORKERS=new Set(['trips','fuel','drivers']);
const STAGES=Object.freeze({
 health_login_context_recovery:'login_context_recovery',
 health_login_context_recovered:'login_context_recovered',
 health_login_lookup_recovery:'login_lookup_recovery',
 health_login_lookup_recovered:'login_lookup_recovered',
});
function prepareWorkerLogin(browser,{worker,...options}={}){
 if(!WORKERS.has(worker))throw new Error('login_worker_invalid');
 const diagnostic=options.diagnostic??(stage=>console.log(JSON.stringify({stage})));
 return prepareHealthLogin(browser,{...options,diagnostic:stage=>diagnostic(STAGES[stage]?`${worker}_${STAGES[stage]}`:stage)});
}
module.exports={prepareWorkerLogin};
