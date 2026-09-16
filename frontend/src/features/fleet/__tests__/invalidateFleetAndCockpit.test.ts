/**
 * Anything that changes a truck must refresh the views that show it.
 *
 * Logging or editing an incident reported success and then displayed the old
 * text: the write landed, but the incident list was keyed
 * 'fleet-truck-incidents' and the helper never invalidated it, so the list kept
 * serving cache. It read as a save that had not saved.
 */
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { invalidateFleetAndCockpit } from '../FleetModals'

function invalidatedKeys(): string[] {
  const qc = new QueryClient()
  const seen: string[] = []
  vi.spyOn(qc, 'invalidateQueries').mockImplementation((filters?: { queryKey?: unknown[] }) => {
    const key = filters?.queryKey?.[0]
    if (typeof key === 'string') seen.push(key)
    return Promise.resolve()
  })
  invalidateFleetAndCockpit(qc)
  return seen
}

describe('invalidateFleetAndCockpit', () => {
  it('refreshes the truck record and its incident list', () => {
    const keys = invalidatedKeys()
    // The one that was missing, and the reason edits looked unsaved.
    expect(keys).toContain('fleet-truck-incidents')
    expect(keys).toContain('fleet-truck')
  })

  it('still refreshes the board and the shop cockpit', () => {
    // Fleet and shop read one repair_orders table, so a fleet change has to
    // reach the owner's queue too.
    const keys = invalidatedKeys()
    expect(keys).toContain('fleet-board')
    expect(keys).toContain('dashboard-action-queue')
    expect(keys).toContain('repair-orders')
  })
})
