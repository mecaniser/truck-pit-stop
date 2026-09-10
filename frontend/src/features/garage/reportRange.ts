export const REPORT_PRESETS = {
  this_week: 'This week', last_week: 'Last week',
  this_month: 'This month', last_month: 'Last month',
  this_quarter: 'This quarter', last_quarter: 'Last quarter',
  this_year: 'This year', last_year: 'Last year',
} as const
export type ReportPreset = keyof typeof REPORT_PRESETS
export type ReportRange = { range: ReportPreset } | { range: 'custom'; from_date: string; to_date: string }
export type ResolvedRange = { range_start: string; range_end: string }

export function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value < '0001-01-01') return false
  const date = new Date(`${value}T12:00:00Z`)
  return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value
}

export function rangeError(from: string, to: string): string | null {
  if (!validDate(from) || !validDate(to)) return 'Enter a valid start and end date.'
  if (from > to) return 'End date must be on or after start date.'
  return null
}

export function readReportRange(params: URLSearchParams): ReportRange {
  const range = params.get('range')
  const from = params.get('from_date') || ''
  const to = params.get('to_date') || ''
  if (range === 'custom' && !rangeError(from, to)) return { range, from_date: from, to_date: to }
  if (range && Object.prototype.hasOwnProperty.call(REPORT_PRESETS, range)) return { range: range as ReportPreset }
  return { range: 'this_month' }
}

export function formatReportDate(value: string): string {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
}
