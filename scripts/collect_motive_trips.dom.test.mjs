/** Run after frontend npm ci: uses the existing jsdom dependency, no browser/auth. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readReport,reportUrl} from './collect_motive_trips.mjs';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {JSDOM}=require('jsdom');

test('grounded calendar wrapper topology extracts date and rejects adjacent or duplicate selection',async()=>{
 const dom=new JSDOM(`
 <main><phx-filter-row data-e2e="trips-filter-row"><phx-date-picker data-testid="date-picker">
 <div class="phx-date-picker-range-labels"><span class="phx-date-picker-label">Apr 1</span></div>
 </phx-date-picker></phx-filter-row>
 <table><thead><tr>${['','Origin (MDY EDT)','Destination (MDY EDT)','Dist. (mi) / Duration','Vehicle ID / Mode','Driver / ID','','Notes',''].map(text=>`<th>${text}</th>`).join('')}</tr></thead><tbody></tbody></table>
 No trips found. Try updating your filter/search criteria.</main>
 <div id="module-loading-spinner" style="display:none"></div>
 <div class="cdk-overlay-pane phx-date-picker-overlay-pane"><div class="phx-date-picker">
 <div class="main" cdktrapfocus><div class="phx-menu-header-body-wrapper"><div class="phx-header-body-wrapper">
 <phx-date-picker-header><div class="phx-date-picker-header-label"><span>Apr&nbsp;</span><span>2026</span></div></phx-date-picker-header>
 <phx-date-picker-body><div class="phx-date-picker-body-date-wrapper"><span class="phx-date-picker-body-date-cell-active-selected"> 1 <!--calendar--><div class="phx-date-event-container"></div></span></div></phx-date-picker-body>
 </div></div></div></div></div>`,{url:reportUrl('2026-04-01','2026-04-01')});
 // jsdom has no layout or innerText; model visibility only, leaving its actual
 // CSS selector engine and exact live ancestor structure untouched.
 const {window}=dom;
 Object.defineProperty(window.HTMLElement.prototype,'innerText',{get(){return this.textContent;}});
 window.HTMLElement.prototype.getBoundingClientRect=function(){return {width:30,height:20};};
 const prior={document:globalThis.document,location:globalThis.location,getComputedStyle:globalThis.getComputedStyle};
 Object.assign(globalThis,{document:window.document,location:window.location,getComputedStyle:window.getComputedStyle.bind(window)});
 try {
  assert.equal(window.document.querySelector('.phx-date-picker > phx-date-picker-header'),null);
  const p={evaluate:async fn=>fn()};
  assert.deepEqual((await readReport(p)).selected_dates,{kind:'visible_date_controls',start:'2026-04-01',end:'2026-04-01'});
  const selected=window.document.querySelector('.phx-date-picker-body-date-cell-active-selected');
  selected.classList.add('phx-date-picker-body-date-cell-prev-next-month');
  assert.equal((await readReport(p)).selected_dates,null);
  selected.classList.remove('phx-date-picker-body-date-cell-prev-next-month');
  selected.after(selected.cloneNode(true));
  assert.equal((await readReport(p)).selected_dates,null);
 } finally {Object.assign(globalThis,prior);window.close();}
});
