import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
import Gate from '../RepairOrderEntryGate'
import { canStartCustomerOrder, loadRepairOrderEntry, readRepairOrderReturn } from '../repairOrderEntry'

const customer = { id: 'bill-to', company_name: 'Carrier' }
const vehicle = { id: 'truck', customer_id: 'different-owner' }
beforeEach(() => { vi.clearAllMocks() })
it('loads only the chosen customer and their linked truck without changing its owner', async () => {
  api.get.mockResolvedValueOnce({ data: customer }).mockResolvedValueOnce({ data: vehicle })
  expect(await loadRepairOrderEntry('bill-to', 'truck')).toEqual({ customer, vehicle })
  expect(api.get.mock.calls.map(([path]) => path)).toEqual(['/customers/bill-to', '/customers/bill-to/vehicles/truck'])
  expect(api.post).not.toHaveBeenCalled()
})
it('leaves truck selection deliberate when starting from the company', async () => {
  api.get.mockResolvedValue({ data: customer })
  expect(await loadRepairOrderEntry('bill-to', null)).toEqual({ customer })
  expect(api.get).toHaveBeenCalledTimes(1)
})
it('rejects a mismatched customer response before loading trucks', async () => {
  api.get.mockResolvedValue({ data: { id: 'foreign' } })
  await expect(loadRepairOrderEntry('bill-to', 'truck')).rejects.toThrow('unavailable')
  expect(api.get).toHaveBeenCalledTimes(1)
})
it('rejects missing or unrelated trucks instead of opening a misleading draft', async () => {
  api.get.mockResolvedValueOnce({ data: customer }).mockResolvedValueOnce({ data: {id:'unrelated'} })
  await expect(loadRepairOrderEntry('bill-to', 'truck')).rejects.toThrow('no longer linked')
})
it.each([403,404,500])('preserves an inaccessible lookup (%s) as failure', async (status) => {
  api.get.mockRejectedValue({response:{status}})
  await expect(loadRepairOrderEntry('bill-to','truck')).rejects.toEqual({response:{status}})
  expect(api.post).not.toHaveBeenCalled()
})
it('shows a recoverable lookup error and delivers exactly once after retry', async () => {
  api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: customer })
  const ready=vi.fn(); const cancel=vi.fn()
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: {queries:{retry:false}} })}><Gate customerId="bill-to" vehicleId={null} onReady={ready} onCancel={cancel} /></QueryClientProvider>)
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load')
  expect(ready).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'Retry'}))
  await waitFor(()=>expect(ready).toHaveBeenCalledTimes(1))
  expect(ready).toHaveBeenCalledWith({customer})
})
it('restricts entry to existing staff roles and return navigation to Customers', () => {
  expect(['garage_owner','garage_admin','receptionist'].every(canStartCustomerOrder)).toBe(true)
  expect(['customer','mechanic','fleet_manager',''].some(canStartCustomerOrder)).toBe(false)
  expect(readRepairOrderReturn({repairOrderReturn:{pathname:'https://evil.invalid',search:'',customerId:'x'}})).toBeNull()
  expect(readRepairOrderReturn(null)).toBeNull()
})
