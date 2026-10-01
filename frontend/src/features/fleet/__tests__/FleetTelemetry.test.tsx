import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import type { BoardTruck } from '../types'
import { readingFreshness, retained, truckCoordinates, truckMotion, type FleetTelemetry, type ReadingProvenance } from '../telemetry'
import TelemetrySummary from '../TelemetrySummary'
import TelemetryCapture from '../TelemetryCapture'
import FleetMap from '../FleetMap'

const mocks = vi.hoisted(() => ({ post: vi.fn(), positions: [] as number[][], maps: [] as Record<string, unknown>[], errors: [] as (() => void)[], removed: vi.fn(), markerRemoved: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { post: mocks.post } }))
vi.mock('mapbox-gl', () => ({ default: {
  Map: class { constructor(options: Record<string, unknown>) { mocks.maps.push(options) } on(_event: string, cb: () => void) { mocks.errors.push(cb) } addControl() {} jumpTo() {} fitBounds() {} remove() { mocks.removed() } resize() {} },
  Marker: class { setLngLat(point: number[]) { mocks.positions.push(point); return this } setPopup() { return this } addTo() { return this } remove() { mocks.markerRemoved() } },
  Popup: class { setDOMContent() { return this } }, NavigationControl: class {}, LngLatBounds: class { extend() { return this } },
} }))
const now = Date.now()
const provenance: ReadingProvenance = { source: 'motive_dashboard_manual', observed_at: null, captured_at: new Date(now).toISOString(), freshness: 'unknown', snapshot_id: 'synthetic-snapshot', source_age_text: '41s ago' }
const telemetry: FleetTelemetry = { location: { ...provenance, lat: null, lng: null, label: 'Synthetic reported area' }, speed: { ...provenance, value: 0, unit: 'mph', basis: null }, odometer: { ...provenance, value: 123456, unit: 'mi', basis: 'dashboard_unspecified' }, engine_hours: null, fuel: null, fault_count: null, motion: 'unknown' }
const truck = { id: 'synthetic-truck', unit_number: 'TEST-1', make: 'Test', model: 'Truck', vin: '1TEST234567890123', status: 'shop', odometer: 100000, board_membership_customer_id: 'selected-company', board_membership_company_name: 'Selected fleet', fleet_customer_id: 'other-company', owner_company_name: 'Different owner', telemetry, lat: 35, lng: -80, moving: true } as BoardTruck
function wrap(node: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{node}</QueryClientProvider>) }
beforeEach(() => {
  mocks.post.mockReset(); mocks.removed.mockReset(); mocks.markerRemoved.mockReset(); mocks.positions.length = 0; mocks.maps.length = 0; mocks.errors.length = 0
  vi.stubEnv('VITE_MAPBOX_TOKEN', '')
  useAuthStore.setState({ user: { id: 'staff', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
})
afterEach(() => vi.unstubAllEnvs())
describe('reported telemetry semantics', () => {
  it('never uses legacy coordinates and keeps label-only locations unpinned', () => expect(truckCoordinates(truck, now)).toBeNull())
  it('preserves exact zero coordinates without offsets', () => expect(truckCoordinates({ ...truck, telemetry: { ...telemetry, location: { ...telemetry.location!, lat: 0, lng: 0 } } }, now)).toEqual([0, 0]))
  it('retains captured unknown-time readings without claiming fresh or stopped', () => { expect(retained(telemetry.speed, now)?.value).toBe(0); expect(readingFreshness(provenance, now)).toBe('unknown'); expect(truckMotion(truck, now)).toBe('unknown') })
  it('treats known fresh zero speed as stopped and stale motion as unknown', () => {
    const fresh = { ...truck, telemetry: { ...telemetry, speed: { ...telemetry.speed!, observed_at: new Date(now).toISOString() } } }
    expect(truckMotion(fresh, now)).toBe('stopped'); expect(truckMotion(fresh, now + 360000)).toBe('unknown')
  })
  it('expires readings after retention and rejects future timestamps', () => { expect(retained(provenance, now + 31 * 86400000)).toBeNull(); expect(retained({ ...provenance, observed_at: new Date(now + 600000).toISOString() }, now)).toBeNull() })
  it('keeps the card to location and speed, with one shared age and no odometer', () => {
    render(<TelemetrySummary truck={truck} compact />)
    expect(screen.getByText('Synthetic reported area')).toBeInTheDocument()
    expect(screen.getByText('0 mph')).toBeInTheDocument()
    expect(screen.queryByText(/odometer/i)).not.toBeInTheDocument()
    expect(screen.queryByText('123,456 mi')).not.toBeInTheDocument()
    expect(screen.getAllByText(/Manual · saved .* · time unknown/)).toHaveLength(1)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByText(/live|stopped/i)).not.toBeInTheDocument()
  })
  it('keeps reported mileage in detail and reveals full history only on demand', () => {
    render(<TelemetrySummary truck={truck} />)
    expect(screen.getByText('Motive odometer')).toBeInTheDocument()
    expect(screen.getByText('123,456 mi')).toBeInTheDocument()
    expect(screen.queryByText('100,000 mi')).not.toBeInTheDocument()
    expect(screen.queryByText(/observation time unknown/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reading details' }))
    expect(screen.getByText('Motive odometer · dashboard')).toBeInTheDocument()
    expect(screen.getAllByText(/observation time unknown/)).toHaveLength(3)
    expect(screen.getAllByText(/source displayed 41s ago/)).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: 'Reading details' }))
    expect(screen.queryByText(/observation time unknown/)).not.toBeInTheDocument()
  })
  it('does not apply a manual location timestamp to a newer API speed', () => {
    render(<TelemetrySummary compact truck={{ ...truck, telemetry: { ...telemetry, speed: { ...telemetry.speed!, source: 'motive_api', observed_at: new Date(now - 20 * 60000).toISOString() } } }} />)
    expect(screen.getByText(/Manual · saved .* · time unknown/)).toBeInTheDocument()
    expect(screen.getByText('Motive · 20m ago · stale')).toBeInTheDocument()
  })
  it('omits compact telemetry when only odometer is available', () => {
    render(<TelemetrySummary compact truck={{ ...truck, telemetry: { ...telemetry, location: null, speed: null } }} />)
    expect(screen.queryByLabelText('Reported truck readings')).not.toBeInTheDocument()
  })
})
describe('geographic map', () => {
  it('provides an accessible location list when no token exists', () => { const select = vi.fn(); render(<FleetMap trucks={[truck]} onSelect={select} />); expect(screen.getByRole('status')).toHaveTextContent('not configured'); expect(screen.getByText(/No verified coordinates/)).toBeInTheDocument(); fireEvent.click(screen.getByRole('button')); expect(select).toHaveBeenCalledWith(truck); expect(mocks.maps).toHaveLength(0) })
  it('groups coincident coordinates without changing positions and excludes unlocated trucks', async () => {
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'synthetic-token')
    const located = { ...truck, telemetry: { ...telemetry, location: { ...telemetry.location!, lat: 37.25, lng: -105.125 } } }
    render(<FleetMap trucks={[located, { ...located, id: 'second' }, { ...truck, id: 'unknown' }]} />)
    await waitFor(() => expect(mocks.positions).toEqual([[-105.125, 37.25]]))
    expect(screen.getAllByText(/Selected fleet/)).toHaveLength(3)
    fireEvent.click(screen.getAllByRole('button')[0])
  })
  it('does not recreate the map or markers when freshness updates', async () => {
    vi.stubEnv('VITE_MAPBOX_TOKEN', 'synthetic-token')
    const located = { ...truck, telemetry: { ...telemetry, location: { ...telemetry.location!, lat: 37.25, lng: -105.125 } } }
    vi.useFakeTimers()
    const result = render(<FleetMap trucks={[located]} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(mocks.positions).toHaveLength(1)
    act(() => vi.advanceTimersByTime(30000))
    expect(mocks.maps).toHaveLength(1); expect(mocks.removed).not.toHaveBeenCalled(); expect(mocks.markerRemoved).not.toHaveBeenCalled()
    vi.useRealTimers(); result.unmount()
  })
  it('keeps the accessible list on map error', async () => { vi.stubEnv('VITE_MAPBOX_TOKEN', 'synthetic-token'); render(<FleetMap trucks={[truck]} />); await waitFor(() => expect(mocks.errors).toHaveLength(1)); fireEvent(window, new Event('resize')); act(() => mocks.errors[0]()); expect(await screen.findByRole('status')).toHaveTextContent('could not load'); expect(screen.getByRole('button')).toHaveTextContent('TEST-1') })
})
describe('manual capture', () => {
  async function open() { const user = userEvent.setup(); wrap(<TelemetryCapture truck={truck} />); await user.click(screen.getByRole('button', { name: 'Add reading' })); return user }
  it('opens a blank entry only after Add reading and closes it after a successful save', async () => {
    const user = userEvent.setup(); mocks.post.mockResolvedValue({ data: {} }); wrap(<TelemetryCapture truck={truck} />)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add reading' }))
    expect(screen.getByText('Manual Motive reading')).toBeInTheDocument()
    await user.type(screen.getByLabelText('VIN verified in Motive'), truck.vin!)
    await user.type(screen.getByLabelText('Speed (mph)'), '0')
    await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' }))
    await screen.findByText('Motive dashboard snapshot saved.')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add reading' })).toHaveAttribute('aria-expanded', 'false')
  })
  it('is unavailable for customer/fleet manager roles', () => { useAuthStore.setState({ user: { role: 'fleet_manager' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> }); wrap(<TelemetryCapture truck={truck} />); expect(screen.queryByRole('button')).not.toBeInTheDocument() })
  it('does not fall back to operator or owner when selected membership is absent', async () => { wrap(<TelemetryCapture truck={{ ...truck, board_membership_customer_id: null }} />); fireEvent.click(screen.getByRole('button')); expect(screen.getByRole('status')).toHaveTextContent('selected fleet membership'); expect(screen.queryByRole('form')).not.toBeInTheDocument() })
  it('requires exact verified VIN and actual reading', async () => { const user = await open(); await user.type(screen.getByLabelText('VIN verified in Motive'), '1WRNG234567890123'); await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' })); expect(screen.getByRole('status')).toHaveTextContent('exact VIN'); expect(mocks.post).not.toHaveBeenCalled() })
  it('rejects a capture with no observed readings and an unpaired coordinate', async () => {
    const user = await open(); await user.type(screen.getByLabelText('VIN verified in Motive'), truck.vin!)
    await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' })); expect(screen.getByRole('status')).toHaveTextContent('at least one reading')
    await user.type(screen.getByLabelText('Verified truck latitude'), '0'); await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' })); expect(screen.getByRole('status')).toHaveTextContent('both verified coordinates'); expect(mocks.post).not.toHaveBeenCalled()
  })
  it('requires timezone on an exact timestamp and never estimates it from age text', async () => {
    mocks.post.mockResolvedValue({ data: {} })
    const user = await open(); await user.type(screen.getByLabelText('VIN verified in Motive'), truck.vin!); await user.type(screen.getByLabelText('Speed (mph)'), '0')
    await user.type(screen.getByLabelText('Exact observation time (optional)'), '2026-01-01T12:00:00'); await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' })); expect(screen.getByRole('status')).toHaveTextContent('timestamp with timezone')
    await user.clear(screen.getByLabelText('Exact observation time (optional)')); await user.type(screen.getByLabelText('Source age text (if displayed)'), '41s ago'); await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' })); await screen.findByText('Motive dashboard snapshot saved.')
    expect(mocks.post.mock.calls[0][1]).toEqual(expect.objectContaining({ observed_at: null, source_age_text: '41s ago' }))
  })
  it('submits selected membership and zero, leaves unknowns null, retries with same id', async () => {
    mocks.post.mockRejectedValueOnce({ response: { status: 503 } }).mockResolvedValueOnce({ data: {} })
    const user = await open()
    await user.type(screen.getByLabelText('VIN verified in Motive'), truck.vin!)
    await user.type(screen.getByLabelText('Speed (mph)'), '0')
    await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' }))
    await screen.findByText(/safely reuse/)
    await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' }))
    await screen.findByText('Motive dashboard snapshot saved.')
    expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(mocks.post.mock.calls[0][1]).toEqual(expect.objectContaining({ fleet_customer_id: 'selected-company', vin: truck.vin, speed_mph: 0, lat: null, lng: null, odometer_miles: null, observed_at: null }))
    expect(mocks.post.mock.calls[1][1].client_request_id).toBe(mocks.post.mock.calls[0][1].client_request_id)
    expect(mocks.post.mock.calls[0][0]).toBe('/fleet/trucks/synthetic-truck/telemetry-snapshots')
  })
  it('uses a new request id after editing a failed capture and hides raw errors', async () => {
    mocks.post.mockRejectedValue({ response: { status: 503, data: { detail: 'secret-provider-payload' } } })
    const user = await open(); await user.type(screen.getByLabelText('VIN verified in Motive'), truck.vin!); await user.type(screen.getByLabelText('Speed (mph)'), '2'); await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' })); await screen.findByText(/safely reuse/)
    await user.clear(screen.getByLabelText('Speed (mph)')); await user.type(screen.getByLabelText('Speed (mph)'), '3'); await user.click(screen.getByRole('button', { name: 'Save dashboard snapshot' })); await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2))
    expect(mocks.post.mock.calls[1][1].client_request_id).not.toBe(mocks.post.mock.calls[0][1].client_request_id); expect(screen.queryByText(/secret-provider/)).not.toBeInTheDocument()
  })
})
