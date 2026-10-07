const test=require('node:test'),assert=require('node:assert/strict');
const {parseCard,parseCount,validateCounts,validateInventory,safeReason}=require('./collect.cjs');
const detail=(spn='00123',occurrence='0')=>`SPN ${spn} FMI 03 · Test circuit condition
First detected on Sep 25, 2026
High
Hide details
Test circuit condition
Network
J1939
Source address
11 · Test controller
First detected
Sep 25, 2026, 5:50 AM
Last observed
Oct 7, 2026, 6:59 PM
Occurrence count
${occurrence}`;
test('expanded detail preserves code strings, unknown event timestamps, and explicit zero occurrence',()=>{
 const p=parseCard('Current fault codes\n'+detail(),1);assert.equal(p.explicit_empty,false);assert.equal(p.codes.length,1);
 assert.equal(p.codes[0].spn,'00123');assert.equal(p.codes[0].fmi,'03');assert.equal(p.codes[0].occurrence_count,0);assert.equal(p.codes[0].last_observed_at,null);assert.equal(p.codes[0].timestamp_precision,'unknown');assert.equal(p.codes[0].timezone_basis,'unverified');assert.equal(p.codes[0].source_status,'Current fault codes');assert.equal(p.codes[0].provider_fault_id,null);
 assert.equal(parseCard('Current fault codes\n'+detail('00123','—'),1).codes[0].occurrence_count,null);
});
test('multiple cards and literal timestamps retained; mismatched and duplicate cards reject',()=>{
 const p=parseCard('Current fault codes\n'+detail()+'\n'+detail('00456','17'),2);assert.equal(p.codes.length,2);assert.equal(p.codes[1].occurrence_count,17);
 assert.throws(()=>parseCard('Current fault codes\n'+detail()+'\n'+detail(),2),/duplicate/);
 assert.throws(()=>parseCard('Current fault codes\n'+detail(),2),/details/);
 assert.throws(()=>parseCard('Current fault codes\n'+detail().replace('Hide details','Show details'),1),/details/);
});
test('zero means explicit current-code empty only; missing cannot be manufactured as healthy',()=>{
 const empty=parseCard('Current fault codes\nNo fault codes',0);assert.deepEqual(validateCounts(0,0,empty),{explicit_empty:true,codes:[]});
 for(const text of ['Current fault codes','No fault codes','Current fault codes\nLoading'])assert.throws(()=>parseCard(text,0));
 assert.throws(()=>validateCounts(4,2,parseCard('Current fault codes\n'+detail()+'\n'+detail('00456'),2)),/count_mismatch/);
 assert.throws(()=>validateCounts(0,1,empty),/count_mismatch/);
});
test('health directory count and exact table headers guard pagination and ambiguity',()=>{
 const s={headers:['VEHICLE OR ASSET','AVAILABILITY','DEFECTS','FAULT CODES','NEXT SERVICE','',''],footer:'Showing 1 of 2',rows:[{href:'#/fleetview/vehicles/summary/1',unit:'01',count:'2'}]};
 assert.deepEqual(validateInventory(s),{shown:1,expected:2});
 assert.throws(()=>validateInventory(s,3),/changed/);
 assert.throws(()=>validateInventory({...s,rows:[...s.rows,...s.rows]}),/duplicate/);
 assert.throws(()=>validateInventory({...s,headers:s.headers.slice(1)}),/layout/);
 assert.throws(()=>parseCount('—'),/unavailable/);assert.throws(()=>parseCount('-1'),/unavailable/);
});
test('failure logs never expose unknown browser errors',()=>{assert.equal(safeReason(new Error('password secret')),'health_data_unavailable');assert.equal(safeReason({name:'TimeoutError'}),'ui_timeout');});
test('missing field values never consume the next diagnostic label',()=>{
 const blank=detail().replace('Source address\n11 · Test controller','Source address\n').replace('First detected\nSep 25, 2026, 5:50 AM','First detected\n').replace('Last observed\nOct 7, 2026, 6:59 PM','Last observed\n');
 const code=parseCard('Current fault codes\n'+blank,1).codes[0];
 assert.equal(code.source_address,null);assert.equal(code.first_detected_text,null);assert.equal(code.last_observed_text,null);assert.equal(code.occurrence_count,0);assert.equal(code.timestamp_precision,'unknown');
});
