const test=require('node:test');
const assert=require('node:assert/strict');
const {parseRanges,classify,validateDirectory,parseSummary,safeReason}=require('./collect.cjs');
const ranges=parseRanges('Performance ranges\nFair\nGood\nExcellent\nFair 50 – 84 Good 85 – 95 Excellent 96 – 100');
const snapshot=()=>({safety_lines:['Safety Score','SEP 28, 2026 - OCT 4, 2026','82','Top behaviors impacting score','Close following','-9','Stop sign violation','-4.7','Speeding','-4'],coaching_annotation:true,fuel_text:'Fuel performance LAST 30 DAYS 41.4% UTILIZATION Summary Active time 68h 14m Idle time 96h 26m',coaching_text:'Driver needs coaching Never coached 4',event_headers:['DATE (MDY EDT) / LOCATION','VEHICLE ID / MMY','STATUS','BEHAVIOR / SEVERITY'],events:[['Oct 9, 2026, 2:29 PM\n—','01\nFRHT 2019','Pending review','Stop sign violation\nN/A']]});
test('Motive source ranges determine bands, including exact boundaries',()=>{
 assert.deepEqual([50,84,85,95,96,100].map(s=>classify(s,ranges).band),['red','red','yellow','yellow','green','green']);
 assert.equal(classify(null,ranges).band,'unknown');assert.equal(classify(0,ranges).band,'unknown');
 const changed=parseRanges('Fair 50-66 Good 67-83 Excellent 84-100');assert.equal(classify(84,changed).band,'green');
});
test('rejects missing duplicate overlapping gapped and reordered source ranges',()=>{
 for(const text of ['Fair 50-84 Good 85-95','Fair 50-85 Good 85-95 Excellent 96-100','Fair 50-84 Good 86-95 Excellent 96-100','Good 50-84 Fair 85-95 Excellent 96-100','Fair 0-84 Good 85-95 Excellent 96-100'])assert.throws(()=>parseRanges(text));
});
test('parses source summary without treating graph coaching annotation as band',()=>{
 const data=parseSummary(snapshot(),ranges);assert.equal(data.safety.score,82);assert.equal(data.safety.band,'red');assert.equal(data.safety.band_label,'Fair (50–84)');assert.equal(data.safety.coaching_label,'Coaching');
 assert.deepEqual(data.safety.top_behaviors.map(b=>b.score_impact),[-9,-4.7,-4]);assert.equal(data.fuel.utilization_percent,41.4);assert.equal(data.fuel.active_time_text,'68h 14m');assert.equal(data.coaching.open_count,4);assert.equal(data.recent_events[0].location,null);assert.equal(data.recent_events[0].severity,null);assert.equal(data.coverage,'partial');
});
test('preserves explicit zero and unknown readings independently',()=>{
 const source=snapshot();source.safety_lines[2]='0';source.fuel_text='Fuel performance LAST 30 DAYS 0% UTILIZATION Active time 0h 0m Idle time 0h 0m';
 const value=parseSummary(source,ranges);assert.equal(value.safety.score,0);assert.equal(value.safety.band,'unknown');assert.equal(value.fuel.utilization_percent,0);
 const missing=parseSummary({},ranges);assert.equal(missing.sections.safety,'unavailable');assert.equal(missing.sections.fuel,'unavailable');assert.equal(missing.sections.recent_events,'unavailable');
});
test('ambiguous scores are unavailable and malformed impact/event rows fail',()=>{
 const a=snapshot();a.safety_lines.splice(2,0,'100');assert.equal(parseSummary(a,ranges).sections.safety,'unavailable');
 const b=snapshot();b.safety_lines.push('Unexpected metric');assert.throws(()=>parseSummary(b,ranges));
 const c=snapshot();c.events[0][0]='unknown time';assert.throws(()=>parseSummary(c,ranges));
});
const directory=()=>({headers:['DRIVER NAME / ID','VEHICLE ID'],footer:'Showing 2 of 2',rows:[{driver_href:'#/fleetview/drivers/summary/1',driver_name:'Sample Driver',vehicle_href:'#/fleetview/vehicles/summary/9',unit:'9'},{driver_href:'#/fleetview/drivers/summary/2',driver_name:'Unassigned Driver',vehicle_href:null,unit:null}]});
test('directory joins stable provider identities in the same source row',()=>{const data=validateDirectory(directory());assert.equal(data[0].provider_driver_id,'1');assert.equal(data[0].provider_vehicle_id,'9');assert.equal(data[1].provider_vehicle_id,null);});
test('rejects incomplete duplicate and ambiguous assignment directories',()=>{
 const a=directory();a.footer='Showing 2 of 3';assert.throws(()=>validateDirectory(a));
 const b=directory();b.rows[1].driver_href=b.rows[0].driver_href;assert.throws(()=>validateDirectory(b));
 const c=directory();c.rows[1].vehicle_href=c.rows[0].vehicle_href;assert.throws(()=>validateDirectory(c));
 const d=directory();d.rows[0].driver_href='https://attacker.invalid/driver/1';assert.throws(()=>validateDirectory(d));
});
test('error logging never emits provider content or credentials',()=>{assert.equal(safeReason(new Error('secret driver payload')),'driver_collection_failed');});

test('complete empty directory remains valid to clear provider assignment projection',()=>{assert.deepEqual(validateDirectory({headers:['DRIVER NAME / ID','VEHICLE ID'],footer:'Showing 0 of 0',rows:[]}),[]);});
