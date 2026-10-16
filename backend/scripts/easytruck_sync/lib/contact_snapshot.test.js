const test = require('node:test');
const assert = require('node:assert/strict');
const {contactSnapshot} = require('./contact_snapshot');
const options = {shop:'shop_test',customerId:'123',observedAt:'2026-10-16T00:00:00Z'};
const view = () => ({pathname:'/shop_test/customers/123/contacts',searchValue:'',archived:false,
  headerBound:true,headerPhones:['7045551234'],headers:['ROLE','FIRST NAME','LAST NAME','PHONE','EMAIL','NOTES'],
  rows:[['Owner','','','7045555678','','']],footer:'Showing 1 to 1 of 1 results',hasNext:false});
test('fresh bounded complete page includes bound account header and table phones', () => {
  assert.deepEqual(contactSnapshot(view(), options).phones, ['7045551234','7045555678']);
  assert.equal(contactSnapshot(view(), options).complete, true);
});
for (const [name,change,reason] of [
  ['wrong account',{pathname:'/shop_test/customers/999/contacts'},'account_mismatch'],
  ['filtered',{searchValue:'driver'},'filtered'], ['archived',{archived:true},'filtered'],
  ['missing filter proof',{archived:null},'filtered'],
  ['pagination',{footer:'Showing 1 to 1 of 2 results',hasNext:true},'page_incomplete'],
  ['missing footer',{footer:''},'page_incomplete'],
  ['unbound header',{headerBound:false},'schema_unsupported'],
  ['truncated columns',{rows:[['Owner']]},'schema_unsupported'],
]) test(name, () => {
  const result=contactSnapshot({...view(),...change},options);
  assert.equal(result.complete,false); assert.equal(result.reason,reason); assert.deepEqual(result.phones,[]);
});
test('explicit zero footer and no current phones is a complete removal', () => {
  const result=contactSnapshot({...view(),rows:[],headerPhones:[],footer:'Showing 0 to 0 of 0 results'},options);
  assert.equal(result.complete,true); assert.deepEqual(result.phones,[]);
});
