const {test}=require('node:test');const assert=require('node:assert/strict');
const {HEADERS,dates,reportUrl,verifyUrl,number,duration,readings,validateSnapshot,finalizeReport,safeFailure}=require('./collect_fuel.cjs');
const vehicle={provider_vehicle_id:'1234',unit:'06'},date='2026-10-07';
const cells={vehicle:'06','driving-fuel':'0.0','idle-fuel':'--','total-fuel':'0.0','total-distance':'1,234.50','driving-time':'0m','idle-time':'—'};
const snapshot=()=>({url:reportUrl(date,'1234'),headers:[...HEADERS],visible_date_text:'Oct 7',selected_unit:'06',rows:[{...cells}],explicit_empty:false});
test('conservative date windows cross month and noon UTC cutoff',()=>{
 assert.deepEqual(dates(new Date('2026-10-01T11:59:59Z')),['2026-09-27','2026-09-28','2026-09-29']);
 assert.deepEqual(dates(new Date('2026-10-01T12:00:00Z')),['2026-09-28','2026-09-29','2026-09-30']);
 for(const x of [0,8,1.2,NaN])assert.throws(()=>dates(new Date(),x),/invalid_days/);
});
test('report URL binds exact provider and date with no extra or duplicated filters',()=>{
 assert.doesNotThrow(()=>verifyUrl(reportUrl(date,'1234'),date,'1234'));
 for(const url of [reportUrl(date,'123'),reportUrl('2026-10-06','1234'),reportUrl(date,'1234')+';vehicle_ids=1234',reportUrl(date,'1234')+';driver_ids=8',reportUrl(date,'1234').replace('app.gomotive.com','evil.test')])assert.throws(()=>verifyUrl(url,date,'1234'),/report_identity_changed/);
});
test('blank is unknown and explicit zero is preserved',()=>{
 assert.equal(number('--'),null);assert.equal(number(''),null);assert.equal(number('0.0'),'0.0');assert.equal(number('1,234.500'),'1234.500');
 for(const value of ['NaN','1e2','-1','2,00','1 gallon','1.1234'])assert.throws(()=>number(value),/invalid_numeric/);
});
test('durations preserve zero, missing and source outliers',()=>{
 assert.equal(duration('0m'),0);assert.equal(duration('--'),null);assert.equal(duration('30h 5m'),108300);assert.equal(duration('1h 2m 3s'),3723);
 for(const value of ['today','-3m','1h rubbish',''])if(value)assert.throws(()=>duration(value),/invalid_duration/);
});
test('named columns prevent positional group-cell shifts',()=>{
 assert.deepEqual(readings(cells),{driving_fuel_gallons:'0.0',idling_fuel_gallons:null,reported_total_fuel_gallons:'0.0',source_distance_miles:'1234.50',source_driving_seconds:0,source_idling_seconds:null});
 assert.throws(()=>readings({...cells,'driving-fuel':undefined}),/layout_changed/);
});
test('visible filters and exact leading zeros must match',()=>{
 for(const change of [{selected_unit:'6'},{visible_date_text:'Oct 6'},{rows:[{...cells,vehicle:'6'}]}])assert.throws(()=>validateSnapshot({...snapshot(),...change},date,vehicle));
 assert.equal(validateSnapshot({...snapshot(),headers:HEADERS.map(x=>x.toLowerCase())},date,vehicle),true);
});
test('loading is not explicit empty; duplicate rows cannot complete',()=>{
 assert.equal(validateSnapshot({...snapshot(),rows:[]},date,vehicle),null);
 assert.throws(()=>finalizeReport({...snapshot(),rows:[]},date,vehicle,'2026-10-08T13:00:00Z'),/incomplete/);
 assert.throws(()=>validateSnapshot({...snapshot(),rows:[cells,cells]},date,vehicle),/not_single_vehicle/);
 assert.throws(()=>validateSnapshot({...snapshot(),explicit_empty:true},date,vehicle),/ambiguous_empty/);
});
test('explicit empty emits source missing receipt while zero is reported',()=>{
 const stamp='2026-10-08T13:00:00Z';const a=finalizeReport(snapshot(),date,vehicle,stamp);
 assert.equal(a.record.state,'reported');assert.equal(a.record.driving_fuel_gallons,'0.0');assert.equal(a.report.provider_vehicle_id,'1234');assert.equal(a.report.filter_start,date);assert.equal(a.report.row_count,1);
 const b=finalizeReport({...snapshot(),rows:[],explicit_empty:true},date,vehicle,stamp);assert.equal(b.record.state,'source_missing');assert.equal(b.report.row_count,0);assert.equal(b.report.explicit_empty,true);
});
test('all-null fuel row remains missing even with distance data',()=>{
 const s=snapshot();s.rows[0]={...cells,'driving-fuel':'--','total-fuel':'—'};const out=finalizeReport(s,date,vehicle,'2026-10-08T13:00:00Z');assert.equal(out.record.state,'source_missing');assert.equal(out.record.reason,'fuel_readings_missing');assert.equal(out.report.row_count,1);assert.equal(out.record.source_distance_miles,'1234.50');
});
test('layout revisions and raw browser errors fail closed',()=>{
 assert.throws(()=>validateSnapshot({...snapshot(),headers:HEADERS.slice(1)},date,vehicle),/layout_changed/);
 assert.equal(safeFailure(Error('locator fill password secret')),'browser_collection_unavailable');
});

test('incomplete filter controls wait without accepting stale data',()=>{
 for(const change of [{headers:[]},{selected_unit:null},{visible_date_text:null}]){const s={...snapshot(),...change};assert.equal(validateSnapshot(s,date,vehicle),null);assert.throws(()=>finalizeReport(s,date,vehicle,'2026-10-08T13:00:00Z'),/incomplete/);}
 assert.throws(()=>validateSnapshot({...snapshot(),selected_unit:'7'},date,vehicle),/filter_changed/);
});
