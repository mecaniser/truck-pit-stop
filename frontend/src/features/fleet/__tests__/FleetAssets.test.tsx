import { useState, type ComponentProps } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import FleetBoard from '../FleetBoard'
import AssetAttachment from '../AssetAttachment'
import TruckDiagnostics from '../TruckDiagnostics'
import type { BoardTruck } from '../types'
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('../FleetActivity', () => ({ default: () => null }))
const asset = (id: string, equipment_type?: BoardTruck['equipment_type']): BoardTruck => ({ id, unit_number: id, equipment_type, make: 'Test', model: 'Equipment', status: 'active', moving: false, pm_interval_miles: 25000, open_work_order_count: 0, open_incident_count: 0 })
const trailer = asset('24', 'trailer'), tractor = asset('603', 'tractor'), unknown = asset('5')
const assets = [trailer, tractor, unknown]
function wrap(node: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{node}</QueryClientProvider>) }
function Board() {
  const [filter, setFilter] = useState<ComponentProps<typeof FleetBoard>['filter']>('all')
  return <FleetBoard data={{ trucks: assets, stats: { total: 3, active: 3, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 } }} onOpen={vi.fn()} onOpenRepairOrder={vi.fn()} filter={filter} setFilter={setFilter} query="" setQuery={vi.fn()} sort="unit" setSort={vi.fn()} />
}
afterEach(() => vi.resetAllMocks())
describe('fleet asset identity', () => {
  it('filters tractors, trailers and unclassified without guessing', async () => {
    wrap(<Board />)
    await userEvent.click(screen.getByRole('button', { name: 'Trailers · 1' }))
    expect(screen.getByRole('button', { name: 'Open 24 trailer details' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Open 603 truck details' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tractors · 1' }))
    expect(screen.getByRole('button', { name: 'Open 603 truck details' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Open 24 trailer details' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Unclassified · 1' }))
    expect(screen.getByRole('button', { name: 'Open 5 truck details' })).toBeVisible()
  })
  it('shows not applicable for missing trailer engine hours', async () => {
    api.get.mockResolvedValue({ data: { last_checked_at: null, codes: [] } })
    wrap(<TruckDiagnostics truckId="24" equipmentType="trailer" />)
    await userEvent.click(screen.getByRole('button', { name: 'View health' }))
    expect(screen.getByRole('heading', { name: 'Trailer health' })).toBeVisible()
    expect(within(screen.getByText('Engine hours').parentElement!).getByText('Not applicable')).toBeVisible()
  })
  it('keeps missing tractor engine hours unavailable', async () => {
    api.get.mockResolvedValue({ data: { last_checked_at: null, codes: [] } })
    wrap(<TruckDiagnostics truckId="603" equipmentType="tractor" />)
    await userEvent.click(screen.getByRole('button', { name: 'View health' }))
    expect(within(screen.getByText('Engine hours').parentElement!).getByText('Unavailable')).toBeVisible()
  })
  it('links an attached asset and detaches with stale-edit protection', async () => {
    const open = vi.fn(); api.put.mockResolvedValue({ data: {} })
    wrap(<AssetAttachment asset={{ ...tractor, attached_asset: { id: '24', unit_number: '24', equipment_type: 'trailer', attached_at: '2026-11-04T23:00:00Z' } }} assets={assets} onOpen={open} />)
    await userEvent.click(screen.getByRole('button', { name: 'Trailer 24' }))
    expect(open).toHaveBeenCalledWith('24')
    await userEvent.click(screen.getByRole('button', { name: 'Detach' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/fleet/trucks/603/attachment', { attached_vehicle_id: null, expected_attached_vehicle_id: '24' }))
    expect(api.patch).not.toHaveBeenCalled()
  })
  it('requires explicit selection of an eligible opposite asset', async () => {
    api.put.mockResolvedValue({ data: {} })
    wrap(<AssetAttachment asset={tractor} assets={assets} onOpen={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Attach', exact: true })).toBeDisabled()
    await userEvent.click(screen.getByRole('combobox', { name: 'Attach trailer' }))
    await userEvent.click(screen.getByRole('option', { name: '24 · Test' }))
    await userEvent.click(screen.getByRole('button', { name: 'Attach', exact: true }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/fleet/trucks/603/attachment', { attached_vehicle_id: '24', expected_attached_vehicle_id: null }))
  })
  it('keeps a real zero engine-hours reading on equipment', async () => {
    api.get.mockResolvedValue({ data: { last_checked_at: null, codes: [] } })
    const stamp = new Date().toISOString()
    wrap(<TruckDiagnostics truckId="24" equipmentType="trailer" telemetry={{ location: null, speed: null, odometer: null, engine_hours: { value: 0, unit: 'h', basis: 'dashboard_unspecified', source: 'motive_dashboard_manual', observed_at: stamp, captured_at: stamp, freshness: 'fresh', snapshot_id: null, source_age_text: null }, fuel: null, fault_count: null, motion: 'unknown' }} />)
    await userEvent.click(screen.getByRole('button', { name: 'View health' }))
    expect(within(screen.getByText('Engine hours').parentElement!).getByText('0 h')).toBeVisible()
    expect(screen.queryByText('Not applicable')).not.toBeInTheDocument()
  })
  it('reports an attachment conflict without retrying or rewriting the asset', async () => {
    api.put.mockRejectedValue({ response: { status: 409 } })
    wrap(<AssetAttachment asset={{ ...tractor, attached_asset: { id: '24', unit_number: '24', equipment_type: 'trailer', attached_at: '2026-11-04T23:00:00Z' } }} assets={assets} onOpen={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Detach' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be saved')
    expect(api.put).toHaveBeenCalledTimes(1)
    expect(api.patch).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Trailer 24' })).toBeVisible()
  })
  it('does not infer attachments for unclassified assets', () => {
    wrap(<AssetAttachment asset={unknown} assets={assets} onOpen={vi.fn()} />)
    expect(screen.getByText('Set the equipment type to attach a tractor or trailer.')).toBeVisible()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})
