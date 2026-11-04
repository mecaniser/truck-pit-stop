import { format, isValid, parseISO } from 'date-fns'

/** Invoice calendar dates include legacy UTC-midnight wire values; other timestamps retain instant semantics. */
export function formatCalendarDate(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const legacyCalendarDate = /^(\d{4}-\d{2}-\d{2})T00:00:00(?:\.0+)?(?:Z|\+00:00)$/.exec(value)
  const date = parseISO(legacyCalendarDate?.[1] || value)
  return isValid(date) ? format(date, 'MMM d, yyyy') : 'Unavailable'
}
