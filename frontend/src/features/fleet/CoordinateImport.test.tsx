import { beforeEach, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import CoordinateImport from './CoordinateImport'
import { exampleObservation, observationSchema, makeCheckpoint, persistCheckpoint } from './coordinateImportModel'
vi.mock('../../lib/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
const actor = { id: '22222222-2222-4222-8222-222222222222', tenant_id: exampleObservation.expected_tenant_id, role: 'garage_owner' as const, is_active: true, email: 'fixture@example.invalid', first_name: 'Test', last_name: 'Worker', phone: null, customer_id: null }
const truck = { id: '33333333-3333-4333-8333-333333333333', vin: exampleObservation.vin, board_membership_customer_id: '44444444-4444-4444-8444-444444444444' }
const receipt = { id: '55555555-5555-4555-8555-555555555555', vehicle_id: truck.id, fleet_customer_id: truck.board_membership_customer_id, captured_by_user_id: actor.id, captured_at: '2026-10-06T18:53:25Z', observed_at: null, source: 'motive_dashboard_manual' }
beforeEach(() => { cleanup(); localStorage.clear(); vi.clearAllMocks(); useAuthStore.setState({ user: actor, isAuthenticated: true, authSessionEpoch: 1 }); Object.defineProperty(navigator, 'locks', { configurable: true, value: { request: (_key: string, cb: () => unknown) => cb() } }); vi.mocked(api.get).mockImplementation(async url => ({ data: url === '/auth/me' ? actor : { trucks: [truck] } })); })
const show = () => render(<MemoryRouter><CoordinateImport /></MemoryRouter>)
async function prepare() { fireEvent.change(screen.getByLabelText('Source observation JSON'), { target: { value: JSON.stringify(exampleObservation) } }); fireEvent.click(screen.getByText('Validate')); await screen.findByText('Import observation'); }
it('freezes uncertain submission, reloads same request, verifies receipt and board on replay', async () => {
 vi.mocked(api.post).mockRejectedValueOnce(Error('connection lost'))
 const page = show(); await prepare(); fireEvent.click(screen.getByText('Import observation'))
 await screen.findByText(/Import outcome unconfirmed/)
 expect(screen.getByLabelText('Source observation JSON')).toBeDisabled()
 const first = vi.mocked(api.post).mock.calls[0][1]
 page.unmount(); show(); await screen.findByText('Retry same request')
 vi.mocked(api.post).mockImplementation(async () => {
 vi.mocked(api.get).mockImplementation(async url => ({ data: url === '/auth/me' ? actor : { trucks: [{ ...truck, telemetry: { location: { lat: exampleObservation.lat, lng: exampleObservation.lng, snapshot_id: receipt.id } } }] } }))
 return { status: 200, data: receipt }
 })
 fireEvent.click(screen.getByText('Retry same request'))
 await screen.findByText('Saved receipt and fleet-board coordinates verified.')
 expect(vi.mocked(api.post).mock.calls[1][1]).toEqual(first)
 expect(screen.getByText('Download receipt')).toBeEnabled()
 fireEvent.click(screen.getByText('Verify fleet board')); await waitFor(() => expect(screen.getByText('Verify fleet board')).toBeEnabled()); expect(api.post).toHaveBeenCalledTimes(2)
})
it('prevents POST on membership change or failed context reads', async () => {
 show(); await prepare()
 vi.mocked(api.get).mockRejectedValue(Error('403 access changed'))
 fireEvent.click(screen.getByText('Import observation')); await screen.findByText('403 access changed'); expect(api.post).not.toHaveBeenCalled()
})
it('retains confirmed receipt when board verification fails', async () => {
 show(); await prepare(); vi.mocked(api.post).mockImplementation(async () => { vi.mocked(api.get).mockRejectedValue(Error('offline')); return { status: 201, data: receipt } })
 fireEvent.click(screen.getByText('Import observation')); await screen.findByText('Saved receipt confirmed; fleet-board verification unavailable. Retry verification.')
 expect(screen.getByText('Download receipt')).toBeEnabled(); expect(screen.getByText('Next observation')).toBeDisabled()
})
it('rejects stale preview after an actor switch before commit', async () => {
 show(); await prepare(); act(() => useAuthStore.setState({ authSessionEpoch: 2 })); await waitFor(() => expect(screen.queryByText('Import observation')).not.toBeInTheDocument()); expect(api.post).not.toHaveBeenCalled()
})

it('restores a competing tab checkpoint without posting a second request', async () => {
 show(); await prepare()
 const competing = makeCheckpoint(observationSchema.parse(exampleObservation), actor, truck as import('./types').BoardTruck)
 persistCheckpoint(localStorage, actor, competing)
 fireEvent.click(screen.getByText('Import observation'))
 await screen.findByText(/Another tab saved a request/)
 expect(api.post).not.toHaveBeenCalled()
 expect(screen.getByLabelText('Source observation JSON')).toBeDisabled()
})
it('fails closed when exclusive locks are unavailable', async () => {
 show(); await prepare(); Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined })
 fireEvent.click(screen.getByText('Import observation')); await screen.findByText('Exclusive browser lock unavailable. Import blocked.'); expect(api.post).not.toHaveBeenCalled()
})

it('holds an uncertain checkpoint if any saved location changed', async () => {
 vi.mocked(api.post).mockRejectedValue(Error('connection lost')); show(); await prepare(); fireEvent.click(screen.getByText('Import observation')); await screen.findByText(/Import outcome unconfirmed/)
 vi.mocked(api.get).mockImplementation(async url => ({ data: url === '/auth/me' ? actor : { trucks: [{ ...truck, telemetry: { location: { lat: 10, lng: 20, observed_at: null, snapshot_id: 'newer' } } }] } }))
 fireEvent.click(screen.getByText('Retry same request')); await screen.findByText(/Fleet position changed since validation/); expect(api.post).toHaveBeenCalledTimes(1)
})

it('exports only observation and receipt evidence with delayed blob cleanup', async () => {
 let exportBlob: Blob | undefined
 const createUrl = vi.fn((blob: Blob) => { exportBlob = blob; return 'blob:synthetic-receipt' })
 const revokeUrl = vi.fn()
 Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createUrl })
 Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeUrl })
 const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { expect(document.body.contains(this)).toBe(true); expect(this.download).toMatch(/^coordinate-receipt-.*\.json$/) })
 vi.mocked(api.post).mockResolvedValue({ status: 201, data: receipt })
 show(); await prepare(); fireEvent.click(screen.getByText('Import observation')); await screen.findByText('Download receipt')
 expect(screen.getByText(receipt.id)).toBeInTheDocument(); expect(screen.getByText(receipt.captured_at)).toBeInTheDocument()
 vi.useFakeTimers()
 fireEvent.click(screen.getByText('Download receipt'))
 expect(createUrl).toHaveBeenCalledOnce(); expect(click).toHaveBeenCalledOnce(); expect(revokeUrl).not.toHaveBeenCalled()
 vi.advanceTimersByTime(10000); expect(revokeUrl).toHaveBeenCalledWith('blob:synthetic-receipt')
 vi.useRealTimers()
 const raw = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsText(exportBlob!) })
 const saved = JSON.parse(raw)
 expect(saved.receipt.id).toBe(receipt.id); expect(saved.response_status).toBe(201); expect(saved.fleet_board_verified).toBe(false); expect(saved.payload.client_request_id).toBeTruthy(); expect(saved.source.source_read_time).toBe(exampleObservation.source_read_time)
 expect(Object.keys(saved).sort()).toEqual(['actor_id', 'baseline_location', 'fleet_board_verified', 'payload', 'receipt', 'response_status', 'source', 'tenant_id', 'vehicle_id', 'version'].sort())
 expect(raw).not.toMatch(/access_token|refresh_token|Authorization|password/)
 click.mockRestore()
})
