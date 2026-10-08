/** Provider report totals are independent of trip estimates and trip timestamps. */
export interface FuelDaily {
  vehicle_id: string
  report_date: string
  source_timezone: string | null
  timezone_status: 'unverified' | 'verified'
  driving_fuel_gallons: number | null
  idling_fuel_gallons: number | null
  reported_total_fuel_gallons: number | null
  source_distance_miles: number | null
  source_driving_seconds: number | null
  source_idling_seconds: number | null
}
export interface FuelDailyResponse {
  items: FuelDaily[]; total: number; offset: number; limit: number
  start_date: string; end_date: string
  date_basis: 'source_report_date'
  coverage: 'partial'
}
const shift = (day: string, n: number) => new Date(Date.parse(`${day}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10)
export async function loadFuelRange(start: string, end: string, fetchPage: (start: string, end: string, offset: number) => Promise<FuelDailyResponse>): Promise<FuelDaily[]> {
  const span = (Date.parse(end) - Date.parse(start)) / 86400000
  if (!Number.isFinite(span) || span < 0 || span >= 366) throw new Error('Invalid fuel range')
  const rows: FuelDaily[] = []
  const keys = new Set<string>()
  for (let cursor = start; cursor <= end;) {
    const last = shift(cursor, 30) < end ? shift(cursor, 30) : end
    let offset = 0
    let expected: number | null = null
    do {
      const page = await fetchPage(cursor, last, offset)
      if (!Number.isInteger(page.total) || page.total < 0 || page.total > 100000 || page.offset !== offset || !Array.isArray(page.items) || page.date_basis !== 'source_report_date' || (expected !== null && page.total !== expected)) throw new Error('Fuel report changed; retry')
      expected = page.total
      if (offset < expected && !page.items.length) throw new Error('Incomplete fuel report')
      for (const row of page.items) {
        const key = `${row.vehicle_id}:${row.report_date}`
        if (keys.has(key) || row.report_date < cursor || row.report_date > last || !row.vehicle_id || [row.driving_fuel_gallons, row.idling_fuel_gallons, row.reported_total_fuel_gallons, row.source_distance_miles, row.source_driving_seconds, row.source_idling_seconds].some(value => value !== null && (!Number.isFinite(value) || value < 0))) throw new Error('Invalid fuel report row')
        keys.add(key); rows.push(row)
      }
      offset += page.items.length
      if (offset > expected) throw new Error('Fuel totals did not reconcile')
    } while (offset < expected)
    cursor = shift(last, 1)
  }
  return rows
}
export function summarizeFuel(rows: FuelDaily[], vehicleId?: string, start?: string, end?: string) {
  const records = rows.filter(row => (!vehicleId || row.vehicle_id === vehicleId) && (!start || row.report_date >= start) && (!end || row.report_date <= end))
  if (!records.length) return null
  const sum = (key: 'driving_fuel_gallons' | 'idling_fuel_gallons' | 'reported_total_fuel_gallons' | 'source_distance_miles') => {
    const values = records.flatMap(row => row[key] === null ? [] : [row[key]!])
    return values.length ? values.reduce((total, value) => total + value, 0) : null
  }
  return {
    driving: sum('driving_fuel_gallons'), idling: sum('idling_fuel_gallons'), total: sum('reported_total_fuel_gallons'), miles: sum('source_distance_miles'),
    days: new Set(records.map(row => row.report_date)).size,
    drivingDays: new Set(records.filter(row => row.driving_fuel_gallons !== null).map(row => row.report_date)).size,
    idlingDays: new Set(records.filter(row => row.idling_fuel_gallons !== null).map(row => row.report_date)).size,
    timezone: records.every(row => row.timezone_status === 'verified' && row.source_timezone === records[0].source_timezone) ? records[0].source_timezone : null,
    first: records.map(row => row.report_date).sort()[0],
    last: records.map(row => row.report_date).sort()[records.length - 1],
  }
}

/** Median of per-truck period totals; missing components do not count as zero. */
export function medianFuel(rows: FuelDaily[], vehicleIds: string[]) {
  const summaries = [...new Set(vehicleIds)].map(id => summarizeFuel(rows, id))
  const component = (key: 'driving' | 'idling') => {
    const values = summaries.flatMap(fuel => fuel?.[key] == null ? [] : [fuel[key]!]).sort((a, b) => a - b)
    const mid = Math.floor(values.length / 2)
    return { value: values.length ? values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2 : null, count: values.length }
  }
  return { driving: component('driving'), idling: component('idling') }
}
