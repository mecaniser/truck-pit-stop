/* Sync opts into bounded anonymous recovery before credentials are filled. */
const {prepareLoginContext}=require('./login_context.cjs');
function prepareSyncLogin(browser,options={}){
 return prepareLoginContext(browser,{...options,recoveryStage:'sync_login_context_recovery',recoveredStage:'sync_login_context_recovered'});
}
module.exports={prepareSyncLogin};
