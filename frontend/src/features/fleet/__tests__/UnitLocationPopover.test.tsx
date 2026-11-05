import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import UnitLocationPopover from '../UnitLocationPopover'
import FleetBoard from '../FleetBoard'
import type { BoardTruck } from '../types'
vi.mock('../FleetActivity', () => ({ default: () => null }))
const stamp = () => new Date().toISOString()
function truck(speedAge = 0): BoardTruck {
  const source = { source: 'motive_dashboard_manual' as const, observed_at: stamp(), captured_at: stamp(), freshness: 'fresh' as const, snapshot_id: null, source_age_text: null }
  return { id: 'unit-one', unit_number: '603', equipment_type: 'tractor', make: 'Demo', model: 'Tractor', status: 'active', moving: false, pm_interval_miles: 25000, open_work_order_count: 0, open_incident_count: 0, telemetry: { motion: 'unknown', location: { ...source, lat: null, lng: null, label: '123 Synthetic Road' }, speed: { ...source, observed_at: new Date(Date.now() - speedAge).toISOString(), value: 0, unit: 'mph', basis: null }, odometer: null, engine_hours: null, fuel: null, fault_count: null } }
}
describe('unit location marker', () => {
  it('keeps address and speed hidden until clicked and preserves a fresh zero', async () => {
    const parent = vi.fn()
    render(<div onClick={parent} onKeyDown={parent}><UnitLocationPopover truck={truck()} /></div>)
    expect(screen.queryByText('123 Synthetic Road')).not.toBeInTheDocument()
    expect(screen.queryByText('0 mph')).not.toBeInTheDocument()
    const marker = screen.getByRole('button', { name: 'Location and speed for 603' })
    await userEvent.click(marker)
    expect(screen.getByRole('dialog', { name: 'Location and speed for 603' })).toBeVisible()
    expect(screen.getByText('123 Synthetic Road')).toBeVisible()
    expect(screen.getByText('0 mph')).toBeVisible()
    expect(parent).not.toHaveBeenCalled()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(marker).toHaveFocus()
  })
  it('does not present an old speed as current beside a recent address', async () => {
    render(<UnitLocationPopover truck={truck(20 * 60000)} />)
    await userEvent.click(screen.getByRole('button'))
    expect(screen.getByText('123 Synthetic Road')).toBeVisible()
    expect(screen.getByLabelText('Speed unavailable')).toBeVisible()
    expect(screen.queryByText('0 mph')).not.toBeInTheDocument()
    expect(screen.getByText(/Last observed/)).toBeVisible()
  })
  it('keeps a marker for units without readings and never invents zero', async () => {
    render(<UnitLocationPopover truck={{ ...truck(), telemetry: null }} />)
    await userEvent.click(screen.getByRole('button'))
    expect(screen.getByLabelText('Speed unavailable')).toBeVisible()
    expect(screen.getByText('No recent speed reading.')).toBeVisible()
    expect(screen.queryByText('0 mph')).not.toBeInTheDocument()
  })
  it('opens from the card without opening truck details, and consumes dismissal clicks', async () => {
    const open = vi.fn()
    render(<QueryClientProvider client={new QueryClient()}><FleetBoard data={{ trucks: [truck()], stats: { total: 1, active: 1, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 } }} onOpen={open} onOpenRepairOrder={vi.fn()} filter="all" setFilter={vi.fn()} query="" setQuery={vi.fn()} sort="unit" setSort={vi.fn()} /></QueryClientProvider>)
    expect(screen.queryByText('123 Synthetic Road')).not.toBeInTheDocument()
    expect(screen.queryByText('Speed unavailable')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Location and speed for 603' }))
    expect(open).not.toHaveBeenCalled()
    fireEvent.click(document.querySelector('.unit-location-backdrop')!)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(open).not.toHaveBeenCalled()
  })
  it('expires speed while the popover stays open without borrowing the address time', () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    const view = render(<UnitLocationPopover truck={truck()} />)
    try {
      fireEvent.click(screen.getByRole('button'))
      expect(screen.getByText('0 mph')).toBeVisible()
      act(() => vi.advanceTimersByTime(300000))
      expect(screen.getByText('0 mph')).toBeVisible()
      act(() => vi.advanceTimersByTime(30000))
      expect(screen.queryByText('0 mph')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Speed unavailable')).toBeVisible()
      expect(screen.getByText('123 Synthetic Road')).toBeVisible()
    } finally { view.unmount(); vi.useRealTimers() }
  })

})
