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
    const main = document.querySelector('main');
    if (!main) return { state: 'unavailable', rows: [] };
    // Other UI panels include placeholder tables. Only the report's Origin-header table owns rows.
    const tables = Array.from(main.querySelectorAll('table')).filter(table => Array.from(table.querySelectorAll('th')).some(el => /^Origin \(MDY (?:EDT|EST)\)$/i.test(el.innerText.trim())));
    if (tables.length !== 1) return {state: tables.length ? 'unavailable' : 'loading', rows: []};
    const table = tables[0];
    const headers = Array.from(table.querySelectorAll('th')).map(el => el.innerText.trim());
    const body = main.innerText;
    const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr => {
      const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
      // Deliberately exclude driver identity and notes from capture.
      return { cells: cells.slice(0, 5), links: Array.from(tr.querySelectorAll('a[href*="/fleetview/vehicles/summary/"]')).map(a => a.getAttribute('href')) };
    }).filter(row => row.cells.length && row.cells.some(cell => cell.trim()));
    return { url: location.href, state: body.includes('No trips found. Try updating your filter/search criteria.') ? 'empty' : rows.length ? 'rows' : 'loading', headers, rows, footer: body.match(/Showing [\d,]+ results/)?.[0] ?? null };
  });
}

/** One step is intentionally bounded; caller persists the returned receipt after every step.
 * Stagnation never means all history was imported: it yields partial for operator review.
 */
export async function captureStep(page, receipt, { maxRows = 20000, verifiedTimezone = null } = {}) {
  const report = await readReport(page);
  if (report.state === 'unavailable') throw new Error('Motive report unavailable: check login');
  if (report.state === 'loading') return { ...receipt, status: 'loading' };
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
    if (receipt.rows.length) throw new Error('Source became empty during collection');
    return { ...receipt, source_read_at: new Date().toISOString(), status: 'empty', header_timezone: zone, terminal_evidence: 'No trips found. Try updating your filter/search criteria.' };
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

/** Completion requires independently observed source total, not scroll stagnation. */
export function finalizeWindow(receipt, expectedTotal, countEvidence) {
  if (!Number.isInteger(expectedTotal) || expectedTotal < 0 || !countEvidence?.trim()) throw new Error('Source count evidence required');
  if (receipt.status === 'empty' && expectedTotal === 0 && receipt.rows.length === 0) return {...receipt, expected_total: 0, footerShown: 0, terminal_evidence: countEvidence};
  const shown = Number(receipt.footer?.match(/^Showing ([\d,]+) results$/)?.[1]?.replaceAll(',', ''));
  const identities = new Set(receipt.rows.map(row => JSON.stringify([row.links, row.cells[1]?.split('\n')[0]])));
  if (identities.size !== receipt.rows.length) throw new Error('Conflicting or ambiguous source identities');
  if (receipt.status !== 'partial' || receipt.rows.length !== expectedTotal || shown !== expectedTotal) throw new Error('Incomplete source window');
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
