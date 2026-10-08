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
  it('preserves code zeroes, occurrence zero and uncertain source times', async () => {
    await open({ last_checked_at: '2026-10-07T20:00:00Z', coverage: 'complete', explicit_empty: false, codes: [{ code: null, spn: '0012', fmi: '00', description: 'Example diagnostic', severity: 'High', network: 'J1939', source_address: null, occurrence_count: 0, first_detected_text: null, last_observed_text: 'Oct 7, 2026, 3:12 PM', timezone_basis: 'unverified' }] })
    expect(await screen.findByText('SPN 0012 · FMI 00')).toBeVisible()
    expect(screen.getByText('0')).toBeVisible()
    expect(screen.getByText('Unknown')).toBeVisible()
    expect(screen.getByText('Oct 7, 2026, 3:12 PM')).toBeVisible()
    expect(screen.getByText('Source times · timezone unverified')).toBeVisible()
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
