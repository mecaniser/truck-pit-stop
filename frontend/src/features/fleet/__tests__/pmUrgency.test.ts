import { describe, expect, it } from 'vitest'
import { pmState, pmUrgency } from '../helpers'

/* PM urgency: what the card says, and how the board orders trucks by it.
   A truck due today is the one to act on, so it must not read or sort as
   "later than" a truck due next week. */

describe('pmState label at the day boundary', () => {
  it('says a truck due today is due today, not "in 0 d"', () => {
    expect(pmState({ pm_remaining: null, pm_days_remaining: 0, pm_interval_miles: 25000 }).label)
      .toBe('Due today')
  })

  it('treats due today as urgent, not merely soon', () => {
    // 'pm-soon' would file it under planning; today is action.
    expect(pmState({ pm_remaining: null, pm_days_remaining: 0, pm_interval_miles: 25000 }).cls)
      .toBe('pm-over')
  })

  it('still reads yesterday as overdue', () => {
    expect(pmState({ pm_remaining: null, pm_days_remaining: -1, pm_interval_miles: 25000 }).label)
      .toBe('OVERDUE 1 d')
  })

  it('still reads tomorrow as due soon', () => {
    const s = pmState({ pm_remaining: null, pm_days_remaining: 1, pm_interval_miles: 25000 })
    expect(s.label).toBe('Due in 1 d')
    expect(s.cls).toBe('pm-soon')
  })
})

describe('pmUrgency orders trucks by whichever axis is closer', () => {
  const truck = (over: Partial<Parameters<typeof pmUrgency>[0]>) =>
    ({ pm_remaining: null, pm_days_remaining: null, pm_interval_miles: 25000, ...over })

  it('ranks overdue ahead of due today', () => {
    expect(pmUrgency(truck({ pm_days_remaining: -1 })))
      .toBeLessThan(pmUrgency(truck({ pm_days_remaining: 0 })))
  })

  it('ranks due today ahead of due in a week', () => {
    expect(pmUrgency(truck({ pm_days_remaining: 0 })))
      .toBeLessThan(pmUrgency(truck({ pm_days_remaining: 7 })))
  })

  it('ranks a truck due by date ahead of one far away on mileage', () => {
    // The old sorter read miles only, so a date-due truck sorted on its
    // odometer and sank below trucks with weeks of road left.
    expect(pmUrgency(truck({ pm_days_remaining: 0, pm_remaining: 20000 })))
      .toBeLessThan(pmUrgency(truck({ pm_remaining: 19000 })))
  })

  it('ranks a truck low on miles ahead of one with a distant date', () => {
    expect(pmUrgency(truck({ pm_remaining: 100 })))
      .toBeLessThan(pmUrgency(truck({ pm_days_remaining: 30 })))
  })

  it('puts an unscheduled truck last, not first', () => {
    // null means "no PM planned" - it needs scheduling, but it is not more
    // urgent than a truck that is actually overdue.
    expect(pmUrgency(truck({ pm_days_remaining: 30 })))
      .toBeLessThan(pmUrgency(truck({})))
  })
})
