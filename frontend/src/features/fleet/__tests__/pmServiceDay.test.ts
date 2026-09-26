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
