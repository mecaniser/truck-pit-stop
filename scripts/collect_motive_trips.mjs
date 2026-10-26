import populatedProof from '../backend/scripts/motive_sync/trip_populated_proof.cjs';
import tripDiagnostics from '../backend/scripts/motive_sync/trip_diagnostics.cjs';
/** Motive's rendered Trips report collector. Inject an authenticated browser adapter.
 * No cookies, passwords, hidden application state or undocumented API requests.
 * Designed for Codex CUA (tab.playwright + nativeTab.scroll), or a Playwright page.
 */
export function reportUrl(start, end) {
  for (const value of [start, end]) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value) throw new Error('Invalid date');
  }
  if (start > end || (Date.parse(end) - Date.parse(start)) / 86400000 > 30) throw new Error('Use windows of at most 31 days');
  return `https://app.gomotive.com/en-US/#/fleetview/list/trips/trips;sort_field=start_time;sort_direction=desc;start_date=${start};end_date=${end};driving_period_start_date=${end}`;
}

export async function readReport(page) {
  return page.evaluate(() => {
    const visible = el => Boolean(el && el.getBoundingClientRect().width > 0
      && el.getBoundingClientRect().height > 0 && getComputedStyle(el).visibility !== 'hidden'
      && getComputedStyle(el).display !== 'none');
    const main = document.querySelector('main');
    if (!main) return { state: 'unavailable', rows: [] };
    // Other UI panels include placeholder tables. Only the report's Origin-header table owns rows.
    const tables = Array.from(main.querySelectorAll('table')).filter(table => Array.from(table.querySelectorAll('th')).some(el => /^Origin \(MDY (?:EDT|EST)\)$/i.test(el.innerText.trim())));
    if (tables.length !== 1) return {state: tables.length ? 'unavailable' : 'loading', rows: []};
    const table = tables[0];
    const headers = Array.from(table.querySelectorAll('th')).map(el => el.innerText.trim());
    const body = main.innerText;
    // Grounded on the live Trips page: this loader remains in the DOM with a
    // hidden class after settling. Its existence alone is not a loading signal.
    const spinner = document.querySelector('#module-loading-spinner');
    const loading = visible(spinner);
    // Grounded read-only calendar controls on the live Trips report (2026-10-26).
    // Never borrow a year from the URL or a neighboring month cell.
    const pickers = Array.from(document.querySelectorAll('phx-filter-row[data-e2e="trips-filter-row"] phx-date-picker[data-testid="date-picker"]')).filter(visible);
    const overlays = Array.from(document.querySelectorAll('.cdk-overlay-pane.phx-date-picker-overlay-pane')).filter(visible);
    let selected_dates = null;
    const proof_structure={picker_count:pickers.length,overlay_count:overlays.length,loading};
    if (pickers.length === 1 && overlays.length === 1) {
      const labels = Array.from(pickers[0].querySelectorAll('.phx-date-picker-range-labels .phx-date-picker-label')).filter(visible);
      const titles = Array.from(overlays[0].querySelectorAll('.phx-date-picker phx-date-picker-header .phx-date-picker-header-label')).filter(visible);
      const days = Array.from(overlays[0].querySelectorAll('phx-date-picker-body .phx-date-picker-body-date-wrapper span.phx-date-picker-body-date-cell-active-selected')).filter(visible);
      Object.assign(proof_structure,{label_count:labels.length,title_count:titles.length,selected_count:days.length});
      if (days.length===1)proof_structure.adjacent_month=days[0].classList.contains('phx-date-picker-body-date-cell-prev-next-month');
      if (labels.length === 1 && titles.length === 1 && days.length === 1
          && !days[0].classList.contains('phx-date-picker-body-date-cell-prev-next-month')) {
        const title = titles[0].innerText.replace(/\s+/g, ' ').trim().match(/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{4})$/);
        const day = Array.from(days[0].childNodes).filter(node => node.nodeType === 3).map(node => node.textContent).join('').trim();
        const collapsed = labels[0].innerText.replace(/\s+/g, ' ').trim();
        Object.assign(proof_structure,{header_valid:Boolean(title),selected_day_valid:/^(?:[1-9]|[12]\d|3[01])$/.test(day),label_matches:Boolean(title && collapsed===`${title[1]} ${Number(day)}`)});
        if (title && /^(?:[1-9]|[12]\d|3[01])$/.test(day) && collapsed === `${title[1]} ${Number(day)}`) {
          const month = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].indexOf(title[1]) + 1;
          const value = `${title[2]}-${String(month).padStart(2,'0')}-${day.padStart(2,'0')}`;
          if (new Date(`${value}T00:00:00Z`).toISOString().slice(0,10) === value)
            selected_dates = {kind:'visible_date_controls', start:value, end:value};
        }
      }
    }
    if(selected_dates)Object.assign(proof_structure,{selected_start:selected_dates.start,selected_end:selected_dates.end});
    const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr => {
      const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
      // Deliberately exclude driver identity and notes from capture.
      return { cells: cells.slice(0, 5), links: Array.from(tr.querySelectorAll('a[href*="/fleetview/vehicles/summary/"]')).map(a => a.getAttribute('href')) };
    }).filter(row => row.cells.length && row.cells.some(cell => cell.trim()));
    return { url: location.href, loading, selected_dates, proof_structure, date_picker_available:pickers.length===1, date_overlay_count:overlays.length, state: body.includes('No trips found. Try updating your filter/search criteria.') ? 'empty' : rows.length ? 'rows' : 'loading', headers, rows, footer: body.match(/Showing [\d,]+ results/)?.[0] ?? null };
  });
}

/** One step is intentionally bounded; caller persists the returned receipt after every step.
 * Stagnation never means all history was imported: it yields partial for operator review.
 */
export async function captureStep(page, receipt, { maxRows = 20000, verifiedTimezone = null, now = () => new Date() } = {}) {
  let report = await readReport(page);
  if (report.state === 'empty' && report.loading === false && report.date_picker_available === true && report.date_overlay_count === 0) {
    if (new URL(report.url).origin !== 'https://app.gomotive.com' || !new URL(report.url).hash.startsWith('#/fleetview/list/trips/trips;')) throw new Error('Unexpected source page');
    // Opening the existing picker only exposes its selected date; do not select,
    // apply or change any filter. No retry loop or new authentication is introduced.
    try {await page.locator('phx-filter-row[data-e2e="trips-filter-row"] phx-date-picker[data-testid="date-picker"] .phx-date-picker-selector').click({timeout:5000});}
    catch(error){throw tripDiagnostics.proofError('report_empty_picker_click_failed',report.proof_structure,error);}
    try {await page.locator('.cdk-overlay-pane.phx-date-picker-overlay-pane').waitFor({state:'visible',timeout:5000});}
    catch(error){throw tripDiagnostics.proofError('report_empty_picker_wait_failed',report.proof_structure,error);}
    report = await readReport(page);
  }
  if (report.state === 'unavailable') throw new Error('Motive report unavailable: check login');
  if (report.state === 'loading' || report.loading === true) return { ...receipt, status: 'loading' };
  const zone = report.headers?.[1]?.match(/^Origin \(MDY (EDT|EST)\)$/i)?.[1]?.toUpperCase();
  if (zone === 'EST' && verifiedTimezone !== 'America/New_York') throw new Error('New York timezone verification required');
  const expectedHeaders = ['', `Origin (MDY ${zone})`, `Destination (MDY ${zone})`, 'Dist. (mi) / Duration', 'Vehicle ID / Mode', 'Driver / ID', '', 'Notes', ''];
  const clean = value => value.replace(/\s+/g, ' ').trim().toLowerCase();
  if (JSON.stringify(report.headers?.map(clean)) !== JSON.stringify(expectedHeaders.map(clean))) throw new Error('Motive table layout or timezone changed');
  if (!zone) throw new Error('Motive table layout or timezone changed');
  if (receipt.header_timezone && receipt.header_timezone !== zone) throw new Error('Report timezone changed during collection');
  const actual = new URL(report.url);
  if (actual.origin !== 'https://app.gomotive.com' || !actual.hash.startsWith('#/fleetview/list/trips/trips;')) throw new Error('Unexpected source page');
  const filters = Object.fromEntries(actual.hash.split(';').slice(1).map(part => part.split('=')));
  if (filters.start_date !== receipt.start || filters.end_date !== receipt.end || Object.keys(filters).some(key => !['sort_field', 'sort_direction', 'start_date', 'end_date', 'driving_period_start_date'].includes(key))) throw new Error('Source filters do not match requested window');
  if (report.state === 'empty') {
    if (receipt.rows.length || report.rows.length) throw new Error('Source became empty during collection');
    const dates=report.selected_dates;
    if(report.loading!==false||!dates||dates.kind!=='visible_date_controls')throw tripDiagnostics.proofError('report_empty_date_proof_unavailable',report.proof_structure);
    if(dates.start!==receipt.start||dates.end!==receipt.end)throw tripDiagnostics.proofError('report_empty_date_proof_mismatch',report.proof_structure);
    return { ...receipt, source_read_at: now().toISOString(), status: 'empty', header_timezone: zone,
      empty_observation:{selected_start:dates.start,selected_end:dates.end,date_evidence_kind:dates.kind,loading_absent:true},
      terminal_evidence: 'No trips found. Try updating your filter/search criteria.' };
  }
  const rowKey = row => {
    // The live elapsed-duration clock is not a new trip revision. Preserve the first
    // raw observation; completed rows and every other ongoing field remain immutable.
    if (row.cells[2]?.split('\n')[0] === 'IN PROGRESS') {
      const cells = [...row.cells];
      cells[3] = cells[3]?.replace(/(?:\d+h\s*)?(?:\d+m\s*)?\d+s$/, '<ongoing-duration>');
      return JSON.stringify({...row, cells});
    }
    return JSON.stringify(row);
  };
  const seen = new Map(receipt.rows.map(row => [rowKey(row), row]));
  for (const row of report.rows) if (!seen.has(rowKey(row))) seen.set(rowKey(row), row);
  if (seen.size > maxRows) throw new Error('Collection row limit reached');
  return { ...receipt, source_read_at: new Date().toISOString(), status: 'partial', header_timezone: zone, rows: [...seen.values()], last_page_rows: report.rows.length, footer: report.footer, stagnant_steps: seen.size === receipt.rows.length ? (receipt.stagnant_steps ?? 0) + 1 : 0 };
}

export function newWindow(start, end) {
  reportUrl(start, end);
  return { start, end, source_read_at: new Date().toISOString(), status: 'partial', rows: [], stagnant_steps: 0 };
}

export function validEmptyProof(receipt) {
 const p=receipt.empty_proof;
 if(!p)return false;
 const elapsed=Date.parse(p.last_observed_at)-Date.parse(p.first_observed_at);
 return p.version===1&&p.date_evidence_kind==='visible_date_controls'&&
  p.selected_start===receipt.start&&p.selected_end===receipt.end&&p.loading_absent===true&&
  Number.isInteger(p.observations)&&p.observations>=13&&p.observations<=120&&
  elapsed>=9000&&elapsed<=120000&&p.last_observed_at===receipt.source_read_at;
}

/** Completion requires independently observed source total, not scroll stagnation. */
export function finalizeWindow(receipt, expectedTotal, countEvidence) {
  if (!Number.isInteger(expectedTotal) || expectedTotal < 0 || !countEvidence?.trim()) throw new Error('Source count evidence required');
  if (receipt.status === 'empty' && expectedTotal === 0 && receipt.rows.length === 0 && validEmptyProof(receipt)) return {...receipt, expected_total: 0, footerShown: 0, terminal_evidence: countEvidence};
  const shown = Number(receipt.footer?.match(/^Showing ([\d,]+) results$/)?.[1]?.replaceAll(',', ''));
  const identities = new Set(receipt.rows.map(row => JSON.stringify([row.links, row.cells[1]?.split('\n')[0]])));
  if (identities.size !== receipt.rows.length) throw new Error('Conflicting or ambiguous source identities');
  if (receipt.status !== 'partial' || receipt.rows.length !== expectedTotal || shown !== expectedTotal) throw new Error('Incomplete source window');
  if (!populatedProof.validProof(receipt)) throw new Error('Populated response identity proof required');
  return {...receipt, status: 'captured', expected_total: expectedTotal, footerShown: shown, terminal_evidence: countEvidence};
}

/** Caller supplies the already-authorized CUA page and a private checkpoint writer.
 * Native scrolling advances the observed report without opening or editing trips.
 * Each call is bounded so a scheduler can checkpoint, report failure, and resume.
 */
export async function advance(page, nativeTab, receipt, checkpoint) {
  receipt = await captureStep(page, receipt);
  await checkpoint(receipt);
  if (receipt.status === 'empty') return receipt;
  if ((receipt.stagnant_steps ?? 0) >= 12) throw new Error('Source stopped advancing; window remains partial');
  await nativeTab.scroll([600, 600], 'down', 10000);
  receipt = await captureStep(page, receipt);
  await checkpoint(receipt);
  return receipt;
}
