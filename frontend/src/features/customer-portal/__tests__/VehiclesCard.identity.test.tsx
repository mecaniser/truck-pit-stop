import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
const mocks=vi.hoisted(()=>({get:vi.fn(),put:vi.fn()}))
vi.mock('@/lib/api',()=>({default:{get:mocks.get,put:mocks.put}}))
import VehiclesCard from '../VehiclesCard'

it('clears the former account editor when the authenticated identity changes',async()=>{
  const user=(suffix:string)=>({id:`user-${suffix}`,tenant_id:`tenant-${suffix}`,customer_id:`customer-${suffix}`,role:'customer',is_active:true} as never)
  const vehicle=(suffix:string)=>({id:suffix,make:`Make-${suffix}`,model:`Model-${suffix}`,vin:`VIN-${suffix}`,notes:`Notes-${suffix}`,license_plate:`PLATE-${suffix}`})
  useAuthStore.setState({user:user('a'),authSessionEpoch:1,isAuthenticated:true})
  mocks.get.mockImplementation(async(url:string)=>({data:[vehicle(url.includes('customer-a')?'a':'b')]}))
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
  render(<QueryClientProvider client={client}><VehiclesCard/></QueryClientProvider>)
  fireEvent.click(await screen.findByTitle('Edit vehicle'))
  expect(screen.getByLabelText('VIN')).toHaveValue('VIN-a')
  act(()=>useAuthStore.setState({user:user('b'),authSessionEpoch:2}))
  await waitFor(()=>expect(mocks.get).toHaveBeenCalledWith('/customers/customer-b/vehicles'))
  await screen.findByText('Make-b Model-b',{exact:false})
  expect(screen.queryByDisplayValue('VIN-a')).not.toBeInTheDocument()
  expect(screen.queryByDisplayValue('Notes-a')).not.toBeInTheDocument()
  expect(screen.queryByRole('form',{name:'Edit vehicle'})).not.toBeInTheDocument()
})
