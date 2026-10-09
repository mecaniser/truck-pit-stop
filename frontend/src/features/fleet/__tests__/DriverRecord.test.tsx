import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DriverRecord from '../DriverRecord'
import FleetBoard from '../FleetBoard'
import type { BoardTruck } from '../types'
import { driverRecord, driverResponse, driverTruck } from './driverRecordFixture'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({ default: { get } }))
vi.mock('../FleetActivity', () => ({ default: () => null }))
const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })
const trigger = () => screen.getByRole('button', { name: /Driver record for Example Driver/ })
function setup(truck: BoardTruck = driverTruck) {
  return render(<QueryClientProvider client={client()}><button>Outside</button><DriverRecord truck={truck} /></QueryClientProvider>)
}
afterEach(() => get.mockReset())

describe('current-driver record', () => {
  it('loads only on opening and preserves source safety, fuel, coaching and event detail', async () => {
    get.mockResolvedValue({ data: driverResponse })
    setup()
    expect(get).not.toHaveBeenCalled()
    expect(trigger()).toHaveTextContent('82')
    expect(trigger().querySelector('[data-band]')).toHaveAttribute('data-band', 'red')
    await userEvent.click(trigger())
    const panel = await screen.findByRole('dialog')
    expect(await within(panel).findByText('68h 14m')).toBeVisible()
    expect(within(panel).getByText('-4.7')).toBeVisible()
    expect(within(panel).getByText('41.4%')).toBeVisible()
    expect(within(panel).getByText('Fair (50–84)')).toBeVisible()
    expect(within(panel).getByText('Never coached')).toBeVisible()
    expect(within(panel).getByText('Partial capture')).toBeVisible()
    expect(within(panel).getAllByText('Pending review')).toHaveLength(2)
    expect(get).toHaveBeenLastCalledWith('/fleet/trucks/synthetic-truck/driver-record')
  })

  it('keeps zero, unknown bands and chart coaching annotations distinct', async () => {
    const record = { ...driverRecord, safety_score: 0, safety_band: 'unknown' as const, safety_band_label: null, safety: { ...driverRecord.safety, score: 0, band: 'unknown' as const, band_label: null, top_behaviors: [{ behavior: 'Zero impact', score_impact: 0 }] }, fuel: { ...driverRecord.fuel, utilization_percent: 0 }, coaching: { ...driverRecord.coaching, open_count: 0 } }
    get.mockResolvedValue({ data: { ...driverResponse, record } })
    setup({ ...driverTruck, driver_record: record })
    expect(trigger()).toHaveTextContent('0')
    expect(trigger().querySelector('[data-band]')).toHaveAttribute('data-band', 'unknown')
    await userEvent.click(trigger())
    expect(await screen.findByText('0%')).toBeVisible()
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '0')
    expect(screen.getByText('Rating unavailable')).toBeVisible()
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(4)
  })

  it('uses neutral dashes and labels stale captures', async () => {
    const record = { ...driverRecord, stale: true }
    get.mockResolvedValue({ data: { ...driverResponse, record } })
    setup({ ...driverTruck, driver_record: record })
    expect(trigger()).toHaveAccessibleName(/stale capture/)
    expect(trigger().querySelector('[data-band]')).toHaveAttribute('data-band', 'unknown')
    await userEvent.click(trigger())
    expect(await screen.findByText('Stale capture')).toBeVisible()
    expect(screen.getByRole('dialog').querySelector('[data-band]')).toHaveAttribute('data-band', 'unknown')
  })

  it.each(['unknown', 'assignment_unverified'] as const)('does not turn %s availability into a score', async availability => {
    get.mockResolvedValue({ data: { ...driverResponse, availability, record: null } })
    setup({ ...driverTruck, driver_record: null })
    expect(trigger()).toHaveTextContent('—')
    await userEvent.click(trigger())
    expect(await screen.findByText(availability === 'unknown' ? 'No verified Motive record is available for this driver.' : 'Motive has not verified the current driver assignment for this truck.')).toBeVisible()
    expect(screen.queryByText('No safety events')).not.toBeInTheDocument()
  })

  it('separates unavailable sections from explicitly empty sections', async () => {
    get.mockResolvedValue({ data: { ...driverResponse, record: { ...driverRecord, sections: { safety: 'unavailable', fuel: 'unavailable', coaching: 'empty', recent_events: 'empty' } } } })
    setup()
    await userEvent.click(trigger())
    expect(await screen.findAllByText('Not available in this capture.')).toHaveLength(2)
    expect(screen.getAllByText('None reported at this check.')).toHaveLength(2)
    expect(screen.queryByRole('meter')).not.toBeInTheDocument()
  })

  it('shows loading and supports close, outside click, Escape and focus return', async () => {
    get.mockReturnValue(new Promise(() => {}))
    setup()
    await userEvent.tab()
    await userEvent.tab()
    await userEvent.keyboard('{Enter}')
    expect(screen.getByRole('status')).toHaveTextContent('Loading driver record')
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger()).toHaveFocus()
    await userEvent.click(trigger())
    await userEvent.click(screen.getByRole('button', { name: 'Close driver record' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await userEvent.click(trigger())
    await userEvent.click(screen.getByRole('button', { name: 'Outside' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('retries errors and rejects a mismatched provider driver', async () => {
    get.mockResolvedValueOnce({ data: { ...driverResponse, record: { ...driverRecord, provider_driver_id: 'different-driver' } } }).mockResolvedValue({ data: driverResponse })
    setup()
    await userEvent.click(trigger())
    expect(await screen.findByRole('alert')).toHaveTextContent('Driver record could not be loaded.')
    expect(screen.queryByText('68h 14m')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('68h 14m')).toBeVisible()
  })

  it('does not attach a record to an unassigned or different managed driver name', () => {
    const { rerender } = render(<DriverRecord truck={{ ...driverTruck, driver_name: null }} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    rerender(<DriverRecord truck={driverTruck} displayName="Different Driver" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('does not display a summary or details belonging to a different driver label', async () => {
    get.mockResolvedValue({ data: { ...driverResponse, record: { ...driverRecord, driver_name: 'Different Driver' } } })
    setup({ ...driverTruck, driver_record: { ...driverRecord, driver_name: 'Different Driver' } })
    expect(trigger()).toHaveTextContent('—')
    await userEvent.click(trigger())
    expect(await screen.findByRole('alert')).toBeVisible()
    expect(screen.queryByText('68h 14m')).not.toBeInTheDocument()
  })

  it('revalidates on reopen and hides previously cached details during that check', async () => {
    get.mockResolvedValueOnce({ data: driverResponse }).mockReturnValue(new Promise(() => {}))
    setup()
    await userEvent.click(trigger())
    expect(await screen.findByText('68h 14m')).toBeVisible()
    await userEvent.keyboard('{Escape}')
    await userEvent.click(trigger())
    expect(screen.getByRole('status')).toHaveTextContent('Loading driver record')
    expect(screen.queryByText('68h 14m')).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('opens from a real fleet card without navigating on click, Enter or Space', async () => {
    const onOpen = vi.fn()
    get.mockResolvedValue({ data: driverResponse })
    render(<QueryClientProvider client={client()}><FleetBoard data={{ trucks: [driverTruck], stats: { total: 1, active: 1, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 } }} onOpen={onOpen} onOpenRepairOrder={vi.fn()} filter="all" setFilter={vi.fn()} query="" setQuery={vi.fn()} sort="attention" setSort={vi.fn()} /></QueryClientProvider>)
    await userEvent.click(trigger())
    await screen.findByText('68h 14m')
    await userEvent.keyboard('{Escape}')
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByRole('dialog')).toBeVisible()
    await userEvent.keyboard('{Escape}')
    await userEvent.keyboard(' ')
    expect(await screen.findByRole('dialog')).toBeVisible()
    expect(onOpen).not.toHaveBeenCalled()
    await userEvent.keyboard('{Escape}')
    await userEvent.click(screen.getByRole('button', { name: /Open TEST-1 truck details/ }))
    expect(onOpen).toHaveBeenCalledWith(driverTruck)
  })
})
