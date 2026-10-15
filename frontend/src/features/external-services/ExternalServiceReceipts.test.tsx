import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { ExternalServiceReceipts } from './ExternalServiceReceipts'
import { MAX_RECEIPT_BYTES, type Receipt } from './receipt-contract'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const vehicleId = '11111111-1111-4111-8111-111111111111'
const recordId = '22222222-2222-4222-8222-222222222222'
const otherId = '99999999-9999-4999-8999-999999999999'
const receipt: Receipt = {
  id: '33333333-3333-4333-8333-333333333333', record_id: recordId, vehicle_id: vehicleId, uploaded_vehicle_id: vehicleId,
  filename: 'QA-outside-shop-receipt.pdf', media_type: 'application/pdf', size_bytes: 1024, version: 1, removed_at: null,
  created_at: '2026-10-14T15:00:00Z', updated_at: '2026-10-14T15:00:00Z',
  created_by_user_id: '44444444-4444-4444-8444-444444444444', created_by_name: 'QA Staff',
  updated_by_user_id: '44444444-4444-4444-8444-444444444444', updated_by_name: 'QA Staff',
}
const timestamp = '2026-10-14T16:00:00Z'
const path = `/vehicles/${vehicleId}/external-services/${recordId}/receipts`
let rows: Receipt[]
let parentVersion: number
let parentVoided: string | null
const props = { vehicleId, recordId, recordVersion: 3, voidedAt: null as string | null, providerName: 'QA Outside Shop' }
const auth = (role = 'garage_owner', tenant = 'tenant-a', actor = 'staff-a') => useAuthStore.setState({ user: { id: actor, tenant_id: tenant, role } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, authSessionEpoch: 0 })
const pdf = (name = 'QA receipt.pdf') => new File(['%PDF-1.7\n%%EOF'], name, { type: 'application/pdf' })
const result = (saved = receipt, replayed = false) => ({ data: { receipt: saved, replayed, record_version: parentVersion, record_voided_at: parentVoided } })
const list = (includeRemoved = false) => ({ data: {
  items: rows.filter(row => includeRemoved || !row.removed_at), total: rows.filter(row => includeRemoved || !row.removed_at).length,
  retained_count: rows.length, retained_bytes: rows.reduce((sum, row) => sum + row.size_bytes, 0),
  max_files: 10, max_file_bytes: MAX_RECEIPT_BYTES, max_total_bytes: MAX_RECEIPT_BYTES * 10,
  record_version: parentVersion, record_voided_at: parentVoided,
} })
const failure = (code: string, message: string) => ({ response: { status: 409, data: { detail: { code, message } } } })
function mount(overrides: Partial<typeof props> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let current = { ...props, ...overrides }
  const child = () => <QueryClientProvider client={client}><ExternalServiceReceipts {...current} /></QueryClientProvider>
  const view = render(child())
  return { ...view, client, change: (next: Partial<typeof props>) => { current = { ...current, ...next }; view.rerender(child()) } }
}
async function open() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Receipts for QA Outside Shop' }))
  await waitFor(() => expect(screen.queryByText('Loading receipts…')).not.toBeInTheDocument())
  return user
}
function select(file = pdf()) { fireEvent.change(screen.getByLabelText('Receipt file'), { target: { files: [file] } }); return file }
const binary = () => ({ data: new Blob([new Uint8Array(1024)], { type: 'application/octet-stream' }), status: 200, headers: { 'content-type': 'application/octet-stream' } })

beforeEach(() => {
  vi.clearAllMocks(); auth(); rows = []; parentVersion = 3; parentVoided = null
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:private-receipt'), revokeObjectURL: vi.fn() }))
  api.get.mockImplementation(async (_url, config) => list(config?.params?.include_removed))
  api.post.mockImplementation(async (url, body) => {
    const saved = url.endsWith('/remove') ? { ...rows[0], version: 2, removed_at: timestamp }
      : url.endsWith('/restore') ? { ...rows[0], version: 3, removed_at: null }
        : { ...receipt, filename: body.name }
    rows = [saved]
    return result(saved)
  })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('private outside-shop receipts', () => {
  it('loads only when opened and shows bounded file metadata and attribution', async () => {
    rows = [receipt]; mount(); expect(api.get).not.toHaveBeenCalled(); await open()
    expect(api.get).toHaveBeenCalledExactlyOnceWith(path, expect.objectContaining({ params: { include_removed: false }, signal: expect.any(AbortSignal) }))
    expect(screen.getByText(receipt.filename)).toBeVisible(); expect(screen.getByText('PDF · 1 KiB')).toBeVisible()
    expect(screen.getByText(/Uploaded by QA Staff/)).toBeVisible(); expect(screen.getByText(/1\/10 retained/)).toBeVisible()
  })

  it('uploads raw bytes using authenticated-client headers and the exact record version', async () => {
    mount(); const user = await open(); const file = select(pdf('receipt #1 ü.pdf'))
    await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(await screen.findByText('Receipt uploaded.')).toBeVisible()
    expect(api.post).toHaveBeenCalledExactlyOnceWith(path, file, expect.objectContaining({ headers: { 'Content-Type': 'application/octet-stream', 'X-Request-ID': expect.any(String), 'X-Expected-Record-Version': '3', 'X-Receipt-Filename': encodeURIComponent(file.name) }, signal: expect.any(AbortSignal), skipAuthRefresh: true }))
    expect(screen.queryByRole('button', { name: 'Upload receipt' })).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: `Download ${file.name}` })).toBeEnabled()
    expect(parentVersion).toBe(3)
  })

  it('retains the File and original request ID for an explicit retry after response loss', async () => {
    api.post.mockRejectedValueOnce(new Error('Response lost')).mockResolvedValueOnce(result(receipt, true))
    mount(); const user = await open(); const file = select()
    await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('selection is kept')
    await user.click(screen.getByRole('button', { name: 'Retry upload' }))
    expect(await screen.findByText('Save confirmed. No duplicate added.')).toBeVisible()
    expect(api.post.mock.calls[0][1]).toBe(file); expect(api.post.mock.calls[1][1]).toBe(file)
    expect(api.post.mock.calls[1][2].headers).toEqual(api.post.mock.calls[0][2].headers)
  })

  it('assigns a fresh request ID after changing the file', async () => {
    api.post.mockRejectedValue(new Error('offline')); mount(); const user = await open(); select()
    await user.click(screen.getByRole('button', { name: 'Upload receipt' })); await screen.findByRole('alert')
    select(pdf('different.pdf')); await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(api.post.mock.calls[1][2].headers['X-Request-ID']).not.toBe(api.post.mock.calls[0][2].headers['X-Request-ID'])
  })

  it('allows only one mutation in flight and locks the pending file', async () => {
    let finish!: (value: unknown) => void
    api.post.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    mount(); const user = await open(); select(); await user.dblClick(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(api.post).toHaveBeenCalledTimes(1); expect(screen.getByLabelText('Receipt file')).toBeDisabled(); expect(screen.getByRole('button', { name: 'Clear selection' })).toBeDisabled()
    await act(async () => finish(result()))
  })

  it.each(['Cancel', 'Escape', 'Close receipt action'])('dismisses removal with %s without writing and returns focus', async how => {
    rows = [receipt]; mount(); const user = await open(); const remove = screen.getByRole('button', { name: `Remove ${receipt.filename}` })
    await user.click(remove); await user.type(screen.getByLabelText('Removal reason'), 'Wrong document')
    if (how === 'Escape') await user.keyboard('{Escape}'); else await user.click(screen.getByRole('button', { name: how }))
    expect(screen.queryByRole('form', { name: 'Remove receipt' })).not.toBeInTheDocument(); expect(api.post).not.toHaveBeenCalled()
    await waitFor(() => expect(remove).toHaveFocus())
  })

  it('requires a removal reason and supports remove, Show removed, attributed history and restore', async () => {
    rows = [receipt]; mount(); const user = await open(); await user.click(screen.getByRole('button', { name: `Remove ${receipt.filename}` }))
    fireEvent.submit(screen.getByRole('form', { name: 'Remove receipt' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a reason')
    await user.type(screen.getByLabelText('Removal reason'), '  Wrong receipt  ')
    await user.click(screen.getByRole('button', { name: 'Remove receipt', exact: true }))
    expect(await screen.findByText('Receipt removed. Restore it from Show removed.')).toBeVisible()
    expect(api.post.mock.calls[0]).toEqual([`${path}/${receipt.id}/remove`, { request_id: expect.any(String), expected_record_version: 3, expected_version: 1, reason: 'Wrong receipt' }, expect.objectContaining({ signal: expect.any(AbortSignal) })])
    await user.click(screen.getByLabelText('Show removed')); const restore = await screen.findByRole('button', { name: `Restore ${receipt.filename}` })
    expect(screen.getByText(/Removed by QA Staff/)).toBeVisible()
    api.get.mockImplementation(async (url, config) => url.endsWith('/history') ? { data: { items: [{ id: otherId, receipt_id: receipt.id, record_id: recordId, version: 2, action: 'remove', actor_user_id: receipt.created_by_user_id, actor_name: 'QA Staff', created_at: timestamp, reason: 'Wrong receipt', snapshot: rows[0] }], total: 1, has_more: false } } : list(config?.params?.include_removed))
    await user.click(screen.getByRole('button', { name: `Receipt history for ${receipt.filename}` }))
    expect(await screen.findByText('Wrong receipt')).toBeVisible()
    await user.click(restore)
    expect(await screen.findByText('Receipt restored.')).toBeVisible()
    expect(api.post.mock.calls[1][1]).toMatchObject({ expected_record_version: 3, expected_version: 2 })
    expect(api.post.mock.calls[1][1].request_id).not.toBe(api.post.mock.calls[0][1].request_id)
  })

  it('preserves a stale upload until refreshed versions are explicitly adopted', async () => {
    api.post.mockRejectedValueOnce(failure('record_changed', 'This service record has changed. Refresh it before saving.'))
    mount(); const user = await open(); const file = select()
    await user.click(screen.getByRole('button', { name: 'Upload receipt' })); await screen.findByText(/has changed/)
    expect(screen.getByRole('button', { name: 'Retry upload' })).toBeDisabled()
    parentVersion = 4
    await user.click(screen.getByRole('button', { name: 'Refresh receipts / record' }))
    await user.click(await screen.findByRole('button', { name: 'Use refreshed version' }))
    expect(api.post).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(await screen.findByText('Receipt uploaded.')).toBeVisible()
    expect(api.post.mock.calls[1][1]).toBe(file)
    expect(api.post.mock.calls[1][2].headers['X-Expected-Record-Version']).toBe('4')
    expect(api.post.mock.calls[1][2].headers['X-Request-ID']).not.toBe(api.post.mock.calls[0][2].headers['X-Request-ID'])
  })

  it('keeps a stale removal reason and uses a fresh receipt version only after confirmation', async () => {
    rows = [receipt]; api.post.mockRejectedValueOnce(failure('receipt_changed', 'This receipt has changed. Refresh it before saving.'))
    mount(); const user = await open(); await user.click(screen.getByRole('button', { name: `Remove ${receipt.filename}` }))
    await user.type(screen.getByLabelText('Removal reason'), 'My correction'); await user.click(screen.getByRole('button', { name: 'Remove receipt', exact: true }))
    await screen.findByText(/receipt has changed/); rows = [{ ...receipt, version: 3 }]
    await user.click(screen.getByRole('button', { name: 'Refresh receipts / record' })); await user.click(await screen.findByRole('button', { name: 'Use refreshed version' }))
    expect(screen.getByLabelText('Removal reason')).toHaveValue('My correction')
    await user.click(screen.getByRole('button', { name: 'Remove receipt', exact: true }))
    expect(api.post.mock.calls[1][1]).toMatchObject({ expected_version: 3, reason: 'My correction' })
    expect(api.post.mock.calls[1][1].request_id).not.toBe(api.post.mock.calls[0][1].request_id)
  })

  it.each(['remove', 'restore'] as const)('retries an uncertain %s with its original normalized payload and ID', async kind => {
    rows = [{ ...receipt, removed_at: kind === 'restore' ? timestamp : null }]
    api.post.mockRejectedValueOnce(new Error('lost response')).mockResolvedValueOnce(result(receipt, true))
    mount(); const user = await open()
    if (kind === 'restore') {
      await user.click(screen.getByLabelText('Show removed'))
      await user.click(await screen.findByRole('button', { name: `Restore ${receipt.filename}` }))
    } else {
      await user.click(screen.getByRole('button', { name: `Remove ${receipt.filename}` }))
      await user.type(screen.getByLabelText('Removal reason'), 'Wrong file')
      await user.click(screen.getByRole('button', { name: 'Remove receipt', exact: true }))
    }
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be confirmed')
    if (kind === 'remove') await user.type(screen.getByLabelText('Removal reason'), '  ')
    await user.click(screen.getByRole('button', { name: kind === 'remove' ? 'Remove receipt' : 'Retry restore', exact: true }))
    expect(await screen.findByText('Save confirmed. No duplicate added.')).toBeVisible()
    expect(api.post.mock.calls[1][1]).toEqual(api.post.mock.calls[0][1])
    expect(api.post.mock.calls[1][2].skipAuthRefresh).toBe(true)
  })

  it('hides an open removal draft after metadata access fails and leaves a named dismissal', async () => {
    rows = [receipt]; const view = mount(); const user = await open()
    await user.click(screen.getByRole('button', { name: `Remove ${receipt.filename}` }))
    await user.type(screen.getByLabelText('Removal reason'), 'Kept draft')
    api.get.mockRejectedValueOnce({ response: { status: 403 } })
    await act(() => view.client.invalidateQueries({ queryKey: ['external-service-receipts'] }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load receipts')
    expect(screen.queryByText(receipt.filename)).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('Kept draft')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Close receipt action' }))
    expect(screen.queryByRole('button', { name: 'Close receipt action' })).not.toBeInTheDocument()
  })

  it('keeps a confirmed save successful when refresh fails and hides stale rows', async () => {
    rows = [receipt]; const view = mount(); const user = await open(); select()
    api.get.mockRejectedValueOnce(new Error('offline'))
    await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(await screen.findByText('Receipt uploaded.')).toBeVisible()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load receipts')
    expect(screen.queryByRole('button', { name: `Download ${receipt.filename}` })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry receipts' }))
    expect(await screen.findByRole('button', { name: 'Download QA receipt.pdf' })).toBeEnabled()
    expect(api.post).toHaveBeenCalledTimes(1)
    await act(() => view.client.invalidateQueries({ queryKey: ['external-service-receipts'] }))
    expect(api.post).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['empty', () => new File([], 'empty.pdf', { type: 'application/pdf' }), 'not empty'],
    ['unsupported', () => new File(['test'], 'file.html', { type: 'text/html' }), 'PDF, JPEG or PNG'],
    ['oversize', () => new File([new Uint8Array(MAX_RECEIPT_BYTES + 1)], 'large.pdf', { type: 'application/pdf' }), 'up to 5 MiB'],
  ] as const)('blocks an invalid selected file %s before sending bytes', async (_name, makeFile, message) => {
    mount(); await open(); select(makeFile())
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('button', { name: 'Upload receipt' })).toBeDisabled(); expect(api.post).not.toHaveBeenCalled()
  })

  it('counts removed files toward capacity while allowing their restoration', async () => {
    rows = Array.from({ length: 10 }, (_, index) => ({ ...receipt, id: `33333333-3333-4333-8333-${String(index).padStart(12, '0')}`, filename: `Receipt ${index}.pdf`, removed_at: timestamp }))
    mount(); const user = await open()
    expect(screen.getByRole('button', { name: 'Choose file' })).toBeDisabled()
    expect(screen.getByText(/10\/10 retained/)).toBeVisible(); expect(screen.getByText(/Removed files still count/)).toBeVisible()
    await user.click(screen.getByLabelText('Show removed'))
    expect(await screen.findByRole('button', { name: 'Restore Receipt 0.pdf' })).toBeEnabled()
  })

  it('shows a removed duplicate with its Restore action instead of uploading another copy', async () => {
    rows = [{ ...receipt, removed_at: timestamp }]
    api.post.mockRejectedValueOnce(failure('duplicate_removed_receipt', 'This file is retained under Show removed. Restore it there.'))
    mount(); const user = await open(); select(); await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Show removed')
    expect(screen.getByLabelText('Show removed')).toBeChecked()
    expect(await screen.findByRole('button', { name: `Restore ${receipt.filename}` })).toBeEnabled()
    expect(api.post).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['duplicate_receipt', 'This file is already attached to this service record.'],
    ['receipt_capacity', 'This service record has reached its retained receipt limit. Removed files still count.'],
    ['receipt_invalid', 'This receipt file is empty, invalid or cannot be safely processed.'],
  ])('shows the precise %s error without clearing the selected file', async (code, message) => {
    api.post.mockRejectedValueOnce(failure(code, message)); mount(); const user = await open(); select()
    await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByText(/QA receipt.pdf ·/)).toBeVisible()
  })

  it.each([{ vehicle_id: otherId }, { record_id: otherId }, { size_bytes: 0 }, { media_type: 'text/html' }])('rejects foreign or malformed metadata %j', async invalid => {
    rows = [{ ...receipt, ...invalid } as Receipt]; mount(); await open()
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load receipts')
    expect(screen.queryByText(receipt.filename)).not.toBeInTheDocument()
  })

  it('rejects a mutation response for a different service and keeps the uncertain attempt', async () => {
    api.post.mockResolvedValueOnce(result({ ...receipt, record_id: otherId })); mount(); const user = await open(); select()
    await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be confirmed')
    expect(screen.queryByText('Receipt uploaded.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry upload' })).toBeEnabled()
  })

  it('rejects foreign receipt history without rendering its reason', async () => {
    rows = [receipt]; mount(); const user = await open()
    api.get.mockResolvedValueOnce({ data: { items: [{ id: otherId, receipt_id: otherId, record_id: recordId, version: 1, action: 'upload', actor_user_id: receipt.created_by_user_id, actor_name: 'Foreign actor', created_at: timestamp, reason: 'Foreign secret', snapshot: receipt }], total: 1, has_more: false } })
    await user.click(screen.getByRole('button', { name: `Receipt history for ${receipt.filename}` }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load receipt history')
    expect(screen.queryByText('Foreign secret')).not.toBeInTheDocument()
  })

  it('downloads only an authenticated exact-sized binary response and revokes its object URL', async () => {
    rows = [receipt]; mount(); const user = await open(); api.get.mockResolvedValueOnce(binary())
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { expect(this.download).toBe(receipt.filename); expect(this.href).toBe('blob:private-receipt') })
    await user.click(screen.getByRole('button', { name: `Download ${receipt.filename}` }))
    expect(api.get.mock.calls[1]).toEqual([`${path}/${receipt.id}/download`, { responseType: 'blob', signal: expect.any(AbortSignal) }])
    expect(click).toHaveBeenCalledTimes(1); expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:private-receipt'))
    expect(document.querySelector('a[download]')).toBeNull()
  })

  it.each(['status', 'type', 'size', 'body'])('rejects an invalid download %s without creating a file', async kind => {
    rows = [receipt]; mount(); const user = await open(); const response = binary()
    if (kind === 'status') response.status = 206
    if (kind === 'type') response.headers['content-type'] = 'text/html'
    if (kind === 'size') response.data = new Blob(['short'], { type: 'application/octet-stream' })
    if (kind === 'body') response.data = { detail: 'Not authorized' } as unknown as Blob
    api.get.mockResolvedValueOnce(response)
    await user.click(screen.getByRole('button', { name: `Download ${receipt.filename}` }))
    expect(await screen.findByRole('alert')).toHaveTextContent(kind === 'body' ? 'Not authorized' : 'Could not download')
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('decodes a bounded JSON error blob without saving it as a receipt', async () => {
    rows = [receipt]; mount(); const user = await open()
    const error = new Blob([JSON.stringify({ detail: { code: 'receipt_removed', message: 'Restore this receipt before downloading it.' } })], { type: 'application/json' })
    Object.assign(error, { text: async () => JSON.stringify({ detail: { code: 'receipt_removed', message: 'Restore this receipt before downloading it.' } }) })
    api.get.mockRejectedValueOnce({ response: { status: 409, data: error } })
    await user.click(screen.getByRole('button', { name: `Download ${receipt.filename}` }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Restore this receipt before downloading it.')
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it.each(['vehicle', 'record', 'tenant', 'actor', 'role', 'session'])('clears metadata, file drafts and cache after a %s change', async change => {
    rows = [receipt]; const view = mount(); const user = await open(); select()
    expect(view.client.getQueryCache().getAll().some(query => query.state.data)).toBe(true)
    if (change === 'vehicle') view.change({ vehicleId: otherId })
    if (change === 'record') view.change({ recordId: otherId })
    if (change === 'tenant') act(() => auth('garage_owner', 'tenant-b'))
    if (change === 'actor') act(() => auth('garage_owner', 'tenant-a', 'staff-b'))
    if (change === 'role') act(() => auth('receptionist'))
    if (change === 'session') act(() => useAuthStore.setState({ authSessionEpoch: 1 }))
    expect(screen.queryByText(receipt.filename)).not.toBeInTheDocument(); expect(screen.queryByText(/QA receipt.pdf ·/)).not.toBeInTheDocument()
    expect(view.client.getQueryCache().getAll().some(query => query.state.data)).toBe(false)
    api.get.mockResolvedValueOnce(list())
    await user.click(screen.getByRole('button', { name: 'Receipts for QA Outside Shop' }))
    expect(screen.queryByRole('button', { name: 'Upload receipt' })).not.toBeInTheDocument()
  })

  it.each(['vehicle', 'session', 'role', 'unmount'])('cancels a late download after %s changes', async change => {
    rows = [receipt]; const view = mount(); const user = await open()
    let finish!: (value: unknown) => void
    api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await user.click(screen.getByRole('button', { name: `Download ${receipt.filename}` }))
    const signal = api.get.mock.calls[1][1].signal as AbortSignal
    if (change === 'vehicle') view.change({ vehicleId: otherId })
    if (change === 'session') act(() => useAuthStore.setState({ authSessionEpoch: 1 }))
    if (change === 'role') act(() => auth('customer'))
    if (change === 'unmount') view.unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => finish(binary()))
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('ignores a late upload response and aborts after moving to another service', async () => {
    const view = mount(); const user = await open(); select()
    let finish!: (value: unknown) => void
    api.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await user.click(screen.getByRole('button', { name: 'Upload receipt' }))
    view.change({ recordId: otherId })
    expect(api.post.mock.calls[0][2].signal.aborted).toBe(true)
    await act(async () => finish(result()))
    expect(screen.queryByText('Receipt uploaded.')).not.toBeInTheDocument()
    expect(view.client.getQueryCache().getAll().some(query => query.state.data)).toBe(false)
  })

  it('discards a late metadata response after switching trucks', async () => {
    let finish!: (value: unknown) => void
    api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const view = mount(); await userEvent.setup().click(screen.getByRole('button', { name: 'Receipts for QA Outside Shop' }))
    const signal = api.get.mock.calls[0][1].signal as AbortSignal
    view.change({ vehicleId: otherId }); rows = [receipt]
    expect(signal.aborted).toBe(true)
    await act(async () => finish(list()))
    expect(screen.queryByText(receipt.filename)).not.toBeInTheDocument()
    expect(view.client.getQueryCache().getAll().some(query => query.state.data)).toBe(false)
  })

  it('does not download a file if its parent becomes voided during the request', async () => {
    rows = [receipt]; const view = mount(); const user = await open()
    let finish!: (value: unknown) => void
    api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await user.click(screen.getByRole('button', { name: `Download ${receipt.filename}` }))
    view.change({ voidedAt: timestamp })
    await act(async () => finish(binary()))
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('keeps voided parent metadata and history readable while all receipt actions stay disabled', async () => {
    rows = [receipt, { ...receipt, id: otherId, filename: 'Removed.pdf', removed_at: timestamp }]; parentVoided = timestamp
    mount({ voidedAt: timestamp }); const user = await open()
    expect(screen.getByText(/Restore this service to upload/)).toBeVisible()
    expect(screen.getByRole('button', { name: `Download ${receipt.filename}` })).toBeDisabled()
    expect(screen.getByRole('button', { name: `Remove ${receipt.filename}` })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Choose file' })).toBeDisabled()
    expect(screen.getByRole('button', { name: `Receipt history for ${receipt.filename}` })).toBeEnabled()
    await user.click(screen.getByLabelText('Show removed'))
    expect(await screen.findByRole('button', { name: 'Restore Removed.pdf' })).toBeDisabled()
  })

  it.each(['customer', 'driver', 'mechanic', 'fleet_manager', 'super_admin'])('does not fetch or expose receipt metadata to %s', role => {
    auth(role); const view = mount(); expect(view.container).toBeEmptyDOMElement(); expect(api.get).not.toHaveBeenCalled()
  })

  it('renders a long Unicode filename as wrapping text without a preview or external link', async () => {
    const filename = `收据-${'Long receipt '.repeat(10)}.pdf`; rows = [{ ...receipt, filename }]
    const view = mount(); await open()
    expect(screen.getByText(filename).closest('.db-receipts__identity')).not.toBeNull()
    expect(view.container.querySelector('img,iframe,object,embed,a')).toBeNull()
    expect(within(view.container).getByRole('button', { name: `Download ${filename}` })).toBeVisible()
  })
})
