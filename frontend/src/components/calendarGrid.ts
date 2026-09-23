/* Date-only calendar arithmetic, shared by the single-date DatePicker and the
   reporting range picker. Every value here is an ISO `YYYY-MM-DD` day string,
   never a Date: a date-only value has no time zone, and constructing a local
   Date from one is what silently shifts a PM due date across midnight. Where a
   Date is unavoidable (weekday, month name) it is built at noon UTC and read
   back with UTC accessors, so no local offset can move the day. */

export function isoToday(now: Date = new Date()) {
  return now.toISOString().slice(0, 10)
}

export function validDay(day: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(day) && !Number.isNaN(Date.parse(`${day}T12:00:00Z`))
}

function noonUTC(day: string) {
  return new Date(`${day}T12:00:00Z`)
}

export function shiftDay(day: string, amount: number) {
  const date = noonUTC(day)
  date.setUTCDate(date.getUTCDate() + amount)
  return date.toISOString().slice(0, 10)
}

export function shiftMonth(month: string, amount: number) {
  const date = new Date(`${month}-01T12:00:00Z`)
  date.setUTCMonth(date.getUTCMonth() + amount)
  return date.toISOString().slice(0, 7)
}

export function monthOf(day: string) {
  return day.slice(0, 7)
}

export function monthLabel(month: string) {
  return noonUTC(`${month}-01`).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/** Accessible day name, and the label the user reads in the trigger. */
export function formatDay(day: string) {
  if (!validDay(day)) return ''
  return noonUTC(day).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function daysInMonth(month: string) {
  return new Date(new Date(`${shiftMonth(month, 1)}-01T12:00:00Z`).valueOf() - 86400000).getUTCDate()
}

/** Monday-first column index for the 1st of the month. */
export function leadingBlanks(month: string) {
  return (noonUTC(`${month}-01`).getUTCDay() + 6) % 7
}

export function daysOf(month: string) {
  return Array.from(
    { length: daysInMonth(month) },
    (_, i) => `${month}-${String(i + 1).padStart(2, '0')}`,
  )
}

/** String compare is correct ordering for zero-padded ISO days. */
export function outOfRange(day: string, min?: string, max?: string) {
  if (min && day < min) return true
  if (max && day > max) return true
  return false
}

export const WEEKDAY_LABELS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'] as const
