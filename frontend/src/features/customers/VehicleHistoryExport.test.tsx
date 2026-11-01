import { ControlButton } from '@/components/ui/Controls'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import type { Vehicle } from '@/types'
import VehicleHistoryExport from './VehicleHistoryExport'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const vehicle = { id: 'vehicle-a', unit_number: 'C-001', make: 'Freightliner', model: 'Cascadia' } as Vehicle
const createUrl = vi.fn(() => 'blob:history-file')
let clicks: string[]
const auth = (role = 'garage_owner', tenant = 'tenant-a', actor = 'staff-a') => useAuthStore.setState({
  user: { id: actor, tenant_id: tenant, role } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>,
  isAuthenticated: true, logoutInProgress: false, authSessionEpoch: 0,
})
const response = () => ({ data: new Blob(['Vehicle ID,Source\r\nvehicle-a,Shop work\r\n']), headers: { 'content-type': 'text/csv; charset=utf-8', 'x-export-row-count': '27', 'x-export-vehicle-id': 'vehicle-a' } })
async function open() { await userEvent.click(screen.getByRole('button', { name: 'Export history' })) }
async function download() { await userEvent.click(screen.getByRole('button', { name: /Download CSV|Retry download/ })) }
function range(from: string, to: string) {
  fireEvent.change(screen.getByLabelText('History from'), { target: { value: from } })
  fireEvent.change(screen.getByLabelText('History to'), { target: { value: to } })
}
beforeEach(() => {
  vi.clearAllMocks(); auth(); clicks = []
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createUrl })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(document.body.contains(this)).toBe(true); clicks.push(this.download)
  })
  api.get.mockResolvedValue(response())
})
afterEach(() => { vi.restoreAllMocks() })
describe('vehicle service-history export', () => {
  it.each(['garage_owner', 'garage_admin', 'receptionist'])('offers %s an explicit all-pages export without fetching on open', async role => {
    auth(role); render(<VehicleHistoryExport vehicle={vehicle} />); await open()
    expect(screen.getByRole('form')).toHaveTextContent('across all pages')
    expect(screen.getByRole('form')).toHaveTextContent('Internal notes and prices are excluded')
    expect(api.get).not.toHaveBeenCalled()
  })
  it.each(['mechanic', 'driver', 'customer', 'fleet_manager', 'super_admin'])('hides the export for %s while preserving existing order action', role => {
    auth(role); render(<VehicleHistoryExport vehicle={vehicle}><ControlButton>New repair order</ControlButton></VehicleHistoryExport>)
    expect(screen.queryByRole('button', { name: 'Export history' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New repair order' })).toBeVisible(); expect(api.get).not.toHaveBeenCalled()
  })
  it('downloads the exact vehicle, all matching rows and no visible-page parameters', async () => {
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); await download()
    expect(await screen.findByRole('status')).toHaveTextContent('Downloaded 27 service records')
    expect(api.get).toHaveBeenCalledWith('/vehicles/vehicle-a/service-history.csv', { params: {}, responseType: 'blob', signal: expect.any(AbortSignal) })
    expect(clicks).toEqual(['vehicle-service-history-vehicle-a.csv']); expect(document.querySelector('a[download]')).toBeNull()
  })
  it('retains dates after failure and retries only on an explicit action', async () => {
    api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(response())
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); range('2026-10-01', '2026-10-14'); await download()
    expect(await screen.findByRole('alert')).toHaveTextContent('Your dates are kept')
    expect(screen.getByLabelText('History from')).toHaveValue('2026-10-01'); expect(clicks).toEqual([])
    await download(); expect(await screen.findByRole('status')).toBeVisible()
    expect(api.get).toHaveBeenLastCalledWith('/vehicles/vehicle-a/service-history.csv', expect.objectContaining({ params: { date_from: '2026-10-01', date_to: '2026-10-14' } }))
    expect(clicks).toHaveLength(1)
  })
  it.each([
    ['history_empty', 'No completed shop work'],
    ['history_export_too_large', 'narrower date range'],
    ['vehicle_not_found', 'vehicle is no longer available'],
  ])('reads JSON error blobs for %s without downloading them', async (code, message) => {
    const data = new Blob([JSON.stringify({ detail: { code } })], { type: 'application/json' })
    Object.defineProperty(data, 'text', { value: async () => JSON.stringify({ detail: { code } }) })
    api.get.mockRejectedValue({ response: { status: 404, data } })
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); await download()
    expect(await screen.findByRole('alert')).toHaveTextContent(message); expect(createUrl).not.toHaveBeenCalled()
  })
  it('rejects reversed dates before requesting and accepts a single bound', async () => {
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); range('2026-10-15', '2026-10-01'); await download()
    expect(await screen.findByRole('alert')).toHaveTextContent('on or before'); expect(api.get).not.toHaveBeenCalled()
    range('2026-10-01', ''); await download()
    expect(api.get).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ params: { date_from: '2026-10-01' } }))
  })
  it.each(['2026-02-31', '2026-2-01', '1899-12-31', 'bad date'])('rejects invalid typed date %s', async value => {
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); range(value, ''); await download()
    expect(await screen.findByRole('alert')).toHaveTextContent('valid history dates'); expect(api.get).not.toHaveBeenCalled()
  })
  it('selects a calendar date, closes only the calendar with Escape and clears the range', async () => {
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); range('2026-10-01', '')
    const picker = within(screen.getByLabelText('History from').closest('.db-datepicker') as HTMLElement)
    await userEvent.click(picker.getByRole('button', { name: 'Choose date — Oct 1, 2026' }))
    await userEvent.click(picker.getByRole('button', { name: 'Oct 2, 2026', exact: true }))
    expect(screen.getByLabelText('History from')).toHaveValue('2026-10-02')
    await userEvent.click(picker.getByRole('button', { name: 'Choose date — Oct 2, 2026' })); await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expect(screen.getByRole('form')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear dates' })); await download()
    expect(api.get).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ params: {} }))
  })
  it('closes an open calendar when Enter in its text field starts an export', async () => {
    api.get.mockImplementation(() => new Promise(() => {}))
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); range('2026-10-01', '')
    await userEvent.click(screen.getByRole('button', { name: 'Choose date — Oct 1, 2026' }))
    screen.getByRole('textbox', { name: 'History from', exact: true }).focus()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await userEvent.keyboard('{Enter}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByLabelText('History from')).toBeDisabled(); expect(screen.getByLabelText('History from')).toHaveValue('2026-10-01')
    expect(screen.getByRole('button', { name: 'Preparing…' })).toBeDisabled()
  })
  it.each(['wrong-vehicle', 'html', 'empty', 'invalid-count', 'oversize'])('does not download a malformed %s success response', async kind => {
    const value = response()
    if (kind === 'wrong-vehicle') value.headers['x-export-vehicle-id'] = 'vehicle-b'
    if (kind === 'html') value.headers['content-type'] = 'text/html'
    if (kind === 'empty') value.data = new Blob([])
    if (kind === 'invalid-count') value.headers['x-export-row-count'] = 'NaN'
    if (kind === 'oversize') value.data = new Blob(['x'.repeat(2 * 1024 * 1024 + 1)])
    api.get.mockResolvedValue(value); render(<VehicleHistoryExport vehicle={vehicle} />); await open(); await download()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not download'); expect(createUrl).not.toHaveBeenCalled()
  })
  it('cancels a pending export with Escape, aborts and restores trigger focus', async () => {
    let finish!: (value: ReturnType<typeof response>) => void
    api.get.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); await download()
    expect(screen.getByRole('button', { name: 'Preparing…' })).toBeDisabled()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('form')).not.toBeInTheDocument(); expect(screen.getByRole('button', { name: 'Export history' })).toHaveFocus()
    expect(api.get.mock.calls[0][1].signal.aborted).toBe(true)
    await act(async () => finish(response())); expect(clicks).toEqual([])
  })
  it('supports named Cancel dismissal and reopening with dates preserved', async () => {
    render(<VehicleHistoryExport vehicle={vehicle} />); await open(); range('2026-10-01', '')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' })); await open()
    expect(screen.getByLabelText('History from')).toHaveValue('2026-10-01'); expect(api.get).not.toHaveBeenCalled()
  })
  it('consumes Escape before an enclosing drawer but leaves a different dialog alone', async () => {
    const drawerEscape = vi.fn()
    const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') drawerEscape() }
    document.addEventListener('keydown', handler)
    try {
      render(<><VehicleHistoryExport vehicle={vehicle} /><div role="dialog"><ControlButton>Other dialog action</ControlButton></div></>)
      await open(); await userEvent.keyboard('{Escape}')
      expect(drawerEscape).not.toHaveBeenCalled(); expect(screen.queryByRole('form')).not.toBeInTheDocument()
      await open(); screen.getByRole('button', { name: 'Other dialog action' }).focus()
      await userEvent.keyboard('{Escape}')
      expect(drawerEscape).toHaveBeenCalledOnce(); expect(screen.getByRole('form')).toBeInTheDocument()
    } finally { document.removeEventListener('keydown', handler) }
  })
  it.each(['vehicle', 'tenant', 'actor', 'role', 'epoch', 'logout'])('prevents late %s responses from creating a file or carrying filters into the next context', async change => {
    let finish!: (value: ReturnType<typeof response>) => void
    api.get.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const view = render(<VehicleHistoryExport vehicle={vehicle} />); await open(); range('2026-10-01', ''); await download()
    if (change === 'vehicle') view.rerender(<VehicleHistoryExport vehicle={{ ...vehicle, id: 'vehicle-b' }} />)
    else act(() => {
      if (change === 'tenant') auth('garage_owner', 'tenant-b')
      if (change === 'actor') auth('garage_owner', 'tenant-a', 'staff-b')
      if (change === 'role') auth('customer')
      if (change === 'epoch') useAuthStore.setState({ authSessionEpoch: 1 })
      if (change === 'logout') useAuthStore.setState({ logoutInProgress: true })
    })
    await act(async () => finish(response()))
    expect(clicks).toEqual([]); expect(screen.queryByRole('form')).not.toBeInTheDocument()
    expect(api.get.mock.calls[0][1].signal.aborted).toBe(true)
  })
  it('aborts when navigating away', async () => {
    api.get.mockImplementation(() => new Promise(() => {})); const view = render(<VehicleHistoryExport vehicle={vehicle} />)
    await open(); await download(); view.unmount()
    await waitFor(() => expect(api.get.mock.calls[0][1].signal.aborted).toBe(true))
  })
})
