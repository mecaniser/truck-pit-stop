import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
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
async function openDay() { await userEvent.click(await screen.findByRole('button', { name: /Oct 2: .*View routes/ })) }
describe('OTR fleet overview', () => {
  it('keeps fleet period drilldown aggregated until a truck is selected', async () => {
    api.get.mockResolvedValue({ data: { ...response, total: 2,
      items: [...response.items, { ...response.items[0], id: 'trip-2', vehicle_id: other.id, distance_miles: 20, driving_seconds: 1800 }],
      summary: { ...response.summary, truck_count: 2, trip_count: 2, distance_miles: 60, driving_seconds: 5400 },
    } })
    setup({ vehicleId: '', start: '2026-10-02', end: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: /Oct 2: .*Compare trucks/ }))
    const fleet = screen.getByRole('region', { name: 'Fleet period breakdown' })
    expect(fleet).toHaveTextContent('60 mi')
    expect(fleet).toHaveTextContent('66.7%')
    expect(within(fleet).getByText('66.7%')).toHaveAttribute('title', '66.7% of the fleet’s recorded distance for Oct 2: 40 mi out of 60 mi across 2 reporting trucks.')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByText('First City, NC')).not.toBeInTheDocument()
    await userEvent.click(within(fleet).getByRole('button', { name: /Example Fleet 101: 40 mi.*View truck routes for this period/ }))
    expect(screen.getByRole('region', { name: 'Selected day routes' })).toHaveTextContent('First City, NC')
    expect(screen.getAllByRole('article')).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: 'Back to fleet period' }))
    expect(screen.getByRole('region', { name: 'Fleet period breakdown' })).toHaveTextContent('60 mi')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Driving hours', exact: true }))
    expect(screen.getByRole('heading', { name: 'Driving hours by truck' })).toBeVisible()
    expect(screen.getByRole('button', { name: /Example Fleet 101: 1.0h.*View truck routes for this period/ })).toBeVisible()
  })
  it('emphasizes first departure and latest arrival inside the route list', async () => {
    setup(); await openDay()
    expect(screen.getByLabelText('First recorded departure in selected period')).toHaveClass('is-period-first')
    expect(screen.getByLabelText('Latest recorded arrival in selected period')).toHaveClass('is-period-last')
    expect(screen.queryByLabelText('Journey across selected period')).not.toBeInTheDocument()
  })
  it('focuses on travel but retains short movements and unchanged full-day totals', async () => {
    api.get.mockResolvedValue({ data: { ...response, total: 2,
      items: [...response.items, { ...response.items[0], id: 'short-trip', distance_miles: 0.5, driving_seconds: 120 }],
      summary: { ...response.summary, trip_count: 2, distance_miles: 40.5, driving_seconds: 3720 },
    } })
    setup(); await openDay()
    const detail = screen.getByRole('region', { name: 'Selected day routes' })
    expect(within(detail).getByLabelText('Route summary')).toHaveTextContent('Travel · 1 trips40 mi')
    expect(detail).toHaveTextContent('Short movements · 10.5 mi · 2 min')
    expect(within(detail).getAllByRole('article')).toHaveLength(1)
    await userEvent.click(within(detail).getByRole('button', { name: 'Show all 2 movements' }))
    expect(within(detail).getAllByRole('article')).toHaveLength(2)
    expect(within(detail).getByLabelText('Route summary')).toHaveTextContent('Travel · 1 trips40 mi')
    await userEvent.click(within(detail).getByRole('button', { name: 'Focus on travel' }))
    expect(within(detail).getAllByRole('article')).toHaveLength(1)
  })
  it('opens a heat-map cell inside the comparison panel and restores it on Back', async () => {
    setup({ vehicleId: '', start: '2026-10-02', end: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: 'Daily pattern', exact: true }))
    const cell = screen.getByRole('button', { name: 'Example Fleet 101, Oct 2: 40 mi. View routes', exact: true })
    const matrix = screen.getByLabelText('Daily truck activity')
    matrix.scrollLeft = 120
    await userEvent.click(cell)
    expect(await screen.findByRole('region', { name: 'Selected day routes' })).toHaveTextContent('40 mi')
    expect(screen.getByRole('region', { name: 'Daily activity chart' })).toBeVisible()
    expect(matrix).not.toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Back to comparison' }))
    expect(matrix).toBeVisible()
    expect(matrix.scrollLeft).toBe(120)
    await waitFor(() => expect(cell).toHaveFocus())
    expect(screen.getByRole('button', { name: 'Daily pattern', exact: true })).toHaveAttribute('aria-pressed', 'true')
  })
  it('shows mileage coverage and a median reference without treating estimates as measured fuel', async () => {
    api.get.mockResolvedValue({ data: { ...response, total: 3,
      items: [
        {...response.items[0], distance_miles: 30, metrics: {...emptyMetrics, estimated_fuel_gallons: 5, estimate_baseline_period: 'last_30_days', estimate_baseline_mpg: 6}},
        {...response.items[0], id:'uncovered', distance_miles:10, metrics:emptyMetrics},
        {...response.items[0], id:'peer', vehicle_id:other.id, distance_miles:20, metrics:{...emptyMetrics, fuel_used_gallons:4}},
      ], summary: {...response.summary, truck_count:2, trip_count:3, distance_miles:60, driving_seconds:10800},
    } })
    setup({vehicleId:'', start:'2026-10-02', end:'2026-10-02'})
    expect(await screen.findByText('Est. · 75% of miles')).toBeVisible()
    expect(screen.getByText('Measured · 100% of miles')).toBeVisible()
    expect(screen.getByText(/Fleet median 30 mi/)).toBeVisible()
    expect(screen.getAllByRole('img', {name:/fleet median 30 mi/})).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', {name:'Driving hours', exact:true}))
    expect(screen.getAllByRole('img', {name:/fleet median 1.5h/})).toHaveLength(2)
  })
  it('shows signed median differences and converts driving deltas to hours', async () => {
    api.get.mockResolvedValue({ data: { ...response, total: 2,
      items: [{ ...response.items[0], metrics: { ...emptyMetrics, fuel_used_gallons: 4 } }, { ...response.items[0], id: 'trip-2', vehicle_id: other.id, distance_miles: 20, driving_seconds: 1800, metrics: { ...emptyMetrics, fuel_used_gallons: 4 } }],
      summary: { ...response.summary, truck_count: 2, trip_count: 2, distance_miles: 60, driving_seconds: 5400 },
    } })
    setup({ vehicleId: '', start: '2026-10-02', end: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: 'Explain activity for Example Fleet 101' }))
    expect(await screen.findByRole('dialog')).toHaveTextContent('40 mi')
    expect(screen.getByRole('dialog')).toHaveTextContent('33.3% above fleet median')
    expect(screen.getByRole('dialog')).toHaveTextContent('10 gal/100 mi')
    expect(screen.getByRole('dialog')).toHaveTextContent('33.3% lower measured fuel / mile')
    expect(screen.getByRole('dialog')).toHaveTextContent('vs median 15 gal/100 mi')
    await userEvent.keyboard('{Escape}')
    await userEvent.click(screen.getByRole('button', { name: 'Driving hours', exact: true }))
    await userEvent.click(screen.getByRole('button', { name: 'Explain activity for Example Fleet 102' }))
    expect(await screen.findByRole('dialog')).toHaveTextContent('33.3% below fleet median')
    expect(screen.getByRole('dialog')).toHaveTextContent('20 mi')
  })
  it('explains rankings on demand and dismisses with Escape without navigating', async () => {
    setup({ vehicleId: '', start: '2026-10-02', end: '2026-10-02' })
    const trigger = await screen.findByRole('button', { name: 'Explain activity for Example Fleet 101' })
    await userEvent.click(trigger)
    const popup = await screen.findByRole('dialog', { name: 'Activity criteria for Example Fleet 101' })
    expect(popup).toHaveTextContent('Distance comparison')
    expect(popup).toHaveTextContent('No other reporting trucks to compare.')
    expect(popup).toHaveTextContent('Measured fuel')
    expect(popup).toHaveTextContent('current driver only')
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Show 1 truck without imported trips' }))
    await userEvent.click(screen.getByRole('button', { name: 'Explain activity for Example Fleet 102' }))
    expect(await screen.findByRole('dialog')).toHaveTextContent('No imported trips.')
    expect(screen.getByRole('dialog')).toHaveTextContent('Check import coverage')
  })
  it('shows a comparison before any raw routes and includes trucks without imports', async () => {
    setup({ vehicleId: '', start: '2026-10-02', end: '2026-10-02' })
    expect(await screen.findByRole('heading', { name: 'OTR fleet comparison' })).toBeInTheDocument()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByText('No imported trips')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show 1 truck without imported trips' }))
    expect(screen.getByText('No imported trips')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Example Fleet 101 Current driver: Unassigned/ }))
    expect(await screen.findByRole('heading', { name: 'Truck activity' })).toBeInTheDocument()
  })
  it('opens a day and returns to overview without repeating the truck link', async () => {
    const open = setup(); await openDay()
    expect(await screen.findByRole('article', { name: /Leg 1/ })).toHaveTextContent('First City, NC')
    expect(screen.queryByText('Stop details unavailable')).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /View truck/ })).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: /View truck/ })); expect(open).toHaveBeenCalledWith(truck.id)
    await userEvent.click(screen.getByRole('button', { name: 'Overview' }))
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })
  it('keeps view and measure independent with one selected option in each group', async () => {
    setup({ vehicleId: '', start: '2026-10-02', end: '2026-10-02' })
    const view = await screen.findByRole('group', { name: 'View', exact: true })
    const measure = screen.getByRole('group', { name: 'Measure', exact: true })
    expect(within(view).getByRole('button', { name: 'Comparison' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(within(measure).getByRole('button', { name: 'Driving hours' }))
    await userEvent.click(within(view).getByRole('button', { name: 'Daily pattern' }))
    expect(within(measure).getByRole('button', { name: 'Driving hours' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(view).getAllByRole('button', { pressed: true })).toHaveLength(1)
    await userEvent.click(within(measure).getByRole('button', { name: 'Miles' }))
    expect(within(view).getByRole('button', { name: 'Daily pattern' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(within(view).getByRole('button', { name: 'Comparison' }))
    expect(within(measure).getByRole('button', { name: 'Miles' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(measure).getAllByRole('button', { pressed: true })).toHaveLength(1)
    expect(screen.getByLabelText('Truck activity comparison')).toBeInTheDocument()
  })
  it('shows current assignments and an honest missing-driver fallback in both views', async () => {
    truck.driver_name = 'Test Driver'
    setup({ vehicleId: '', start: '2026-10-02', end: '2026-10-02' })
    expect(await screen.findByLabelText('Current driver: Test Driver')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show 1 truck without imported trips' }))
    expect(screen.getByLabelText('Current driver: Unassigned')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Daily pattern' }))
    expect(screen.getByLabelText('Current driver: Test Driver')).toBeInTheDocument()
    truck.driver_name = null
  })
  it('opens a daily pattern cell with only that truck and date', async () => {
    setup({ vehicleId: '', start: '2026-10-02', end: '2026-10-02' })
    await userEvent.click(await screen.findByRole('button', { name: 'Daily pattern' }))
    const matrix = screen.getByLabelText('Daily truck activity')
    expect(matrix.closest('.otr-workspace')).toHaveClass('is-fleet')
    await userEvent.click(within(matrix).getByRole('button', { name: 'Show 1 truck without imported trips' }))
    expect(within(matrix).getByLabelText('No imported trips')).toHaveTextContent('—')
    await userEvent.click(within(matrix).getByRole('button', { name: /Example Fleet 101, Oct 2:/ }))
    expect(screen.getAllByRole('article')).toHaveLength(1)
  })
  it('reveals calendars on Custom and hides them on quick picks', async () => {
    setup({ vehicleId: truck.id, start: '2026-10-02', end: '2026-10-02', preset: 'week' })
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Custom' }))
    expect(screen.getByLabelText('From')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Month' }))
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument()
  })
  it('labels fuel estimates and excludes them from overview efficiency rankings', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [{ ...response.items[0], metrics: { ...emptyMetrics, estimated_fuel_gallons: 6.2, estimate_baseline_mpg: 6.5, estimate_baseline_period: 'last_30_days' } }] } })
    setup(); await screen.findByRole('heading', { name: 'Truck activity' })
    expect(screen.queryByText('Est. fuel')).not.toBeInTheDocument(); await openDay()
    expect(screen.getByText('Est. fuel')).toBeInTheDocument()
    expect(screen.queryByText('Trip efficiency')).not.toBeInTheDocument()
  })
  it.each([1799, 1800, 2400])('shows idle only at thirty minutes or longer: %i', async seconds => {
    api.get.mockResolvedValue({ data: { ...response, items: [{ ...response.items[0], metrics: { ...emptyMetrics, idle_seconds: seconds } }] } })
    setup(); await openDay()
    expect(!!screen.queryByText('Idle time')).toBe(seconds >= 1800)
  })
  it('shows measured fuel and efficiency without estimate labels', async () => {
    api.get.mockResolvedValue({ data: { ...response, items: [{ ...response.items[0], metrics: { ...emptyMetrics, fuel_used_gallons: 5, trip_mpg: 8 } }] } })
    setup(); await openDay(); expect(screen.getByText('Fuel used')).toBeInTheDocument(); expect(screen.getByText('Trip efficiency')).toBeInTheDocument()
  })
  it('keeps loading, failure, retry and missing-history states distinct', async () => {
    api.get.mockRejectedValueOnce(new Error('offline'))
    setup(); expect(screen.getByRole('status')).toHaveTextContent('Loading')
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
    api.get.mockResolvedValue({ data: { ...response, items: [], total: 0, summary: { ...response.summary, trip_count: 0, truck_count: 0, distance_miles: 0, driving_seconds: 0 } } })
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('heading', { name: 'No imported trips' })).toBeInTheDocument()
  })
  it('rejects invalid dates and unknown trucks without API calls', () => {
    setup({ vehicleId: 'unknown', start: '2025-09-01', end: '2026-10-04' })
    expect(screen.getByRole('alert')).toHaveTextContent('up to 366 days'); expect(api.get).not.toHaveBeenCalled()
  })
  it('fetches every page before showing comparisons', async () => {
    const rows = Array.from({ length: 101 }, (_, i) => ({ ...response.items[0], id: String(i) }))
    api.get.mockImplementation((_url, { params }) => Promise.resolve({ data: { ...response, items: rows.slice(params.offset, params.offset + 100), offset: params.offset, total: 101, summary: { ...response.summary, trip_count: 101, distance_miles: 4040, driving_seconds: 363600 } } }))
    setup(); expect(await screen.findByLabelText('Imported trip totals')).toHaveTextContent('4,040')
    expect(api.get.mock.calls.filter(([url]) => url === '/fleet/trips')).toHaveLength(2)
    await openDay(); expect(screen.getAllByRole('article')).toHaveLength(50)
    await userEvent.click(screen.getByRole('button', { name: 'Next' })); expect(screen.getByText('51–100 of 101')).toBeInTheDocument()
  })
  it('recalculates day, week, month and custom totals for the selected truck', async () => {
    const dates = ['2026-09-28', '2026-10-01', '2026-10-02', '2026-10-04']
    const rows = dates.flatMap((date, i) => [truck, other].map(t => ({ ...response.items[0], id: `${date}-${t.id}`, vehicle_id: t.id, started_at: `${date}T16:00:00Z`, distance_miles: (i + 1) * 10 })))
    api.get.mockImplementation((_url, { params }) => {
      const items = rows.filter(t => t.started_at.slice(0, 10) >= params.start_date && t.started_at.slice(0, 10) <= params.end_date && (!params.vehicle_id || t.vehicle_id === params.vehicle_id))
      return Promise.resolve({ data: { ...response, items, total: items.length, summary: { ...response.summary, truck_count: new Set(items.map(t => t.vehicle_id)).size, trip_count: items.length, distance_miles: items.reduce((n, t) => n + t.distance_miles, 0), driving_seconds: items.length * 3600 } } })
    })
    setup({ vehicleId: truck.id, start: '2026-10-01', end: '2026-10-02', preset: 'custom' })
    expect(await screen.findByLabelText('Imported trip totals')).toHaveTextContent('50 mi')
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(2026, 9, 4, 12))
    try {
      await userEvent.click(screen.getByRole('button', { name: 'Day', exact: true }))
      await waitFor(() => expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('40 mi'))
      await userEvent.click(screen.getByRole('button', { name: 'Week', exact: true }))
      await waitFor(() => expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('100 mi'))
      await userEvent.click(screen.getByRole('button', { name: 'Month', exact: true }))
      await waitFor(() => expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('90 mi'))
    } finally { vi.useRealTimers() }
  })
  it('rejects an unknown truck even with valid dates', () => {
    setup({ vehicleId: 'unknown', start: '2026-10-01', end: '2026-10-02' })
    expect(screen.getByRole('alert')).toHaveTextContent('no longer available'); expect(api.get).not.toHaveBeenCalled()
  })
  it('navigates previous/current periods without losing the truck filter', async () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(2026, 9, 7, 12))
    try {
      setup({ vehicleId: truck.id, ...tripPreset('week'), preset: 'week' })
      expect(screen.getByRole('button', { name: 'Next week' })).toBeDisabled()
      await userEvent.click(screen.getByRole('button', { name: 'Previous week' }))
      await waitFor(() => expect(api.get).toHaveBeenCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: truck.id, start_date: '2026-09-28', end_date: '2026-10-04' }) })))
      await userEvent.click(screen.getByRole('button', { name: 'This week', exact: true }))
      await waitFor(() => expect(api.get).toHaveBeenCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ start_date: '2026-10-05', end_date: '2026-10-07' }) })))
      await userEvent.click(screen.getByRole('button', { name: 'Month', exact: true }))
      await userEvent.click(screen.getByRole('button', { name: 'Previous month' }))
      await waitFor(() => expect(api.get).toHaveBeenCalledWith('/fleet/trips', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: truck.id, start_date: '2026-09-01', end_date: '2026-09-30' }) })))
      await userEvent.click(screen.getByRole('button', { name: 'Next month' }))
      expect(screen.getByRole('button', { name: 'Next month' })).toBeDisabled()
      await userEvent.click(screen.getByRole('button', { name: 'Custom', exact: true }))
      expect(screen.queryByRole('group', { name: 'Month navigation' })).not.toBeInTheDocument()
    } finally { vi.useRealTimers() }
  })
  it('loads Motive fuel independently and keeps source totals separate from estimates', async () => {
    const daily = { vehicle_id: truck.id, report_date: '2026-10-02', driving_fuel_gallons: 6, idling_fuel_gallons: 2, reported_total_fuel_gallons: 8.1, source_distance_miles: 35, source_driving_seconds: 3300, source_idling_seconds: 600, timezone_status: 'unverified', source_timezone: null }
    api.get.mockImplementation((url) => Promise.resolve({ data: url === '/fleet/fuel-daily' ? { items: [daily], total: 1, offset: 0, limit: 100, start_date: response.start_date, end_date: response.end_date, date_basis: 'source_report_date', coverage: 'partial' } : { ...response, items: [{ ...response.items[0], metrics: { ...emptyMetrics, estimated_fuel_gallons: 5, estimate_baseline_mpg: 8, estimate_baseline_period: 'last_30_days' } }] } }))
    setup({ vehicleId: '', start: response.start_date, end: response.end_date })
    expect(await screen.findByRole('columnheader', { name: 'Motive diesel · gal' })).toBeVisible()
    expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('40 mi')
    await userEvent.click(screen.getAllByRole('button', { name: 'Motive fuel details: 6 gallons driving, 2 gallons idling' })[0])
    const details = screen.getByRole('dialog', { name: 'Motive fuel report' })
    expect(details).toHaveTextContent('8.1 gal')
    expect(details).toHaveTextContent('35 mi')
    expect(details).toHaveTextContent('timezone is unverified')
    await userEvent.keyboard('{Escape}')
    await userEvent.click(screen.getByRole('button', { name: /Explain activity for Example Fleet 101/ }))
    const activity = screen.getByRole('dialog', { name: /Activity criteria/ })
    expect(activity).toHaveTextContent('Calculated estimate')
    expect(activity).toHaveTextContent('5 gal')
    expect(activity).not.toHaveTextContent('fuel / mile')
  })
  it('keeps idling-only trucks visible in comparison and period breakdown', async () => {
    const daily = { vehicle_id: other.id, report_date: '2026-10-02', driving_fuel_gallons: 0, idling_fuel_gallons: 3, reported_total_fuel_gallons: 3, source_distance_miles: 0, source_driving_seconds: 0, source_idling_seconds: 7200, timezone_status: 'unverified', source_timezone: null }
    api.get.mockImplementation(url => Promise.resolve({ data: url === '/fleet/fuel-daily' ? { items: [daily], total: 1, offset: 0, date_basis: 'source_report_date' } : response }))
    setup({ vehicleId: '', start: response.start_date, end: response.end_date })
    expect(await screen.findByRole('columnheader', { name: 'Motive diesel · gal' })).toBeVisible()
    expect(screen.getByRole('button', { name: /Explain activity for Example Fleet 102/ })).toBeVisible()
    expect(screen.queryByRole('button', { name: /Show 1 truck without/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Oct 2: .*Compare trucks/ }))
    const period = screen.getByRole('region', { name: 'Fleet period breakdown' })
    const idleTruck = within(period).getByRole('button', { name: /Example Fleet 102: 0 mi.*idling fuel 3 gallons/ })
    expect(idleTruck).toHaveTextContent('Driving 0 · Idling 3 gal')
    await userEvent.click(idleTruck)
    expect(screen.getByRole('region', { name: 'Selected day routes' })).toHaveTextContent('Motive fuel · selected report dates')
  })
  it('keeps trips available when fuel fetching fails and retries fuel separately', async () => {
    api.get.mockImplementation(url => url === '/fleet/fuel-daily' ? Promise.reject(new Error('fuel unavailable')) : Promise.resolve({ data: response }))
    setup()
    expect(await screen.findByText(/Fuel reports unavailable/)).toBeVisible()
    expect(screen.getByLabelText('Imported trip totals')).toHaveTextContent('40 mi')
    const tripCalls = api.get.mock.calls.filter(([url]) => url === '/fleet/trips').length
    await userEvent.click(screen.getByRole('button', { name: 'Retry fuel' }))
    expect(api.get.mock.calls.filter(([url]) => url === '/fleet/trips')).toHaveLength(tripCalls)
  })
  it('preserves calendar preset boundaries', () => {
    expect(tripPreset('week', new Date(2026, 9, 4, 12))).toEqual({ start: '2026-09-28', end: '2026-10-04' })
    expect(tripPreset('month', new Date(2026, 9, 4, 12))).toEqual({ start: '2026-10-01', end: '2026-10-04' })
    expect(tripWeeks('2026-09-28', '2026-10-04')).toHaveLength(1)
  })
})
