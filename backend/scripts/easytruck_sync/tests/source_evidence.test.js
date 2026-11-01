const assert = require('node:assert/strict');
const test = require('node:test');
const {extractSourceEvidence} = require('../lib/invoice_json');
test('keeps provider evidence, drops private arbitrary fields, does not assert settlement', () => {
 const value = extractSourceEvidence(JSON.stringify({props:{secret:'token',service:{id:12,number:12,int_id:99,completed_at:'2026-10-07T07:00:00.000Z',notes:'private',invoice:{id:34,number:456,service_id:99,payment_lines:[{id:56,payment:{id:78,date:'2026-10-07T07:00:00.000Z',qb_reference:'123',notes:'private',token:'secret'}}]}}}}));
 assert.equal(value.payment_lines[0].payment.id,78);
 assert.equal(value.payment_lines[0].payment.date_source,'2026-10-07T07:00:00.000Z');
 assert.equal(value.settlement_semantics,'unverified');
 assert.ok(!JSON.stringify(value).includes('private'));
 assert.ok(!JSON.stringify(value).includes('secret'));
});
test('malformed and oversized input are bounded',()=>{
 assert.equal(extractSourceEvidence('bad'),null);
 const v=extractSourceEvidence(JSON.stringify({props:{service:{id:12,number:12,int_id:99,invoice:{service_id:99,payment_lines:Array(201).fill({})}}}}));
 assert.equal(v.payment_lines.length,200);assert.equal(v.payment_lines_truncated,true);
});

test('rejects mismatched internal service linkage',()=>{
 assert.equal(extractSourceEvidence(JSON.stringify({props:{service:{id:12,number:12,int_id:99,invoice:{id:34,service_id:98}}}})),null);
});

test('receipt marker allowlist drops all surrounding notes and rejects ambiguity',()=>{
 const {receiptReference}=require('../lib/invoice_json');
 const id='ABCDEF01-2345-6789-ABCD-EF0123456789';
 assert.equal(receiptReference({notes:`Private customer note DBN-RECEIPT:${id}`}),`DBN-RECEIPT:${id.toLowerCase()}`);
 assert.equal(receiptReference({notes:`DBN-RECEIPT:${id} DBN-RECEIPT:00000000-0000-0000-0000-000000000001`}),null);
 assert.equal(receiptReference({notes:`DBN-RECEIPT:${id}bad`}),null);
 const value=extractSourceEvidence(JSON.stringify({props:{service:{id:12,number:12,int_id:99,invoice:{id:34,service_id:99,payment_lines:[{payment:{notes:`PRIVATE DBN-RECEIPT:${id}`,date:'2026-10-07T07:00:00Z'}}]}}}}));
 assert.equal(value.payment_lines[0].payment.dbn_receipt_reference,`DBN-RECEIPT:${id.toLowerCase()}`);
 assert.ok(!JSON.stringify(value).includes('PRIVATE'));
});

test('only genuine explicit UTC calendar datetimes receive verified UTC semantics',()=>{
 const {paymentDateSemantics}=require('../lib/invoice_json');
 for(const value of ['2026-10-07T07:00:00Z','2026-10-07T07:00:00.000000+00:00']) assert.equal(paymentDateSemantics(value),'source_datetime_utc');
 for(const value of ['2026-02-30T07:00:00Z','2026-10-07','2026-10-07T07:00:00','2026-10-07T07:00:00-04:00','2026-10-07T24:00:00Z']) assert.equal(paymentDateSemantics(value),'source_datetime_unverified');
});

test('customer proof comes only from exact embedded invoice association without PII',()=>{
 const page={component:'services/show/invoice',props:{service:{id:'1821',number:'1821',int_id:506423,customer:{id:97052,uuid:'02104722-a300-48a5-ba98-0eab3b2fb32e',deleted:false,name:'PRIVATE',email:'SECRET'},invoice:{id:468019,service_id:506423}}}};
 const result=extractSourceEvidence(JSON.stringify(page));
 assert.equal(result.source_customer_id,'97052');assert.equal(result.source_customer_uuid,page.props.service.customer.uuid);
 assert.equal(result.source_customer_binding_kind,'embedded_service_customer');assert.equal(result.source_customer_deleted,false);
 assert.ok(!('source_customer_internal_id' in result));assert.ok(!JSON.stringify(result).match(/PRIVATE|SECRET/));
 page.component='parts/index';assert.equal(extractSourceEvidence(JSON.stringify(page)),null);
 delete page.component;assert.ok(!('source_customer_id' in extractSourceEvidence(JSON.stringify(page))));
 page.component='services/show/invoice';delete page.props.service.customer.uuid;
 assert.ok(!('source_customer_id' in extractSourceEvidence(JSON.stringify(page))));
});
