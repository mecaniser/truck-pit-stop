import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import ProfileSettingsPage from '../ProfileSettingsPage'
const m = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: m.get } }))
vi.mock('@/stores/authStore', async importOriginal => ({ ...await importOriginal<typeof import('@/stores/authStore')>(), useAuthStore: () => ({ user:{id:'u1',tenant_id:'t1',customer_id:'c1',role:'customer',is_active:true},authSessionEpoch:1,authProvider:'legacy',isAuthenticated:true,logoutInProgress:false,setUser:vi.fn() }) }))
const customer = {first_name:'Test',last_name:'Driver',email:'driver@example.com',updated_at:'2026-11-02T12:00:00Z',created_at:'2026-01-02T12:00:00Z'}
const config = {provider:'quickbooks_payments',available:true,context_key:'context-one',save_pending:false}
const mount = () => {
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
  render(<MemoryRouter><QueryClientProvider client={client}><ProfileSettingsPage /></QueryClientProvider></MemoryRouter>)
  return client
}
beforeEach(()=>vi.resetAllMocks())
it('contact summary reports list failure rather than no card and shares session/context cache',async()=>{
  m.get.mockImplementation(async(path:string)=>{
    if(path.startsWith('/customers/')) return {data:customer}
    if(path.endsWith('/config')) return {data:config}
    throw new Error('offline')
  })
  const client=mount()
  expect(await screen.findByText('Saved cards unavailable. Open Payment methods to retry.')).toBeInTheDocument()
  expect(screen.queryByText('No card on file')).not.toBeInTheDocument()
  expect(client.getQueryState(['payment-methods',JSON.stringify([1,'legacy','u1','t1','customer','c1']),'context-one'])?.status).toBe('error')
})
it('contact summary reports pending cards as loading',async()=>{
  m.get.mockImplementation((path:string)=>path.startsWith('/customers/')?Promise.resolve({data:customer}):path.endsWith('/config')?Promise.resolve({data:config}):new Promise(()=>{}))
  mount()
  expect(await screen.findByText('Loading saved cards…')).toBeInTheDocument()
  expect(screen.queryByText('No card on file')).not.toBeInTheDocument()
})
it('contact summary shows no card only for successful empty list',async()=>{
  m.get.mockImplementation(async(path:string)=>({data:path.startsWith('/customers/')?customer:path.endsWith('/config')?config:[]}))
  mount();expect(await screen.findByText('No card on file')).toBeInTheDocument()
})
it('contact summary shows unavailable when no processor capability is active',async()=>{
  m.get.mockImplementation(async(path:string)=>({data:path.startsWith('/customers/')?customer:{...config,available:false}}))
  mount();expect(await screen.findByText('Saved cards unavailable. Open Payment methods to retry.')).toBeInTheDocument()
  expect(m.get.mock.calls.some(([path]) => path === '/payments/cards')).toBe(false)
  expect(screen.queryByText('No card on file')).not.toBeInTheDocument()
})
it('contact summary preserves an unconfirmed save instead of showing an empty wallet',async()=>{
  m.get.mockImplementation(async(path:string)=>({data:path.startsWith('/customers/')?customer:path.endsWith('/config')?{...config,save_pending:true}:[]}))
  mount();expect(await screen.findByText('Card save unconfirmed. Open Payment methods for details.')).toBeInTheDocument()
  expect(screen.queryByText('No card on file')).not.toBeInTheDocument()
})
