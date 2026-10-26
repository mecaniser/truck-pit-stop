'use strict';
// Closed vocabulary only: never emit provider values or exception text.
const PHASES=new Set(['navigation','header','capture','empty_proof','populated_proof','viewport','finalize']);
const REASONS=new Set(['transport','status','content_type','declared_body_limit','decoded_body_limit','body_timeout','json','root_shape','total_changed','record_shape','id_invalid','vehicle_id_invalid','timestamp_invalid','outside_day','duplicate_id','duplicate_identity','dom_identity_invalid','bijection_mismatch','request_failed','response_limit','no_matching_response','pending_response','incomplete_tail','dom_count_mismatch','rendered_count_mismatch']);
const COUNTS=['observed_requests','provider_requests','unbound_provider_requests','matched_requests','responses','pending','decoded_pages','authoritative_total','response_identities','dom_rows','rendered_count'];
const FIELDS=['total','per_page','driving_periods','record','id','vehicle','vehicle_id','start_time'];
const TYPES=new Set(['missing','null','array','object','string','number','boolean','other']);
function type(value){return value===undefined?'missing':value===null?'null':Array.isArray(value)?'array':['object','string','number','boolean'].includes(typeof value)?typeof value:'other';}
function sanitize(value){const out={};if(!value||typeof value!=='object')return out;
 if(PHASES.has(value.phase))out.phase=value.phase;if(REASONS.has(value.reason))out.reason=value.reason;
 for(const k of COUNTS)if(Number.isSafeInteger(value[k])&&value[k]>=0)out[k]=Math.min(value[k],1000000);
 if(value.fields&&typeof value.fields==='object'){out.fields={};for(const k of FIELDS)if(TYPES.has(value.fields[k]))out.fields[k]=value.fields[k];}
 return out;}
function attach(error,value){if(error&&typeof error==='object')error.tripPopulatedDiagnostic=Object.freeze((()=>{const out=sanitize(value);if(out.fields)Object.freeze(out.fields);return out;})());return error;}
module.exports={sanitize,attach,type};
