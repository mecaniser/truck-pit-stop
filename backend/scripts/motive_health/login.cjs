/* Health retains its reviewed policy and diagnostic names. */
const {prepareLoginContext}=require('../motive_sync/login_context.cjs');
function prepareHealthLogin(browser,options={}){
 return prepareLoginContext(browser,{...options,recoveryStage:'health_login_context_recovery',recoveredStage:'health_login_context_recovered'});
}
module.exports={prepareHealthLogin};
