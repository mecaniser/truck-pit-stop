import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BoardTruck } from '../types'
import FleetTrips, { type FleetTripsResponse, type TripFilters } from '../FleetTrips'
const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const truck = { id: 'truck-1', unit_number: '101', display_unit_number: 'Example Fleet 101' } as BoardTruck
const other = { ...truck, id: 'truck-2', unit_number: '102', display_unit_number: 'Example Fleet 102' }
const response: FleetTripsResponse = {
  items: [{ id: 'trip-1', vehicle_id: truck.id, unit_number: '101', fleet_customer_id: 'fleet-1', fleet_name: 'Example Fleet', started_at: '2026-10-02T13:00:00Z', ended_at: '2026-10-02T14:00:00Z', origin_label: 'First City, NC', destination_label: 'Second City, NC', distance_miles: 40, driving_seconds: 3600, captured_at: '2026-10-02T15:00:00Z', source: 'motive_dashboard_manual', stops: null }],
  summary: { trip_count: 1, distance_miles: 40, driving_seconds: 3600 }, total: 1, limit: 50, offset: 0, timezone: 'America/New_York', start_date: '2026-10-02', end_date: '2026-10-02',
}
function setup(filters: TripFilters = { vehicleId: truck.id, start: '2026-10-02', end: '2026-10-02' }) {
  const open = vi.fn()
  function Harness() { const [value, setValue] = useState(filters); return <FleetTrips trucks={[truck, other]} filters={value} onFilters={setValue} onOpenTruck={open} /> }
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Harness /></QueryClientProvider>)
  return open
}
beforeEach(() => { api.get.mockReset(); api.get.mockResolvedValue({ data: response }) })
describe('Fleet trip history', () => {
  it('carries truck filter, expands on tap, returns to the same truck', async () => {
    const user = userEvent.setup(); const open = setup()
    expect(await screen.findByText('First City, NC')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: truck.id, start_date: '2026-10-02', end_date: '2026-10-02' }) }))
    await user.click(screen.getByRole('button', { name: /First City/ }))
    expect(screen.getByRole('button', { name: /First City/ })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Stop details unavailable/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View truck' })); expect(open).toHaveBeenCalledWith(truck.id)
  })
  it('changes truck and date filters', async () => {
    const user = userEvent.setup(); setup(); await screen.findByText('First City, NC')
    await user.selectOptions(screen.getByLabelText('Truck'), other.id)
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: other.id }) })))
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-09-30' } })
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ start_date: '2026-09-30' }) })))
  })
  it('does not request overlong date ranges', () => {
    setup({ vehicleId: '', start: '2026-08-01', end: '2026-10-02' }); expect(screen.getByRole('alert')).toHaveTextContent('31 days'); expect(api.get).not.toHaveBeenCalled()
  })
  it('distinguishes missing imported history from no driving', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [], total: 0, summary: { trip_count: 0, distance_miles: 0, driving_seconds: 0 } } }); setup()
    expect(await screen.findByText('No imported trips')).toBeInTheDocument(); expect(screen.queryByText(/no driving/i)).not.toBeInTheDocument()
  })
  it('shows errors instead of misleading zero totals, and retries', async () => {
    api.get.mockRejectedValueOnce(new Error('offline')); const user = userEvent.setup(); setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded'); expect(screen.queryByLabelText('Imported trip totals')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' })); expect(await screen.findByText('First City, NC')).toBeInTheDocument()
  })
  it('handles unknown stop times without invented dates or idle', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [{ ...response.items[0], stops: [{ location_label: 'Rest stop', arrived_at: null, departed_at: null, idle_seconds: null }] }] } }); setup()
    await userEvent.click(await screen.findByRole('button', { name: /First City/ }))
    expect(screen.getByText('Rest stop')).toBeInTheDocument(); expect(screen.queryByText(/0m idle|1970/)).not.toBeInTheDocument()
  })
  it('paginates without changing full-period totals', async () => {
    api.get.mockResolvedValue({ data: { ...response, total: 51, summary: { trip_count: 51, distance_miles: 2040, driving_seconds: 183600 } } }); setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Next' }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ offset: 50 }) })))
    expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('2,040')
  })
})
