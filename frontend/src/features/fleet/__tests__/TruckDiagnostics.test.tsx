import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TruckDiagnostics, { type DiagnosticsResponse } from '../TruckDiagnostics'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({ default: { get } }))

async function open(data: DiagnosticsResponse) {
  get.mockResolvedValue({ data })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TruckDiagnostics truckId="truck-one" /></QueryClientProvider>)
  expect(get).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'View health' }))
}

afterEach(() => get.mockReset())
describe('dashboard diagnostics', () => {
  it('keeps an unavailable capture distinct from an explicit empty check', async () => {
    await open({ last_checked_at: null, coverage: 'unknown', explicit_empty: null, codes: [] })
    expect(await screen.findByText('No verified dashboard check is available for this truck.')).toBeVisible()
    expect(screen.queryByText(/No current fault codes/)).not.toBeInTheDocument()
  })
  it('shows the check time for an explicitly empty complete capture', async () => {
    await open({ last_checked_at: '2026-10-07T20:00:00Z', coverage: 'complete', explicit_empty: true, codes: [] })
    expect(await screen.findByText('No current fault codes were reported at this check.')).toBeVisible()
    expect(screen.getByText(/Dashboard checked/)).toBeVisible()
  })
  it('preserves code zeroes and source timestamps without the timezone note', async () => {
    await open({ last_checked_at: '2026-10-07T20:00:00Z', coverage: 'complete', explicit_empty: false, codes: [{ code: null, spn: '0012', fmi: '00', description: 'Example diagnostic', severity: 'High', network: 'J1939', source_address: null, occurrence_count: 0, first_detected_text: null, last_observed_text: 'Oct 7, 2026, 3:12 PM', timezone_basis: 'unverified' }] })
    expect(await screen.findByText('SPN 0012 · FMI 00')).toBeVisible()
    expect(screen.getByText('0')).toBeVisible()
    expect(screen.getByText('Unknown')).toBeVisible()
    expect(screen.getByText('Oct 7, 2026, 3:12 PM')).toBeVisible()
    expect(screen.queryByText('Source times · timezone unverified')).not.toBeInTheDocument()
  })
  it('does not call a partial empty capture healthy', async () => {
    await open({ last_checked_at: '2026-10-07T20:00:00Z', coverage: 'partial', explicit_empty: true, codes: [] })
    expect(await screen.findByText('Fault-code details are unavailable.')).toBeVisible()
    expect(screen.queryByText(/No current fault codes/)).not.toBeInTheDocument()
  })
})

const empty: DiagnosticsResponse = { last_checked_at: null, coverage: 'unknown', explicit_empty: null, codes: [] }
it('closes with Escape and returns focus to the health button', async () => {
  await open(empty)
  await screen.findByText('No verified dashboard check is available for this truck.')
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByText('Truck health')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'View health' })).toHaveFocus()
})
it('closes with its close button', async () => {
  await open(empty)
  await userEvent.click(screen.getByRole('button', { name: 'Close truck health' }))
  expect(screen.queryByText('Truck health')).not.toBeInTheDocument()
})
it('retries a failed read using the selected truck endpoint', async () => {
  get.mockRejectedValueOnce(new Error('unavailable')).mockResolvedValue({ data: empty })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TruckDiagnostics truckId="truck-two" /></QueryClientProvider>)
  await userEvent.click(screen.getByRole('button', { name: 'View health' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Fault codes could not be loaded.')
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('No verified dashboard check is available for this truck.')).toBeVisible()
  expect(get).toHaveBeenLastCalledWith('/fleet/trucks/truck-two/diagnostics')
})
it('shows loading and dismisses on an outside click', async () => {
  get.mockReturnValue(new Promise(() => {}))
  render(<QueryClientProvider client={new QueryClient()}><button>Outside</button><TruckDiagnostics truckId="truck-one" /></QueryClientProvider>)
  await userEvent.click(screen.getByRole('button', { name: 'View health' }))
  expect(screen.getByRole('status')).toHaveTextContent('Loading fault codes')
  await userEvent.click(screen.getByRole('button', { name: 'Outside' }))
  await waitFor(() => expect(screen.queryByText('Truck health')).not.toBeInTheDocument())
})

it('shows zero vitals and provenance even when fault-code loading fails', async () => {
  get.mockRejectedValue(new Error('offline'))
  const reading = { value: 0, unit: 'mi', basis: 'dashboard_unspecified', source: 'motive_dashboard_manual' as const, observed_at: null, captured_at: new Date().toISOString(), freshness: 'unknown' as const, snapshot_id: 'capture', source_age_text: null }
  const telemetry = { location: null, speed: null, odometer: reading, engine_hours: { ...reading, value: 23520, unit: 'h' }, fuel: null, fault_count: null, motion: 'unknown' as const }
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TruckDiagnostics truckId="truck-one" telemetry={telemetry} /></QueryClientProvider>)
  await userEvent.click(screen.getByRole('button', { name: 'View health' }))
  expect(await screen.findByText('0 mi')).toBeVisible()
  expect(screen.getByText('23,520 h')).toBeVisible()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  const info = screen.getByRole('button', { name: 'Mileage and engine hours information' })
  await userEvent.click(info)
  expect(screen.getAllByText(/Observation time unknown/)).toHaveLength(1)
  expect(screen.getByRole('tooltip')).toHaveTextContent('Mileage and engine hours')
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  expect(screen.getByText('Truck health')).toBeVisible()
  expect(await screen.findByRole('alert')).toHaveTextContent('Fault codes could not be loaded.')
})
it('shows unavailable vitals alongside a verified empty fault check', async () => {
  await open({ last_checked_at: new Date().toISOString(), coverage: 'complete', explicit_empty: true, codes: [] })
  expect(await screen.findByText('No current fault codes were reported at this check.')).toBeVisible()
  expect(screen.getAllByText('Unavailable')).toHaveLength(2)
})

it('preserves separate sources and capture times in shared keyboard information', async () => {
  get.mockResolvedValue({ data: empty })
  const base = { value: 1, unit: 'mi', basis: null, source: 'motive_api' as const, observed_at: new Date().toISOString(), captured_at: new Date().toISOString(), freshness: 'fresh' as const, snapshot_id: null, source_age_text: null }
  const hours = { ...base, source: 'motive_dashboard_manual' as const, observed_at: null, captured_at: new Date(Date.now() - 3600000).toISOString(), unit: 'h' }
  const telemetry = { location: null, speed: null, odometer: base, engine_hours: hours, fuel: null, fault_count: null, motion: 'unknown' as const }
  render(<QueryClientProvider client={new QueryClient()}><TruckDiagnostics truckId="truck-one" telemetry={telemetry} /></QueryClientProvider>)
  await userEvent.click(screen.getByRole('button', { name: 'View health' }))
  const info = screen.getByRole('button', { name: 'Mileage and engine hours information' })
  await userEvent.tab()
  info.focus()
  const tip = await screen.findByRole('tooltip')
  expect(tip).toHaveTextContent('Motive API')
  expect(tip).toHaveTextContent('Motive dashboard')
  expect(tip).toHaveTextContent(new Date(base.captured_at).toLocaleString())
  expect(tip).toHaveTextContent(new Date(hours.captured_at).toLocaleString())
  expect(info).toHaveAttribute('aria-describedby', tip.id)
  await userEvent.click(info)
  await userEvent.click(info)
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})
