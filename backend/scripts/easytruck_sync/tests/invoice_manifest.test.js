const test = require('node:test');
const assert = require('node:assert/strict');
const {mergeInvoicePages} = require('../lib/invoice_manifest');
function page() { return {component:'invoices/index',props:{user:{current_shop_public_id:'sh_test',current_shop_id:1},filters:{status:'all',range:'all',search:''},invoices:{meta:{current_page:1,last_page:1,total:1},data:[{id:2,type:'SERVICE',service_id:3,service:{id:4,number:4,int_id:3,shop_id:1}}]}}}; }
test('full unfiltered identity-bound enumeration supplies manifest',()=>{assert.deepEqual(mergeInvoicePages([page()],'sh_test')['4'].invoice_ids,['2']);});
for (const kind of ['filtered','duplicate','missing','shop','service']) test(`holds ${kind} enumeration`,()=>{
 const p=page();
 if(kind==='filtered')p.props.filters.status='paid';
 if(kind==='duplicate')p.props.invoices.data.push(p.props.invoices.data[0]);
 if(kind==='missing')p.props.invoices.meta.total=2;
 if(kind==='shop')p.props.user.current_shop_public_id='other';
 if(kind==='service')p.props.invoices.data[0].service_id=999;
 assert.throws(()=>mergeInvoicePages([p],'sh_test'));
});

test('standalone SALE invoices count toward coverage but never repair identity',()=>{ const p=page();p.props.invoices.meta.total=2;p.props.invoices.data.push({id:5,type:'SALE',service:null}); assert.equal(Object.keys(mergeInvoicePages([p],'sh_test')).length,1);});
test('missing service on unknown type cannot be ignored',()=>{ const p=page();p.props.invoices.data[0]={id:2,type:'OTHER',service:null}; assert.throws(()=>mergeInvoicePages([p],'sh_test'));});
const {applyCurrentManifest,invalidateCachedService} = require('../lib/invoice_manifest');
test('cached positive is removed before current detail read, including failures',()=>{
 const results={'4':{sourceEvidence:{invoice_manifest:{complete:true}}}};
 invalidateCachedService(results,'4');
 assert.equal(results['4'],undefined);
});
test('missing service or failed current enumeration invalidates old complete manifest',()=>{
 const evidence={service_internal_id:3,invoice_manifest:{complete:true,invoice_ids:['2']}};
 for(const manifests of [{}, {'other':{complete:true}}]) {
  const result=applyCurrentManifest(evidence,manifests,'4','2026-10-15T12:00:00Z');
  assert.equal(result.invoice_manifest,null);
  assert.equal(result.observed_at_source,'2026-10-15T12:00:00Z');
 }
});
