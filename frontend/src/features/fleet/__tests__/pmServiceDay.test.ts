import { describe, expect, it } from 'vitest'
import { nextPmServiceDay, projectPmDueDate } from '../helpers'

/* The shop performs PM work on Saturdays, so the date the modal offers must be
   one. Rounding forward rather than back keeps the mileage contract: the truck
   is never asked in sooner than its odometer supports. */

describe('nextPmServiceDay', () => {
  it('moves a mid-week date to the following Saturday', () => {
    expect(nextPmServiceDay('2026-10-07')).toBe('2026-10-10') // Wed -> Sat
  })

  it('leaves a Saturday alone', () => {
    expect(nextPmServiceDay('2026-10-10')).toBe('2026-10-10')
  })

  it('moves a Sunday a full week forward', () => {
    expect(nextPmServiceDay('2026-10-11')).toBe('2026-10-17')
  })

  it('never returns a date before the one given', () => {
    for (let d = 1; d <= 28; d += 1) {
      const day = `2026-10-${String(d).padStart(2, '0')}`
      expect(nextPmServiceDay(day) >= day).toBe(true)
    }
  })

  it('always returns a Saturday', () => {
    for (let d = 1; d <= 28; d += 1) {
      const day = `2026-10-${String(d).padStart(2, '0')}`
      expect(new Date(`${nextPmServiceDay(day)}T12:00:00Z`).getUTCDay()).toBe(6)
    }
  })
})

describe('projectPmDueDate', () => {
  it('projects from the mileage target, then rounds to the PM day', () => {
    // 1,200 mi remaining at 600 mi/day = 2 days: Mon 5th -> Wed 7th -> Sat 10th.
    expect(projectPmDueDate(101200, 100000, '2026-10-05')).toBe('2026-10-10')
  })

  it('books the next PM day when the truck is already overdue on mileage', () => {
    expect(projectPmDueDate(99000, 100000, '2026-10-07')).toBe('2026-10-10')
  })

  it('does not shift a date-only value across a timezone boundary', () => {
    // 2026-03-01 is a Sunday; the PM day is the 7th, regardless of local offset.
    expect(projectPmDueDate(100000, 100000, '2026-03-01')).toBe('2026-03-07')
  })
})

describe('projectPmDueDate honours an overdue date, not just mileage', () => {
  /* A PM is due when EITHER the date or the odometer is reached. Projecting
     from mileage alone offered a date six weeks out for a truck already 27 days
     overdue, because it still had 25,000 miles to run. */

  it('offers the next service day when the stored date has passed', () => {
    // 24,999 mi left (42 days at 600/day) but the due date passed 27 days ago.
    expect(projectPmDueDate(646565, 621566, '2026-09-28', '2026-09-01')).toBe('2026-10-03')
  })

  it('does not push an overdue truck out to its mileage date', () => {
    const offered = projectPmDueDate(646565, 621566, '2026-09-28', '2026-09-01')
    expect(offered < '2026-11-14').toBe(true)
  })

  it('still projects from mileage when the stored date is in the future', () => {
    // Due date far off, mileage close: the mileage governs.
    expect(projectPmDueDate(101200, 100000, '2026-10-05', '2027-01-01')).toBe('2026-10-10')
  })

  it('takes whichever trigger comes first', () => {
    // Stored date sooner than the mileage projection: the date governs.
    expect(projectPmDueDate(125000, 100000, '2026-10-05', '2026-10-13')).toBe('2026-10-17')
  })

  it('behaves as before when there is no stored date', () => {
    expect(projectPmDueDate(101200, 100000, '2026-10-05')).toBe('2026-10-10')
  })

  it('books the next service day when overdue on both axes', () => {
    expect(projectPmDueDate(99000, 100000, '2026-09-28', '2026-09-01')).toBe('2026-10-03')
  })
})
