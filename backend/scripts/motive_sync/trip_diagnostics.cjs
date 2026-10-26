/* Static browser-proof diagnostics only. Never serialize exceptions or DOM strings. */
const PHASES={
 report_empty_picker_click_failed:'empty_picker_click',
 report_empty_picker_wait_failed:'empty_picker_wait',
 report_empty_date_proof_unavailable:'empty_date_validation',
 report_empty_date_proof_mismatch:'empty_date_validation',
};
const COUNTS=['picker_count','overlay_count','label_count','title_count','selected_count'];
const FLAGS=['loading','header_valid','selected_day_valid','adjacent_month','label_matches'];
function isoDay(value) {
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
 const stamp=Date.parse(value+'T00:00:00Z');return Number.isFinite(stamp)&&new Date(stamp).toISOString().slice(0,10)===value;
}
function structural(value) {
 const result={};
 if(!value||typeof value!=='object')return result;
 for(const key of COUNTS)if(Number.isInteger(value[key])&&value[key]>=0)result[key]=Math.min(21,value[key]);
 for(const key of FLAGS)if(typeof value[key]==='boolean')result[key]=value[key];
 for(const key of ['selected_start','selected_end'])if(isoDay(value[key]))result[key]=value[key];
 return result;
}
function category(error) {return Object.hasOwn(PHASES,error?.message)?error.message:null;}
function diagnostic(error) {
 const code=category(error);
 return code?{phase:PHASES[code],error_kind:code,structure:structural(error.tripProofStructure)}:null;
}
function proofError(code,structure,cause) {
 if(!Object.hasOwn(PHASES,code))throw new Error('invalid_trip_proof_category');
 const error=new Error(code);
 // Preserve existing bounded transient handling without retaining raw cause text.
 if(cause?.name==='TimeoutError'||/^(?:page\.(?:goto|reload): )?net::ERR_(CONNECTION_RESET|CONNECTION_CLOSED|TIMED_OUT|NETWORK_CHANGED)(?:\s|$)/.test(cause?.message||''))error.name='TimeoutError';
 error.tripProofStructure=structural(structure);
 return error;
}
module.exports={category,diagnostic,proofError,structural};
