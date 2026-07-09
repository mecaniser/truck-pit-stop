/**
 * Format a decimal-hours value as "Xh Ym" (e.g. 2.5 -> "2h 30m", 0.25 -> "15m",
 * 3 -> "3h"). Book/labor time is stored as decimal hours but reads ambiguously
 * ("2.5" — 2.5 of what?), so we display the elapsed time instead.
 *
 * Minutes are rounded to the nearest whole minute; if rounding rolls up to a
 * full hour it carries into the hours part. Zero/invalid input renders "0m".
 */
export function formatHoursMinutes(value: number | string | null | undefined): string {
  const decimal = typeof value === 'number' ? value : parseFloat(value || '0')
  if (!Number.isFinite(decimal) || decimal <= 0) return '0m'

  let hours = Math.floor(decimal)
  let minutes = Math.round((decimal - hours) * 60)
  if (minutes === 60) {
    hours += 1
    minutes = 0
  }

  if (hours > 0 && minutes > 0) return `${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h`
  return `${minutes}m`
}
