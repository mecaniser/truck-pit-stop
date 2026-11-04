import { format } from 'date-fns'
import { describe, expect, it } from 'vitest'
import { formatCalendarDate } from '../calendarDate'

describe('calendar-date display', () => {
  it.each([['2026-11-03', 'Nov 3, 2026'], ['2026-11-03T00:00:00Z', 'Nov 3, 2026'], ['2026-11-03T00:00:00+00:00', 'Nov 3, 2026'], ['2026-11-03T00:00:00.000Z', 'Nov 3, 2026'], ['2026-11-03T00:00:00.000000+00:00', 'Nov 3, 2026'], ['2026-01-01', 'Jan 1, 2026'], ['2024-02-29', 'Feb 29, 2024']])('preserves the literal day of %s', (value, expected) => {
    expect(formatCalendarDate(value)).toBe(expected)
  })
  it.each([null, undefined, '', 'not-a-date', '2026-02-30', '2026-13-01', '2026-00-01', '2026-11-00', '2026-02-30T00:00:00Z', '2026-02-30T00:00:00.000+00:00'])('shows unavailable for invalid or missing date %s', value => {
    expect(formatCalendarDate(value)).toBe('Unavailable')
  })
  it.each(['2026-11-03T00:30:00Z', '2026-11-03T23:30:00-05:00', '2026-11-03T00:00:00.001Z', '2026-11-03T00:00:00-05:00'])('retains instant-based local display for timestamp %s', value => {
    expect(formatCalendarDate(value)).toBe(format(new Date(value), 'MMM d, yyyy'))
  })
})
