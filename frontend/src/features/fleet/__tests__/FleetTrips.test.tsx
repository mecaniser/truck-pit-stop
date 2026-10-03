import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { tripPreset, tripWeeks } from '../tripFilters'
import type { BoardTruck } from '../types'
import FleetTrips, { type FleetTripsResponse, type TripFilters } from '../FleetTrips'
const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 400: '#ffd000', 500: '#ffd000' } }) }))
vi.mock('@/lib/api', () => ({ default: api }))
const truck = { id: 'truck-1', unit_number: '101', display_unit_number: 'Example Fleet 101' } as BoardTruck
const other = { ...truck, id: 'truck-2', unit_number: '102', display_unit_number: 'Example Fleet 102' }
const response: FleetTripsResponse = {
  items: [{ id: 'trip-1', vehicle_id: truck.id, unit_number: '101', fleet_customer_id: 'fleet-1', fleet_name: 'Example Fleet', started_at: '2026-10-02T13:00:00Z', ended_at: '2026-10-02T14:00:00Z', origin_label: 'First City, NC', destination_label: 'Second City, NC', distance_miles: 40, driving_seconds: 3600, captured_at: '2026-10-02T15:00:00Z', source: 'motive_dashboard_manual', stops: null }],
  summary: { coverage: 'partial', truck_count: 1, trip_count: 1, distance_miles: 40, driving_seconds: 3600 }, total: 1, limit: 50, offset: 0, timezone: 'America/New_York', start_date: '2026-10-02', end_date: '2026-10-02',
}
function setup(filters: TripFilters = { vehicleId: truck.id, start: '2026-10-02', end: '2026-10-02' }) {
  const open = vi.fn()
  function Harness() { const [value, setValue] = useState(filters); return <FleetTrips trucks={[truck, other]} filters={value} onFilters={setValue} onOpenTruck={open} /> }
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Harness /></QueryClientProvider>)
  return open
}
beforeEach(() => { api.get.mockReset(); api.get.mockResolvedValue({ data: response }) })
const emptyMetrics = { fuel_used_gallons: null, trip_mpg: null, estimated_fuel_gallons: null, idle_seconds: null, fuel_start_percent: null, fuel_end_percent: null, estimate_baseline_mpg: null, estimate_baseline_captured_at: null, estimate_baseline_period: null }
describe('Fleet trip history', () => {
  it('shows imported bounds outside the selected dates without claiming complete history', async () => {
    api.get.mockResolvedValue({ data: { ...response, imported_start: '2026-07-22', imported_end: '2026-10-02', items: [], total: 0 } })
    setup({ vehicleId: truck.id, start: '2026-08-01', end: '2026-08-10', preset: 'custom' })
    const bounds = await screen.findByTitle('Dates show the earliest and latest imported departures. Gaps may remain.')
    expect(bounds).toHaveTextContent('Imported Jul 22, 2026–Oct 2, 2026 · Partial')
    expect(screen.getByRole('heading', { name: 'No imported trips' })).toBeInTheDocument()
  })
  it('uses a compact fallback when imported bounds are unavailable', async () => {
    api.get.mockResolvedValue({ data: { ...response, imported_start: null, imported_end: null } })
    setup()
    expect(await screen.findByTitle('Dates show the earliest and latest imported departures. Gaps may remain.')).toHaveTextContent('Imported trips · Partial')
  })
  it('shows selected truck once as a heading and labels each leg endpoints', async () => {
    setup()
    const leg = await screen.findByRole('article', { name: /Leg 1/ })
    expect(screen.getByRole('heading', { name: 'Example Fleet 101' })).toBeInTheDocument()
    expect(leg).not.toHaveTextContent('Example Fleet 101')
    expect(leg).toHaveTextContent('Departure')
    expect(leg).toHaveTextContent('Arrival')
    expect(screen.getByRole('heading', { name: 'Oct 2' })).toBeInTheDocument()
  })
  it('retains leg truck identity for all trucks and groups chronological days', async () => {
    const first = { ...response.items[0], id: 'earlier', started_at: '2026-09-28T13:00:00Z', ended_at: '2026-09-28T14:00:00Z' }
    api.get.mockResolvedValue({ data: { ...response, items: [first, response.items[0]], total: 2 } })
    setup({ vehicleId: '', start: '2026-09-28', end: '2026-10-02' })
    const legs = await screen.findAllByRole('article', { name: /Example Fleet 101/ })
    expect(legs).toHaveLength(2)
    expect(screen.getAllByRole('heading', { level: 3 }).map(h => h.textContent)).toEqual(['Sep 28', 'Oct 2'])
  })
  it('shows full-fleet totals and coverage even when the page contains only one truck', async () => {
    api.get.mockResolvedValue({ data: { ...response, summary: { coverage: 'partial', truck_count: 13, trip_count: 342, distance_miles: 25072.67, driving_seconds: 1634303 }, total: 342 } })
    setup({ vehicleId: '', start: '2026-09-28', end: '2026-10-02', preset: 'week' })
    const totals = await screen.findByLabelText('Imported trip totals')
    expect(totals).toHaveTextContent('13Trucks with trips')
    expect(totals).toHaveTextContent('342Trips')
    expect(totals).toHaveTextContent('25,072.7 mi')
    expect(totals).toHaveTextContent('453h 58m')
    expect(screen.getByText(/Partial/)).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: undefined }) }))
    await userEvent.click(screen.getByLabelText('Truck'))
    await userEvent.click(screen.getByRole('option', { name: 'Example Fleet 101' }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: truck.id }) })))
  })
  it('reveals custom calendars only on Custom and hides them on quick picks', async () => {
    setup({ vehicleId: truck.id, start: '2026-09-28', end: '2026-10-02', preset: 'week' })
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Custom', exact: true }))
    expect(screen.getByLabelText('From')).toHaveValue('2026-09-28')
    expect(screen.getByLabelText('To')).toHaveValue('2026-10-02')
    expect(screen.getByRole('button', { name: 'Custom' })).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Week', exact: true }))
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument()
  })
  it('shows seconds for short trips rather than zero minutes', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [{ ...response.items[0], driving_seconds: 14, ended_at: response.items[0].started_at, timestamp_precision: 'minute' }] } })
    setup(); expect(await screen.findByRole('article', { name: /First City/ })).toHaveTextContent('14s')
  })
  it('labels baseline fuel estimates and never presents them as trip efficiency', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [{ ...response.items[0], metrics: { ...emptyMetrics, estimated_fuel_gallons: 40 / 6.5, estimate_baseline_mpg: 6.5, estimate_baseline_period: 'last_30_days', estimate_baseline_captured_at: '2026-10-02T15:00:00Z', idle_seconds: 240 } }] } })
    setup(); await screen.findByRole('article', { name: /First City/ })
    const vitals = screen.getByLabelText('Trip fuel and efficiency')
    expect(vitals).toHaveTextContent('Est. fuel6.2 gal')
    expect(vitals).toHaveTextContent('6.5 MPG · 30-day avg')
    expect(vitals).toHaveTextContent('Idle time4m')
    expect(within(vitals).queryByText('Trip efficiency')).not.toBeInTheDocument()
    expect(within(vitals).queryByText('Fuel level')).not.toBeInTheDocument()
  })
  it('shows actual fuel, actual efficiency and zero end fuel without estimates', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [{ ...response.items[0], metrics: { ...emptyMetrics, fuel_used_gallons: 5, trip_mpg: 8, fuel_start_percent: 10, fuel_end_percent: 0, idle_seconds: 0 } }] } })
    setup(); await screen.findByRole('article', { name: /First City/ })
    const vitals = screen.getByLabelText('Trip fuel and efficiency')
    expect(vitals).toHaveTextContent('Fuel used5 gal'); expect(vitals).toHaveTextContent('Trip efficiency8 MPG')
    expect(vitals).toHaveTextContent('10% → 0%'); expect(vitals).toHaveTextContent('Idle time0m')
    expect(within(vitals).queryByText('Est. fuel')).not.toBeInTheDocument()
  })
  it('omits all-unknown metrics instead of rendering empty fields', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [{ ...response.items[0], metrics: emptyMetrics }] } })
    setup(); await screen.findByRole('article', { name: /First City/ })
    expect(screen.queryByLabelText('Trip fuel and efficiency')).not.toBeInTheDocument()
  })
  it('uses calendar quick picks while keeping the truck selection', async () => {
    setup(); await screen.findByText('First City, NC')
    for (const [label, preset] of [['Day', 'day'], ['Week', 'week'], ['Month', 'month']] as const) {
      await userEvent.click(screen.getByRole('button', { name: label, exact: true }))
      const expected = tripPreset(preset)
      expect(screen.queryByLabelText('From')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('To')).not.toBeInTheDocument()
      await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ start_date: expected.start, end_date: expected.end }) })))
      expect(screen.getByRole('button', { name: label, exact: true })).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByLabelText('Truck')).toHaveTextContent('Example Fleet 101')
    }
  })
  it('opens the app calendar and switches to custom when a day is picked', async () => {
    setup(); await screen.findByText('First City, NC')
    await userEvent.click(screen.getAllByRole('button', { name: /Choose date/ })[0])
    const calendar = screen.getByRole('dialog', { name: 'From' })
    expect(within(calendar).getByRole('button', { name: 'Previous month' })).toBeInTheDocument()
    expect(within(calendar).queryByText(/scheduled/)).not.toBeInTheDocument()
    await userEvent.click(within(calendar).getByRole('button', { name: /Oct 1, 2026/ }))
    expect(screen.getByLabelText('From')).toHaveValue('2026-10-01')
    expect(screen.getByRole('button', { name: 'Custom' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('handles week and month boundaries using local calendar dates', () => {
    expect(tripPreset('week', new Date(2026, 0, 1, 12))).toEqual({ start: '2025-12-29', end: '2026-01-01' })
    expect(tripPreset('week', new Date(2026, 9, 4, 12))).toEqual({ start: '2026-09-28', end: '2026-10-04' })
    expect(tripPreset('month', new Date(2024, 1, 29, 12))).toEqual({ start: '2024-02-01', end: '2024-02-29' })
  })
  it('shows no empty disclosure and returns through the single summary truck link', async () => {
    const user = userEvent.setup(); const open = setup()
    expect(await screen.findByText('First City, NC')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: truck.id, start_date: '2026-10-02', end_date: '2026-10-02' }) }))
    expect(screen.queryByRole('button', { name: /First City/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/Stop details unavailable/)).not.toBeInTheDocument()
    expect(screen.getAllByText('First City, NC')).toHaveLength(1)
    expect(screen.getAllByText('Second City, NC')).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: /View truck/ })).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Truck 101 View truck' })); expect(open).toHaveBeenCalledWith(truck.id)
  })
  it('changes truck and date filters', async () => {
    const user = userEvent.setup(); setup(); await screen.findByText('First City, NC')
    await user.click(screen.getByLabelText('Truck'))
    await user.click(screen.getByRole('option', { name: 'Example Fleet 102' }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: other.id }) })))
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-09-30' } })
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ start_date: '2026-09-30' }) })))
  })
  it('does not request overlong date ranges', () => {
    setup({ vehicleId: '', start: '2026-08-01', end: '2026-10-02' }); expect(screen.getByRole('alert')).toHaveTextContent('31 days'); expect(api.get).not.toHaveBeenCalled()
  })
  it('distinguishes missing imported history from no driving', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [], total: 0, summary: { coverage: 'partial', truck_count: 0, trip_count: 0, distance_miles: 0, driving_seconds: 0 } } }); setup()
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
    api.get.mockResolvedValue({ data: { ...response, total: 51, summary: { coverage: 'partial', truck_count: 2, trip_count: 51, distance_miles: 2040, driving_seconds: 183600 } } }); setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Next' }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ offset: 50 }) })))
    expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('2,040')
  })
})

describe('Weekly columns', () => {
  it('partitions partial weeks across month/year and DST without overlap', () => {
    expect(tripWeeks('2026-09-16', '2026-10-03')).toEqual([
      { start: '2026-09-16', end: '2026-09-20' }, { start: '2026-09-21', end: '2026-09-27' }, { start: '2026-09-28', end: '2026-10-03' },
    ])
    expect(tripWeeks('2026-12-31', '2027-01-04')).toEqual([{ start: '2026-12-31', end: '2027-01-03' }, { start: '2027-01-04', end: '2027-01-04' }])
    expect(tripWeeks('2026-10-26', '2026-11-02')).toEqual([{ start: '2026-10-26', end: '2026-11-01' }, { start: '2026-11-02', end: '2026-11-02' }])
  })
  it('shows later weeks immediately, pages each independently and resets when truck changes', async () => {
    api.get.mockImplementation(async (_url, { params: p }) => {
      const overall = p.start_date === '2026-09-14' && p.end_date === '2026-10-03'
      const total = overall ? 53 : p.start_date === '2026-09-14' ? 51 : 1
      const offset = p.offset || 0
      return { data: { ...response, total, offset, items: Array.from({length: Math.min(50, total-offset)}, (_, i) => ({...response.items[0], id: `${p.vehicle_id}-${p.start_date}-${offset+i}`, vehicle_id:p.vehicle_id || truck.id, started_at:`${p.start_date}T13:00:00Z`, ended_at:`${p.start_date}T14:00:00Z`})), summary: {coverage:'partial',truck_count:1,trip_count:total,distance_miles:total*40,driving_seconds:total*3600} } }
    })
    setup({ vehicleId:truck.id,start:'2026-09-14',end:'2026-10-03',preset:'custom' })
    const first = await screen.findByRole('region',{name:'Week Sep 14 – Sep 20'})
    const last = await screen.findByRole('region',{name:'Week Sep 28 – Oct 3'})
    expect(await within(last).findByRole('article',{name:/Leg 1/})).toBeInTheDocument()
    expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('53')
    await userEvent.click(within(first).getByRole('button',{name:'Next'}))
    expect(await within(first).findByRole('article',{name:/Leg 51/})).toBeInTheDocument()
    expect(within(last).getByRole('article',{name:/Leg 1/})).toBeInTheDocument()
    expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('53')
    await userEvent.click(screen.getByLabelText('Truck'))
    await userEvent.click(screen.getByRole('option',{name:'Example Fleet 102'}))
    await waitFor(()=>expect(within(screen.getByRole('region',{name:'Week Sep 14 – Sep 20'})).getByRole('button',{name:'Previous'})).toBeDisabled())
    expect(api.get).toHaveBeenCalledWith('/fleet/trips',expect.objectContaining({params:expect.objectContaining({vehicle_id:other.id,start_date:'2026-09-14',end_date:'2026-09-20',offset:0})}))
  })
  it('keeps empty weeks visible and retries a failed week separately', async () => {
    let failed = true
    api.get.mockImplementation(async (_url,{params:p})=> {
      if(p.start_date==='2026-09-21' && failed) throw new Error('offline')
      return {data:{...response,items:[],total:p.end_date==='2026-10-03' ? 1 : 0}}
    })
    setup({vehicleId:truck.id,start:'2026-09-14',end:'2026-10-03',preset:'custom'})
    const empty=await screen.findByRole('region',{name:'Week Sep 14 – Sep 20'})
    expect(await within(empty).findByText('No imported trips')).toBeInTheDocument()
    const broken=screen.getByRole('region',{name:'Week Sep 21 – Sep 27'})
    expect(await within(broken).findByRole('alert')).toBeInTheDocument()
    failed=false
    await userEvent.click(within(broken).getByRole('button',{name:'Retry'}))
    expect(await within(broken).findByText('No imported trips')).toBeInTheDocument()
  })
})
