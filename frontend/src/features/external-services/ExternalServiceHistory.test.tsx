import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { ExternalServiceHistory } from './ExternalServiceHistory'
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const record = { id: 'service-a', vehicle_id: 'vehicle-a', original_vehicle_id: 'vehicle-a', source: 'external', currency: 'USD', provider_name: 'Outside QA Shop', service_date: '2026-10-01', description: 'Replaced air dryer', odometer: 425000, reference: 'EXT-1', reported_cost: '240.50' as string | null, version: 1, voided_at: null as string | null, created_at: '2026-10-14T15:00:00Z', updated_at: '2026-10-14T15:00:00Z', created_by_user_id: 'staff-a', created_by_name: 'Casey Staff', updated_by_user_id: 'staff-a', updated_by_name: 'Casey Staff' }
let rows: typeof record[]
function auth(role = 'garage_owner', tenant = 'tenant-a', actor = 'staff-a') { useAuthStore.setState({ user: { id: actor, tenant_id: tenant, role } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, authSessionEpoch: 0 }) }
function mount(vehicleId = 'vehicle-a') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const child = (id: string) => <QueryClientProvider client={client}><ExternalServiceHistory vehicleId={id} /></QueryClientProvider>
  const view = render(child(vehicleId)); return { ...view, client, change: (id: string) => view.rerender(child(id)) }
}
async function compose() {
  const user = userEvent.setup(); await waitFor(() => expect(screen.getByRole('button', { name: 'Add outside service' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: 'Add outside service' })); await user.type(screen.getByLabelText('Outside shop'), 'Outside QA Shop')
  fireEvent.change(screen.getByLabelText('Service date'), { target: { value: '2026-10-01' } }); await user.type(screen.getByLabelText('Work performed'), 'Replaced air dryer'); return user
}
beforeEach(() => {
  vi.clearAllMocks(); auth(); rows = []
  api.get.mockImplementation(async (_url, config) => {
    const { search = '', skip = 0, limit = 10, include_voided = false } = config?.params ?? {}
    const matches = rows.filter(row => (include_voided || !row.voided_at) && [row.provider_name, row.description, row.reference].some(value => value?.toLowerCase().includes(search.toLowerCase())))
    return { data: { items: matches.slice(skip, skip + limit), total: matches.length, has_more: skip + limit < matches.length } }
  })
  api.post.mockImplementation(async (_url, body) => { const saved = { ...record, ...body }; rows = [saved]; return { data: { record: saved, replayed: false } } })
  api.put.mockImplementation(async (_url, body) => { const saved = { ...record, ...body, version: 2 }; rows = [saved]; return { data: { record: saved, replayed: false } } })
})
describe('outside-shop history', () => {
  it('creates only a historical record with optional cost and mileage', async () => {
    mount(); const user = await compose(); await user.type(screen.getByLabelText('Mileage at service'), '425000'); await user.type(screen.getByLabelText('Reported cost (USD)'), '240.50'); await user.type(screen.getByLabelText('Reference'), 'EXT-1'); await user.click(screen.getByRole('button', { name: 'Save service' }))
    expect(await screen.findByText('Outside service saved.')).toBeVisible()
    expect(api.post).toHaveBeenCalledExactlyOnceWith('/vehicles/vehicle-a/external-services', { request_id: expect.any(String), provider_name: 'Outside QA Shop', service_date: '2026-10-01', description: 'Replaced air dryer', odometer: 425000, reported_cost: '240.50', reference: 'EXT-1' })
    expect(screen.getByText('Reported cost $240.50')).toBeVisible(); expect(screen.getByText(/Not billed by this shop/)).toBeVisible()
  })
  it('retains the failed draft and exact save ID for explicit retry', async () => {
    api.post.mockRejectedValueOnce(new Error('Response lost')); mount(); const user = await compose(); await user.click(screen.getByRole('button', { name: 'Save service' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your draft is kept'); expect(screen.getByLabelText('Work performed')).toHaveValue('Replaced air dryer')
    await user.click(screen.getByRole('button', { name: 'Retry save' })); expect(await screen.findByText('Outside service saved.')).toBeVisible(); expect(api.post.mock.calls[1]).toEqual(api.post.mock.calls[0])
  })
  it('confirms a replay without describing it as a new record', async () => {
    api.post.mockResolvedValue({ data: { record, replayed: true } }); mount(); const user = await compose(); await user.click(screen.getByRole('button', { name: 'Save service' })); expect(await screen.findByText('Save confirmed. No duplicate added.')).toBeVisible()
  })
  it('prevents double submission and changing pending input', async () => {
    let finish!: (value: unknown) => void; api.post.mockImplementation(() => new Promise(resolve => { finish = resolve })); mount(); const user = await compose(); await user.dblClick(screen.getByRole('button', { name: 'Save service' }))
    expect(api.post).toHaveBeenCalledTimes(1); expect(screen.getByLabelText('Work performed')).toBeDisabled(); expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled(); await act(async () => finish({ data: { record, replayed: false } }))
  })
  it.each(['customer', 'driver', 'mechanic', 'fleet_manager', 'super_admin'])('does not expose or fetch records for %s', role => { auth(role); const view = mount(); expect(view.container).toBeEmptyDOMElement(); expect(api.get).not.toHaveBeenCalled() })
  it.each(['garage_owner', 'garage_admin', 'receptionist'])('allows %s', async role => { auth(role); mount(); expect(await screen.findByText('No outside-shop services recorded for this vehicle.')).toBeVisible() })
  it('distinguishes unknown cost from zero and renders source text safely', async () => {
    rows = [{ ...record, reported_cost: null, description: '<img src=x>' }, { ...record, id: 'service-b', reported_cost: '0.00' }]; const view = mount(); expect(await screen.findByText('Cost not recorded')).toBeVisible(); expect(screen.getByText('Reported cost $0.00')).toBeVisible(); expect(screen.getByText('<img src=x>')).toBeVisible(); expect(view.container.querySelector('img')).toBeNull()
  })
  it('cancels with Escape and Cancel, restoring focus without writes', async () => {
    mount(); const user = await compose(); await user.keyboard('{Escape}'); expect(screen.queryByRole('form')).not.toBeInTheDocument(); await waitFor(() => expect(screen.getByRole('button', { name: 'Add outside service' })).toHaveFocus()); await user.click(screen.getByRole('button', { name: 'Add outside service' })); await user.click(screen.getByRole('button', { name: 'Cancel' })); expect(api.post).not.toHaveBeenCalled()
  })
  it.each([['Mileage at service', '1.5', 'Mileage must'], ['Reported cost (USD)', '-1', 'Reported cost must'], ['Reported cost (USD)', '1.999', 'Reported cost must']])('rejects invalid %s %s', async (label, value, message) => {
    mount(); const user = await compose(); await user.type(screen.getByLabelText(label), value); await user.click(screen.getByRole('button', { name: 'Save service' })); expect(await screen.findByRole('alert')).toHaveTextContent(message); expect(api.post).not.toHaveBeenCalled()
  })
  it('corrects the exact record and disables unchanged saves', async () => {
    rows = [record]; mount(); const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: 'Edit service from Outside QA Shop' })); expect(screen.getByRole('button', { name: 'Save service' })).toBeDisabled(); await user.type(screen.getByLabelText('Work performed'), ' and test'); await user.click(screen.getByRole('button', { name: 'Save service' })); expect(await screen.findByText('Outside service saved.')).toBeVisible(); expect(api.put).toHaveBeenCalledWith('/vehicles/vehicle-a/external-services/service-a', expect.objectContaining({ expected_version: 1, description: 'Replaced air dryer and test' }))
  })
  it('retains stale edits until explicit review of the latest version', async () => {
    rows = [record]; api.put.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'This service record has changed. Refresh it before saving.' } } }); mount(); const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: 'Edit service from Outside QA Shop' })); await user.type(screen.getByLabelText('Work performed'), ' my correction'); await user.click(screen.getByRole('button', { name: 'Save service' })); expect(await screen.findByRole('alert')).toHaveTextContent('has changed')
    rows = [{ ...record, description: 'Another staff correction', version: 2 }]; await user.click(screen.getByRole('button', { name: 'Refresh record' })); expect(await screen.findByText('Latest saved version 2')).toBeVisible(); expect(screen.getByLabelText('Work performed')).toHaveValue('Replaced air dryer my correction'); expect(api.put).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Apply to latest version' })); await user.click(screen.getByRole('button', { name: 'Save service' })); expect(api.put.mock.calls[1][1]).toMatchObject({ expected_version: 2 }); expect(api.put.mock.calls[1][1].request_id).not.toBe(api.put.mock.calls[0][1].request_id)
  })
  it('voids with a reason and restores through the voided filter', async () => {
    rows = [record]; api.post.mockImplementation(async (url) => { rows = [{ ...record, version: url.endsWith('/restore') ? 3 : 2, voided_at: url.endsWith('/restore') ? null : '2026-10-14T17:00:00Z' }]; return { data: { record: rows[0], replayed: false } } }); mount(); const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: 'Void service from Outside QA Shop' })); await user.type(screen.getByLabelText('Reason'), 'Wrong truck'); await user.click(screen.getByRole('button', { name: 'Void service', exact: true })); expect(await screen.findByText(/Service voided/)).toBeVisible(); expect(api.post.mock.calls[0][1]).toMatchObject({ reason: 'Wrong truck', expected_version: 1 }); await user.click(screen.getByLabelText('Show voided')); await user.click(await screen.findByRole('button', { name: 'Restore service from Outside QA Shop' })); await user.click(screen.getByRole('button', { name: 'Restore service', exact: true })); expect(await screen.findByText('Service restored.')).toBeVisible(); expect(api.post.mock.calls[1][1]).toMatchObject({ expected_version: 2 })
  })
  it('loads change history only on request with original values', async () => {
    rows = [record]; api.get.mockImplementation(async url => ({ data: url.endsWith('/history') ? { items: [{ id: 'event-a', record_id: record.id, version: 1, action: 'create', actor_name: 'Original Staff', created_at: record.created_at, reason: null, snapshot: { ...record, description: 'Original work details' } }], total: 1, has_more: false } : { items: rows, total: 1, has_more: false } })); mount(); const user = userEvent.setup(); await screen.findByText('Replaced air dryer'); expect(api.get.mock.calls).toHaveLength(1); await user.click(screen.getByRole('button', { name: 'Change history for Outside QA Shop' })); expect(await screen.findByText('Original work details')).toBeVisible(); expect(screen.getByText(/Original Staff/)).toBeVisible()
  })
  it('hides stale cached records after refresh failure and supports retry', async () => {
    rows = [record]; const view = mount(); await screen.findByText('Replaced air dryer'); api.get.mockRejectedValueOnce(new Error('offline')); await act(() => view.client.invalidateQueries({ queryKey: ['external-services'] })); expect(await screen.findByRole('alert')).toHaveTextContent('Could not load outside-shop history'); expect(screen.queryByText('Replaced air dryer')).not.toBeInTheDocument(); await userEvent.setup().click(screen.getByRole('button', { name: 'Retry outside history' })); expect(await screen.findByText('Replaced air dryer')).toBeVisible()
  })
  it('clears data and drafts on vehicle and identity changes', async () => {
    rows = [record]; const view = mount(); const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: 'Edit service from Outside QA Shop' })); api.get.mockImplementation(() => new Promise(() => {})); view.change('vehicle-b'); expect(screen.queryByDisplayValue('Replaced air dryer')).not.toBeInTheDocument(); expect(screen.queryByText('Replaced air dryer')).not.toBeInTheDocument(); act(() => auth('customer')); expect(view.container).toBeEmptyDOMElement(); act(() => auth('garage_owner', 'tenant-b', 'staff-b')); expect(screen.queryByText('Replaced air dryer')).not.toBeInTheDocument()
  })
  it('rejects mismatched vehicle data', async () => {
    api.get.mockResolvedValue({ data: { items: [{ ...record, vehicle_id: 'wrong-vehicle' }], total: 1, has_more: false } }); mount(); expect(await screen.findByRole('alert')).toHaveTextContent('Could not load outside-shop history'); expect(screen.queryByText('Replaced air dryer')).not.toBeInTheDocument()
  })
  it.each([{ reported_cost: 'NaN' }, { service_date: '2026-02-31' }, { odometer: -1 }])('rejects malformed financial/date/mileage fields %j', async invalid => {
    api.get.mockResolvedValue({ data: { items: [{ ...record, ...invalid }], total: 1, has_more: false } }); mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load outside-shop history')
    expect(screen.queryByText('Replaced air dryer')).not.toBeInTheDocument()
  })
  it('hides an editor after access loss but keeps a named dismissal available', async () => {
    rows = [record]; const view = mount(); await userEvent.setup().click(await screen.findByRole('button', { name: 'Edit service from Outside QA Shop' }))
    api.get.mockRejectedValue({ response: { status: 403 } }); await act(() => view.client.invalidateQueries({ queryKey: ['external-services'] }))
    await screen.findByRole('button', { name: 'Close service editor' })
    expect(screen.queryByDisplayValue('Replaced air dryer')).not.toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Close service editor' }))
    expect(screen.queryByRole('button', { name: 'Close service editor' })).not.toBeInTheDocument()
  })
  it.each(['vehicle', 'session'])('ignores an old save completion after a %s change', async change => {
    let finish!: (value: unknown) => void
    api.post.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const view = mount(); const user = await compose()
    await user.click(screen.getByRole('button', { name: 'Save service' }))
    if (change === 'vehicle') view.change('vehicle-b')
    else act(() => useAuthStore.setState({ authSessionEpoch: 1 }))
    const nextUser = await compose()
    await nextUser.type(screen.getByLabelText('Work performed'), ' new context draft')
    await act(async () => finish({ data: { record, replayed: false } }))
    expect(screen.getByLabelText('Work performed')).toHaveValue('Replaced air dryer new context draft')
    expect(screen.queryByText('Outside service saved.')).not.toBeInTheDocument()
    expect(screen.queryByText('Reported cost $240.50')).not.toBeInTheDocument()
  })
})

describe('outside-shop history search', () => {
  it('searches the entire history, resets paging, preserves filters on Cancel and Escape, and clears', async () => {
    rows = [...Array.from({ length: 11 }, (_, i) => ({ ...record, id: `service-${i}`, description: `Recent ${i}` })), { ...record, id: 'older', provider_name: 'Older shop', description: 'Needle valve' }]
    mount(); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Next services' }))
    expect(await screen.findByText('Page 2')).toBeVisible()
    const search = screen.getByRole('searchbox', { name: 'Search outside-shop history' })
    await user.type(search, '  needle  ')
    expect(await screen.findByRole('heading', { name: 'Outside-shop history (1 matching)' })).toBeVisible()
    expect(screen.queryByText('Page 2')).not.toBeInTheDocument()
    expect(api.get).toHaveBeenLastCalledWith('/vehicles/vehicle-a/external-services', expect.objectContaining({ params: expect.objectContaining({ skip: 0, search: 'needle' }), signal: expect.any(AbortSignal) }))
    for (const cancel of ['Cancel', 'Escape']) {
      await user.click(screen.getByRole('button', { name: 'Edit service from Older shop' }))
      expect(search).toBeDisabled(); expect(screen.getByRole('button', { name: 'Clear search' })).toBeDisabled(); expect(screen.getByLabelText('Show voided')).toBeDisabled()
      await user.type(screen.getByLabelText('Work performed'), ' draft')
      if (cancel === 'Cancel') await user.click(screen.getByRole('button', { name: 'Cancel' }))
      else await user.keyboard('{Escape}')
      expect(search).toHaveValue('  needle  '); expect(screen.getByText('Needle valve')).toBeVisible()
    }
    await user.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(await screen.findByText('Recent 0')).toBeVisible(); expect(search).toHaveFocus(); expect(api.put).not.toHaveBeenCalled()
  })
  it('hides previous results while typing and ignores a delayed earlier search response', async () => {
    rows = [record]; const original = api.get.getMockImplementation()!
    let resolveOld!: (value: unknown) => void
    api.get.mockImplementation((url, config) => config.params.search === 'old' ? new Promise(resolve => { resolveOld = resolve }) : original(url, config))
    mount(); const user = userEvent.setup(); await screen.findByText('Replaced air dryer')
    const search = screen.getByRole('searchbox'); fireEvent.change(search, { target: { value: 'old' } })
    expect(screen.queryByText('Replaced air dryer')).not.toBeInTheDocument()
    await waitFor(() => expect(resolveOld).toBeTypeOf('function'))
    await user.clear(search); await user.type(search, 'dryer')
    expect(await screen.findByText('Replaced air dryer')).toBeVisible()
    await act(async () => resolveOld({ data: { items: [{ ...record, description: 'Stale old result' }], total: 1, has_more: false } }))
    expect(screen.queryByText('Stale old result')).not.toBeInTheDocument()
  })
  it('distinguishes failed search from no matches and retries with the same query', async () => {
    rows = [record]; mount(); await screen.findByText('Replaced air dryer')
    api.get.mockRejectedValueOnce(new Error('offline'))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'missing' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load')
    expect(screen.queryByText(/No outside-shop services match/)).not.toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry outside history' }))
    expect(await screen.findByText('No outside-shop services match this search.')).toBeVisible()
    expect(screen.getByRole('searchbox')).toHaveValue('missing')
  })
  it('retains a draft if a conflicting edit removes the record from search results', async () => {
    rows = [record]; mount(); const user = userEvent.setup(); await screen.findByText('Replaced air dryer')
    await user.type(screen.getByRole('searchbox'), 'dryer'); await screen.findByRole('heading', { name: 'Outside-shop history (1 matching)' })
    await user.click(screen.getByRole('button', { name: 'Edit service from Outside QA Shop' })); await user.type(screen.getByLabelText('Work performed'), ' my draft')
    api.put.mockImplementationOnce(async () => { rows = [{ ...record, description: 'Other work', version: 2 }]; throw { response: { status: 409, data: { detail: 'Record changed' } } } })
    await user.click(screen.getByRole('button', { name: 'Save service' })); await screen.findByText('Record changed')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh record' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Refresh record' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('no longer in this list')
    expect(screen.getByLabelText('Work performed')).toHaveValue('Replaced air dryer my draft')
    await user.click(screen.getByRole('button', { name: 'Cancel' })); expect(screen.getByRole('searchbox')).toHaveValue('dryer')
  })
  it('returns to page one with the query retained after the last match on a later page is edited away', async () => {
    rows = Array.from({ length: 11 }, (_, i) => ({ ...record, id: `service-${i}`, provider_name: `Shop ${i}` }))
    mount(); const user = userEvent.setup(); await screen.findByText('Shop 0')
    await user.type(screen.getByRole('searchbox'), 'dryer'); await screen.findByRole('heading', { name: 'Outside-shop history (11 matching)' })
    await user.click(screen.getByRole('button', { name: 'Next services' })); await user.click(await screen.findByRole('button', { name: 'Edit service from Shop 10' }))
    await user.clear(screen.getByLabelText('Work performed')); await user.type(screen.getByLabelText('Work performed'), 'Different work')
    api.put.mockImplementationOnce(async (_url, body) => { rows[10] = { ...rows[10], ...body, version: 2 }; return { data: { record: rows[10], replayed: false } } })
    await user.click(screen.getByRole('button', { name: 'Save service' })); expect(await screen.findByText('Outside service saved.')).toBeVisible()
    expect(await screen.findByText('Shop 0')).toBeVisible(); expect(screen.queryByText('Page 2')).not.toBeInTheDocument(); expect(screen.getByRole('searchbox')).toHaveValue('dryer')
    await user.click(screen.getByRole('button', { name: 'Clear search' })); expect(await screen.findByRole('heading', { name: 'Outside-shop history (11)' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Next services' })); expect(await screen.findByText('Different work')).toBeVisible()
  })
  it('resets search on vehicle or session changes and includes voided matches only when requested', async () => {
    rows = [{ ...record, voided_at: '2026-10-14T17:00:00Z' }]; const view = mount(); const user = userEvent.setup()
    await user.type(screen.getByRole('searchbox'), 'dryer'); await screen.findByText('No outside-shop services match this search.')
    await user.click(screen.getByLabelText('Show voided')); expect(await screen.findByText('Replaced air dryer')).toBeVisible()
    view.change('vehicle-b'); expect(screen.getByRole('searchbox')).toHaveValue('')
    await user.type(screen.getByRole('searchbox'), 'other'); act(() => useAuthStore.setState({ authSessionEpoch: 2 })); expect(screen.getByRole('searchbox')).toHaveValue('')
  })
})
