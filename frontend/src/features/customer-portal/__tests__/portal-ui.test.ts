import { afterEach, describe, expect, it, vi } from 'vitest'

import { daysOverdue, formatMoney, isActiveRepair, overdueLevel, repairStatusLabel } from '../portal-ui'
import { getPortalPreferences, savePortalPreferences } from '../portal-preferences'

describe('customer portal shared behavior', () => {
  afterEach(() => {
    vi.useRealTimers()
    window.localStorage.clear()
  })

  it('uses one overdue threshold for warning and critical invoice states', () => {
    expect(overdueLevel(0)).toBe('none')
    expect(overdueLevel(1)).toBe('warn')
    expect(overdueLevel(2)).toBe('warn')
    expect(overdueLevel(3)).toBe('critical')
  })

  it('calculates whole overdue days without counting future invoices', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-24T12:00:00'))

    expect(daysOverdue('2026-07-21T08:00:00')).toBe(3)
    expect(daysOverdue('2026-07-26T08:00:00')).toBe(0)
  })

  it('formats portal money consistently', () => {
    expect(formatMoney(1127)).toBe('$1,127.00')
    expect(formatMoney('109.49')).toBe('$109.49')
  })

  it('keeps repair work active until payment or cancellation is finalized', () => {
    expect(isActiveRepair({ status: 'completed' } as never)).toBe(true)
    expect(isActiveRepair({ status: 'invoiced' } as never)).toBe(true)
    expect(isActiveRepair({ status: 'paid' } as never)).toBe(false)
    expect(repairStatusLabel('pending_review')).toBe('Quality review')
  })

  it('persists payment and notification preferences per customer', () => {
    const preferences = getPortalPreferences('customer-1')
    savePortalPreferences('customer-1', {
      ...preferences,
      defaultPaymentMethod: 'card',
      notifications: { ...preferences.notifications, pmReminders: false },
    })

    expect(getPortalPreferences('customer-1')).toMatchObject({
      defaultPaymentMethod: 'card',
      notifications: { pmReminders: false },
    })
    expect(getPortalPreferences('customer-2').defaultPaymentMethod).toBe('zelle')
  })
})
