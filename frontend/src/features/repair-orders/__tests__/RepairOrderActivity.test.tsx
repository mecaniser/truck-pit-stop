import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import RepairOrderActivity from '../RepairOrderActivity'
import { buildPartHistoryEvents, repairOrderHistoryDetail } from '../repairOrderHistory'
import type { RepairOrderHistoryEvent } from '@/types'

const operation: RepairOrderHistoryEvent = {
  id: 'op-event', event_type: 'operation_completed', label: 'Operation completed',
  created_at: '2026-10-13T15:20:00Z', actor_name: 'Casey', entity_id: 'op-1',
  detail: 'Inspect brakes; before: technician=15ef589b-a315-4bd9-b169-8487c7d6ef8a, status=pending, version=2, completed_by=None, completed_at=None; after: technician=15ef589b-a315-4bd9-b169-8487c7d6ef8a, status=completed, version=3',
}

describe('readable operation history', () => {
  it.each(['operation_assigned', 'operation_completed', 'operation_reopened', 'operation_scope_removed'])('preserves recorded operation, actor, identity and time for %s', event_type => {
    expect(buildPartHistoryEvents([], [{ ...operation, event_type }])).toEqual([{
      id: 'op-event', label: 'Operation completed', at: operation.created_at,
      actor: 'Casey', detail: 'Inspect brakes', entityId: 'op-1',
    }])
  })
  it.each([null, '', '; before: technician=None', 'technician=unknown, version=2', 'Work; before: broken; after: version=3'])('does not render incomplete implementation snapshots: %s', detail => {
    expect(repairOrderHistoryDetail({ ...operation, detail })).toBeUndefined()
  })
  it('preserves ordinary descriptions including punctuation and readable future payloads', () => {
    expect(repairOrderHistoryDetail({ ...operation, detail: 'Brake; air test; before: technician=None; after: technician=None' })).toBe('Brake; air test')
    expect(repairOrderHistoryDetail({ ...operation, detail: 'Inspect brakes' })).toBe('Inspect brakes')
  })
  it('does not reinterpret other event types or invent an assignee', () => {
    const other = { ...operation, event_type: 'part_added', detail: 'Filter · 2 ea', actor_name: null }
    expect(buildPartHistoryEvents([], [other])[0]).toMatchObject({ detail: 'Filter · 2 ea', actor: undefined })
    expect(operation.detail).toContain('version=3')
  })
})

const events = Array.from({ length: 14 }, (_, index) => ({
  id: String(index), label: index === 0 ? 'Operation reopened' : 'Operation completed',
  detail: index === 0 ? 'Older brake inspection' : `Tire check ${index}`,
  actor: index === 0 ? 'Alex' : 'Casey', at: `2026-10-13T15:${String(index).padStart(2, '0')}:00Z`,
}))

describe('repair order activity review', () => {
  it('searches the entire history, not just visible rows, and recovers from no results', async () => {
    const user = userEvent.setup()
    render(<RepairOrderActivity events={events} initiallyOpen />)
    expect(within(screen.getByRole('list', { name: 'History events' })).getAllByRole('listitem')).toHaveLength(10)
    await user.type(screen.getByRole('searchbox'), 'ALEX brake')
    expect(screen.getByText('Older brake inspection')).toBeInTheDocument()
    expect(screen.getByText('1 matching event')).toBeInTheDocument()
    await user.clear(screen.getByRole('searchbox'))
    await user.type(screen.getByRole('searchbox'), 'no-such-work')
    expect(screen.getByText('No events match your search.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear search', exact: true }))
    expect(screen.getByRole('searchbox')).toHaveValue('')
    await user.click(screen.getByRole('button', { name: 'Show 4 older events' }))
    expect(within(screen.getByRole('list', { name: 'History events' })).getAllByRole('listitem')).toHaveLength(14)
    await user.click(screen.getByRole('button', { name: 'Show less' }))
    expect(screen.getByText('Showing 10 of 14 events')).toBeInTheDocument()
  })
  it('shows partial failure, preserves search and existing rows, and retries explicitly', async () => {
    const user = userEvent.setup(); const onRetry = vi.fn()
    const view = render(<RepairOrderActivity events={events} initiallyOpen error onRetry={onRetry} />)
    await user.type(screen.getByRole('searchbox'), 'Alex')
    expect(screen.getByRole('alert')).toHaveTextContent('Events may be missing')
    await user.click(screen.getByRole('button', { name: 'Retry history' }))
    expect(onRetry).toHaveBeenCalledOnce()
    view.rerender(<RepairOrderActivity events={events} initiallyOpen loading error onRetry={onRetry} />)
    expect(screen.getByRole('button', { name: 'Retry history' })).toBeDisabled()
    expect(screen.getByRole('searchbox')).toHaveValue('Alex')
    expect(screen.getByText('Older brake inspection')).toBeInTheDocument()
    view.rerender(<RepairOrderActivity events={events} initiallyOpen />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('searchbox')).toHaveValue('Alex')
  })
  it('does not claim empty history during loading or failure; supports read-only disclosure', async () => {
    const user = userEvent.setup(); const onOpen = vi.fn()
    const view = render(<RepairOrderActivity events={[]} loading onOpen={onOpen} />)
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Repair order history' }))
    expect(onOpen).toHaveBeenCalledOnce()
    expect(screen.getByText('Loading history…')).toBeInTheDocument()
    expect(screen.queryByText('No repair order history has been recorded yet.')).not.toBeInTheDocument()
    view.rerender(<RepairOrderActivity events={[]} error />)
    expect(screen.queryByText('No repair order history has been recorded yet.')).not.toBeInTheDocument()
    view.rerender(<RepairOrderActivity events={[]} />)
    expect(screen.getByText('No repair order history has been recorded yet.')).toBeInTheDocument()
  })
})
