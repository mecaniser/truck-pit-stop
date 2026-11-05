/* Fixed diagnostic categories only; never retain page content or source values. */
const STAGES=new Set(['new_page','goto_summary','wait_live_link','vin_presence_wait','route_check','read_summary','cleanup']);
const ROUTES=new Set(['expected_summary','other_app_route','unexpected_origin','about_blank','unavailable']);
const proofs=new WeakMap();
function attach(error,metadata) {
 try {
  if(error&&(typeof error==='object'||typeof error==='function')&&STAGES.has(metadata?.step)&&ROUTES.has(metadata?.route))
   proofs.set(error,Object.freeze({identity_step:metadata.step,identity_route:metadata.route}));
 }catch{} // Observation must never replace the source error, including frozen errors.
 return error;
}
function diagnostic(error) {try{return proofs.get(error)||null;}catch{return null;}}
function observe(options,step) {
 try {
  if(STAGES.has(step)&&typeof options?.onStage==='function')Promise.resolve(options.onStage(step)).catch(()=>{});
 }catch{} // A callback is observational and cannot change collection or retry policy.
}
function route(page,href) {
 try {
  const raw=page.url();if(raw==='about:blank')return 'about_blank';
  const url=new URL(raw);if(url.origin!=='https://app.gomotive.com')return 'unexpected_origin';
  return url.pathname==='/en-US/'&&!url.search&&!url.username&&!url.password&&url.hash===href?'expected_summary':'other_app_route';
 }catch{return 'unavailable';}
}
module.exports={attach,diagnostic,observe,route};
