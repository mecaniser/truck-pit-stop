/* Reuse the reviewed native-form flow; preserve location-specific diagnostics. */
const {prepareHealthLogin}=require('../motive_health/login.cjs');
const STAGES=Object.freeze({
 health_login_context_recovery:'sync_login_context_recovery',
 health_login_context_recovered:'sync_login_context_recovered',
 health_login_lookup_recovery:'sync_login_lookup_recovery',
 health_login_lookup_recovered:'sync_login_lookup_recovered',
});
function prepareSyncLogin(browser,options={}){
 const diagnostic=options.diagnostic??(stage=>console.log(JSON.stringify({stage})));
 return prepareHealthLogin(browser,{...options,diagnostic:stage=>diagnostic(STAGES[stage]??stage)});
}
module.exports={prepareSyncLogin};
