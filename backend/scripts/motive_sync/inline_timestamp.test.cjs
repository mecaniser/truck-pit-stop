const assert=require('node:assert/strict');
const {test,before,after}=require('node:test');
const {chromium}=require('playwright');
const {readInlineLocationTimestamp,stableObservation,speedFromParts}=require('./collect.cjs');
const DATE='Oct 13, 2026, 5:34 PM';
const row=(date=DATE,extra='')=>`<div class="d-flex align-items-center phx-web-type-body-medium grey-70 ng-star-inserted"><i class="clock"></i><span class="upper-case ng-star-inserted" ${extra}>${date}</span></div>`;
const control='<div class="container mt-4 pos-relative"><span class="grey-70 regular-14">Synthetic location</span><button phxcontent="Copy coordinates">Copy</button></div>';
const location=(body=row()+control)=>`<div class="current-location mt-8-imp">${body}</div>`;
const panel=body=>`<section class="driver-location-info">${body}</section>`;
let browser;
before(async()=>{browser=await chromium.launch({headless:true});});
after(async()=>{await browser?.close();});
async function fixture(html,fn){
 const context=await browser.newContext({timezoneId:'America/New_York',locale:'en-US'});
 await context.route('**/*',route=>route.abort());
 const page=await context.newPage();
 await page.setContent(`<style>.upper-case{text-transform:uppercase}</style>${html}`);
 try{return await fn(page);}finally{await context.close();}
}
test('grounded visible current-location date owns the same unique coordinate control',async()=>{
 for(const date of [DATE,'OCT 13, 2026, 5:34 PM','Oct  13,\n2026, 5:34 pm']){
  await fixture(panel(location(row(date)+control)),async page=>{
   const value=await readInlineLocationTimestamp(page);
   assert.equal(value.rawTimestamp,DATE);assert.equal(value.timestampBasis,'inline_location');assert.equal(value.timestampReason,null);
   const reading=await stableObservation({timestamp:()=>readInlineLocationTimestamp(page),point:async()=>[35,-80],verifyVin:async()=>{},address:null,speed:async()=>speedFromParts('40','MPH')});
   assert.equal(reading.precision,'minute');assert.equal(reading.speed_mph,null);assert.equal(reading.speedReason,'speed_timestamp_location_only');
  });
 }
});
test('grounded provider date plus EDT retains exact source text and matches NY minute',async()=>{
 for(const [date,expected]of [['Oct 13, 2026, 5:34 PM','2026-10-13T21:34:00.000Z'],['Oct 28, 2026, 5:05 PM','2026-10-28T21:05:00.000Z'],['Oct 29, 2026, 9:37 PM','2026-10-30T01:37:00.000Z'],['Jan 13, 2026, 5:34 PM','2026-01-13T22:34:00.000Z']]){
  const source=date+(date.startsWith('Jan')?' EST':' EDT');
  await fixture(panel(location(row(source)+control))+'<footer>Account timezone America/New_York EST</footer>',async page=>{
   const timestamp=await readInlineLocationTimestamp(page);
   assert.equal(timestamp.rawTimestamp,date);assert.equal(timestamp.timestampSourceText,source);
   const reading=await stableObservation({timestamp:()=>readInlineLocationTimestamp(page),point:async()=>[35,-80],verifyVin:async()=>{},address:null});
   assert.equal(reading.observed_minute_start,expected);assert.equal(reading.timestampSourceText,source);assert.equal(reading.speed_mph,null);
  });
 }
});
test('a disconnected banner outside current-location never becomes its date',async()=>{
 await fixture(`<div>Disconnected ${row('Oct 1, 2026, 1:00 PM')}${panel(location())}</div>`,async page=>{
  assert.equal((await readInlineLocationTimestamp(page)).rawTimestamp,DATE);
 });
});
const rejected={
 'date outside location':panel(row()+location(control)),
 'no location coordinate owner':panel(location(row())+control),
 'two global coordinate controls':panel(location())+control,
 'two current-location blocks':panel(location()+location()),
 'two panels':panel(location())+panel(location()),
 'last connected sibling in clock row':panel(location(row().replace('<i class="clock"></i>','<i class="clock"></i><span>Last connected</span>')+control)),
 'device updated sibling in clock row':panel(location(row().replace('<i class="clock"></i>','<i class="clock"></i><span>Device updated</span>')+control)),
 'text label in clock row':panel(location(row().replace('<i class="clock"></i>','<i class="clock"></i>Updated ')+control)),
 'summer EST mismatch':panel(location(row(DATE+' EST')+control)),
 'winter EDT mismatch':panel(location(row('Jan 13, 2026, 5:34 PM EDT')+control)),
 'unsupported timezone':panel(location(row(DATE+' UTC')+control)),
 'extra timezone label':panel(location(row(DATE+' EDT EST')+control)),
 'timezone outside leaf':panel(location(row().replace('</div>','<span> EDT</span></div>')+control)),
 'two owned clocks':panel(location(row()+row()+control)),
 'another owned absolute date':panel(location(row()+control+`<b>Oct 2, 2026, 5:34 PM</b>`)),
 'disconnected event in location':panel(location(row()+control+'<b>Disconnected</b>')),
 'last updated event in location':panel(location(row()+control+'<b>Last updated</b>')),
 'last seen event in location':panel(location(row()+control+'<b>Last seen</b>')),
 'status widget takes precedence':panel(location(row()+control+'<span class="current-location-status">Stationary</span>')),
 'hidden date':panel(location(row(DATE,'style="display:none"')+control)),
 'transparent date':panel(location(row(DATE,'style="opacity:0"')+control)),
 'hidden location':panel(location().replace('current-location mt-8-imp','current-location mt-8-imp" style="visibility:hidden')),
 'relative date':panel(location(row('Yesterday at 5:34 PM')+control)),
 'missing year':panel(location(row('Oct 13, 5:34 PM')+control)),
 'label substring':panel(location(row('Last updated '+DATE)+control)),
 'unreviewed structure':panel(location(row().replace('grey-70','grey-60')+control)),
 'nested clock label':panel(location(row(`<span>${DATE}</span>`)+control)),
};
for(const [name,html]of Object.entries(rejected))test(`reject ${name} as an authoritative inline timestamp`,async()=>{
 await fixture(html,async page=>{
  const value=await readInlineLocationTimestamp(page);
  assert.equal(value.rawTimestamp,null);assert.ok(value.timestampReason);assert.equal(value.timestampBasis,undefined);
  const reading=await stableObservation({timestamp:()=>readInlineLocationTimestamp(page),point:async()=>[35,-80],verifyVin:async()=>{},address:null});
  assert.equal(reading.precision,'unknown');assert.equal(reading.observed_at,null);assert.equal(reading.observed_minute_start,null);
 });
});
test('hidden duplicate templates do not create a second rendered clock',async()=>{
 await fixture(panel(location(row()+row('Oct 2, 2026, 1:00 PM','style="display:none"')+control)),async page=>{
  assert.equal((await readInlineLocationTimestamp(page)).rawTimestamp,DATE);
 });
});
test('ambiguous DST and invalid calendar dates never become known time',async()=>{
 for(const date of ['Nov 1, 2026, 1:30 AM','Mar 8, 2026, 2:30 AM','Feb 30, 2026, 5:34 PM','Nov 1, 2026, 1:30 AM EDT','Nov 1, 2026, 1:30 AM EST','Mar 8, 2026, 2:30 AM EST','Feb 30, 2026, 5:34 PM EST']){
  await fixture(panel(location(row(date)+control)),async page=>{
   const value=await stableObservation({timestamp:()=>readInlineLocationTimestamp(page),point:async()=>[35,-80],verifyVin:async()=>{},address:null});
   assert.equal(value.precision,'unknown');assert.equal(value.observed_at,null);assert.equal(value.observed_minute_start,null);
  });
 }
});
test('changed owned date, coordinates or provider identity fail the existing stable-read gate',async()=>{
 await fixture(panel(location()),async page=>{
  let reads=0;
  await assert.rejects(stableObservation({timestamp:async()=>{const value=await readInlineLocationTimestamp(page);if(!reads++)await page.locator('span.upper-case').evaluate(el=>{el.textContent='Oct 14, 2026, 5:34 PM';});return value;},point:async()=>[35,-80],verifyVin:async()=>{},address:null}),/^Error: source_changed_during_capture$/);
  let n=0;
  await assert.rejects(stableObservation({timestamp:()=>readInlineLocationTimestamp(page),point:async()=>[35+n++,-80],verifyVin:async()=>{},address:null}),/source_changed/);
  await assert.rejects(stableObservation({timestamp:()=>readInlineLocationTimestamp(page),point:async()=>[35,-80],verifyVin:async()=>{throw new Error('vin_changed');},address:null}),/vin_changed/);
 });
});

test('same canonical date with changed exact source text fails stability',async()=>{
 await fixture(panel(location(row(DATE+' EDT')+control)),async page=>{
  let reads=0;
  await assert.rejects(stableObservation({timestamp:async()=>{const value=await readInlineLocationTimestamp(page);if(!reads++)await page.locator('span.upper-case').evaluate(el=>{el.textContent='OCT 13, 2026, 5:34 PM EDT';});return value;},point:async()=>[35,-80],verifyVin:async()=>{},address:null}),/^Error: source_changed_during_capture$/);
 });
});
