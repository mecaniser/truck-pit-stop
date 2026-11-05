import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import type { Vehicle } from '@/types'
const mocks = vi.hoisted(() => ({ put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { put: mocks.put } }))
import CustomerVehicleEditor from '../CustomerVehicleEditor'
const vehicle = { id:'v1', tenant_id:'tenant', customer_id:'customer', unit_number:'603', vin:'1M8GDM9AXKP042788', make:'Volvo', model:'VNR', year:2020, license_plate:'OLD', color:'White', notes:null } as Vehicle
function show(onClose=vi.fn()) {
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
  const invalidate=vi.spyOn(client,'invalidateQueries')
  const view=render(<QueryClientProvider client={client}><CustomerVehicleEditor vehicle={vehicle} onClose={onClose}/></QueryClientProvider>)
  return {onClose,invalidate,...view}
}
beforeEach(()=>{
  mocks.put.mockReset()
  useAuthStore.setState({user:{id:'u',tenant_id:'tenant',customer_id:'customer',role:'customer',is_active:true} as never,isAuthenticated:true,authSessionEpoch:10})
})
it('keeps VIN read-only and sends only customer-maintained labels',async()=>{
  mocks.put.mockResolvedValue({data:{...vehicle,unit_number:'604'}})
  const {onClose,invalidate}=show()
  expect(screen.getByLabelText('VIN')).toHaveAttribute('readonly')
  expect(screen.getByRole('button',{name:'Save changes'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Unit number'),{target:{value:'604'}})
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
  await waitFor(()=>expect(onClose).toHaveBeenCalledTimes(1))
  expect(mocks.put).toHaveBeenCalledWith('/customers/customer/vehicles/v1',{unit_number:'604',license_plate:'OLD',color:'White',notes:null})
  expect(invalidate).toHaveBeenCalledWith({queryKey:['vehicles']})
  expect(invalidate).toHaveBeenCalledWith({queryKey:['customerVehicles','customer']})
})
it('retains drafts after a failed save and does not retry automatically',async()=>{
  mocks.put.mockRejectedValue(new Error('offline'))
  show()
  fireEvent.change(screen.getByLabelText('License plate'),{target:{value:'NEW'}})
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Your edits are still here')
  expect(screen.getByLabelText('License plate')).toHaveValue('NEW')
  expect(mocks.put).toHaveBeenCalledTimes(1)
})
it('disables fields and cancel during a pending save',async()=>{
  let finish!:(value:unknown)=>void
  mocks.put.mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const {onClose}=show()
  fireEvent.change(screen.getByLabelText('Color'),{target:{value:'Blue'}})
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
  await waitFor(()=>expect(screen.getByLabelText('Color')).toBeDisabled())
  expect(screen.getByRole('button',{name:'Cancel'})).toBeDisabled()
  await act(async()=>{finish({data:vehicle})})
  await waitFor(()=>expect(onClose).toHaveBeenCalledOnce())
})
it('ignores success after the authenticated session changes',async()=>{
  let finish!:(value:unknown)=>void
  mocks.put.mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const {onClose,invalidate}=show()
  fireEvent.change(screen.getByLabelText('Color'),{target:{value:'Blue'}})
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
  await waitFor(()=>expect(mocks.put).toHaveBeenCalledTimes(1))
  act(()=>useAuthStore.setState({authSessionEpoch:11}))
  await act(async()=>{finish({data:vehicle})})
  expect(onClose).not.toHaveBeenCalled()
  expect(invalidate).not.toHaveBeenCalled()
})
it('cancel closes without sending an update',()=>{
  const {onClose}=show()
  fireEvent.change(screen.getByLabelText('Notes'),{target:{value:'Draft'}})
  fireEvent.click(screen.getByRole('button',{name:'Cancel'}))
  expect(onClose).toHaveBeenCalledOnce()
  expect(mocks.put).not.toHaveBeenCalled()
})
it('rejects overlong labels before sending an update',async()=>{
  show()
  fireEvent.change(screen.getByLabelText('License plate'),{target:{value:'x'.repeat(21)}})
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('20 characters')
  expect(mocks.put).not.toHaveBeenCalled()
})
it('rejects a queued submit when its original session has already changed',async()=>{
  const {onClose}=show()
  fireEvent.change(screen.getByLabelText('Color'),{target:{value:'Blue'}})
  fireEvent.submit(screen.getByRole('form',{name:'Edit vehicle'}))
  act(()=>useAuthStore.setState({authSessionEpoch:11}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t save changes')
  expect(mocks.put).not.toHaveBeenCalled()
  expect(onClose).not.toHaveBeenCalled()
})
