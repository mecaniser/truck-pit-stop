import userEvent from '@testing-library/user-event'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import ProfileSettingsPage from '../ProfileSettingsPage'

const m = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), logout: vi.fn(), epoch: 1 }))
vi.mock('@/lib/api', () => ({ default: { get: m.get, put: m.put } }))
vi.mock('@/stores/authStore', async original => ({
  ...await original<typeof import('@/stores/authStore')>(),
  isCurrentAuthEpoch: () => true,
  useAuthStore: () => ({
    user: { id:'u1',tenant_id:'t1',customer_id:'c1',role:'customer',is_active:true },
    authSessionEpoch:m.epoch,authProvider:'legacy',isAuthenticated:true,logoutInProgress:false,setUser:vi.fn(),logout:m.logout,
  }),
}))
const customer = {first_name:'Test',last_name:'Driver',email:'driver@example.com',updated_at:'2026-11-02T12:00:00Z',created_at:'2026-01-02T12:00:00Z'}
const config = {provider:'quickbooks_payments',available:true,context_key:'context-one',save_pending:false}
function Destination() {
  const location = useLocation()
  return <output aria-label="Destination">{JSON.stringify({path:location.pathname,state:location.state})}</output>
}
function mount(query = '') {
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}})
  const view = render(<MemoryRouter initialEntries={['/portal/settings'+query]}><QueryClientProvider client={client}><ProfileSettingsPage /><Destination /></QueryClientProvider></MemoryRouter>)
  return {client,...view}
}
const click = async (element: HTMLElement) => { await act(async () => { await userEvent.click(element) }) }
beforeEach(()=>{
  vi.resetAllMocks()
  localStorage.clear()
  m.epoch=1
  m.get.mockImplementation(async(path:string)=>({data:path.startsWith('/customers/')?customer:path.endsWith('/config')?config:[]}))
})
it('updates the checkout explanation without changing the separately labeled saved card', async()=>{
  m.get.mockImplementation(async(path:string)=>({data:path.startsWith('/customers/')?customer:path.endsWith('/config')?config:[{id:'card1',brand:'Visa',last4:'4242',is_default:true}]}))
  mount()
  await screen.findByText('Preferred checkout method')
  expect(screen.getByRole('button',{name:'zelle',exact:true})).toHaveAttribute('aria-pressed','true')
  fireEvent.click(screen.getByRole('button',{name:'card',exact:true}))
  expect(screen.getByRole('button',{name:'card',exact:true})).toHaveAttribute('aria-pressed','true')
  expect(screen.getByText('Card is preferred. Available cards and fees are shown at checkout.')).toBeInTheDocument()
  expect(screen.getByText('Saved card for this shop')).toBeInTheDocument()
  expect(screen.getByText(/Card on file: Visa/)).toBeInTheDocument()
  expect(screen.getByText(/on this browser/)).toBeInTheDocument()
})
it('offers Cancel for dirty contact details and restores saved fields',async()=>{
  mount();const name=await screen.findByLabelText('First name')
  expect(screen.getByRole('button',{name:'Save changes'})).toBeDisabled()
  fireEvent.change(name,{target:{value:'Changed'}})
  expect(screen.getByRole('button',{name:'Save changes'})).toBeEnabled()
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Cancel',exact:true}))
  expect(name).toHaveValue('Test')
  expect(screen.getByRole('button',{name:'Save changes'})).toBeDisabled()
  expect(m.put).not.toHaveBeenCalled()
})
it('keeps unsaved fields on failed save and allows retry',async()=>{
  m.put.mockRejectedValue(new Error('offline'))
  mount();const name=await screen.findByLabelText('First name')
  fireEvent.change(name,{target:{value:'Changed'}})
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
  await waitFor(()=>expect(m.put).toHaveBeenCalledTimes(1))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Save changes'})).toBeEnabled())
  expect(name).toHaveValue('Changed')
})
it('clears dirty state after successful save and disables fields while pending',async()=>{
  let saved=customer
  let finish!: (value:unknown)=>void
  m.get.mockImplementation(async(path:string)=>({data:path.startsWith('/customers/')?saved:path.endsWith('/config')?config:[]}))
  m.put.mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  mount();const name=await screen.findByLabelText('First name')
  fireEvent.change(name,{target:{value:'Changed'}})
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
  await waitFor(()=>expect(name).toBeDisabled())
  saved={...customer,first_name:'Changed'}
  finish({data:{user:{...saved}}})
  await waitFor(()=>expect(screen.getByRole('button',{name:'Save changes'})).toBeDisabled())
  await waitFor(()=>expect(name).toBeEnabled())
  expect(name).toHaveValue('Changed')
  expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument()
})
it('places sign out outside Security and associates password fields with their labels',()=>{
  mount('?tab=security')
  expect(within(screen.getByRole('navigation',{name:'Account sections'})).getByRole('button',{name:'Sign out'})).toBeInTheDocument()
  expect(within(screen.getByRole('region',{name:'Security'})).queryByRole('button',{name:'Sign out'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Change Password',exact:true}))
  expect(screen.getByLabelText('Current Password')).toHaveAttribute('autocomplete','current-password')
  expect(screen.getByLabelText('New Password')).toHaveAttribute('autocomplete','new-password')
  expect(screen.getByText(/Use at least 8 characters/)).toBeInTheDocument()
})
it.each(['shops','vehicles'])('distinguishes failed %s loading from an empty list',async(section)=>{
  m.get.mockRejectedValue(new Error('offline'))
  mount('?tab='+section)
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load your '+section)
  expect(screen.getByRole('button',{name:'Retry loading '+section})).toBeInTheDocument()
  expect(screen.queryByText(/No vehicles on file|No shops are linked/)).not.toBeInTheDocument()
})
it.each(['Keep editing','Close dialog and keep editing'])('keeps edits when dismissed with %s and never calls native confirm',async dismissLabel=>{
  const native=vi.spyOn(window,'confirm').mockImplementation(()=>{throw new Error('Native confirmation must not be used')})
  mount();const name=await screen.findByLabelText('First name')
  fireEvent.change(name,{target:{value:'Changed'}})
  fireEvent.click(screen.getByRole('button',{name:'Security',exact:true}))
  const dialog=await screen.findByRole('alertdialog',{name:'Discard unsaved changes?'})
  expect(dialog).toHaveAttribute('aria-modal','true')
  expect(dialog).toHaveAccessibleDescription('Leaving this section will discard your unsaved changes.')
  await waitFor(()=>expect(within(dialog).getByRole('button',{name:'Keep editing'})).toHaveFocus())
  expect(name).toHaveValue('Changed')
  fireEvent.click(within(dialog).getByRole('button',{name:dismissLabel}))
  await waitFor(()=>expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  expect(name).toHaveValue('Changed')
  expect(screen.queryByRole('button',{name:'Change Password',exact:true})).not.toBeInTheDocument()
  expect(native).not.toHaveBeenCalled()
  native.mockRestore()
})
it('navigates to the requested section only after confirming discard',async()=>{
  mount();fireEvent.change(await screen.findByLabelText('First name'),{target:{value:'Changed'}})
  await click(screen.getByRole('button',{name:'Security',exact:true}))
  const dialog=await screen.findByRole('alertdialog')
  await click(within(dialog).getByRole('button',{name:'Discard changes',exact:true}))
  expect(await screen.findByRole('button',{name:'Change Password',exact:true})).toBeInTheDocument()
  expect(screen.queryByLabelText('First name')).not.toBeInTheDocument()
})

it('uses the same discard modal for payment management and sign-out',async()=>{
  mount();fireEvent.change(await screen.findByLabelText('First name'),{target:{value:'Changed'}})
  fireEvent.click(screen.getByRole('button',{name:'Manage payment methods'}))
  await click(within(await screen.findByRole('alertdialog')).getByRole('button',{name:'Keep editing'}))
  await waitFor(()=>expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  expect(m.logout).not.toHaveBeenCalled()
  await click(screen.getByRole('button',{name:'Sign out',exact:true}))
  const dialog=await screen.findByRole('alertdialog',{name:'Discard changes and sign out?'})
  expect(m.logout).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button',{name:'Discard and sign out'}))
  expect(m.logout).toHaveBeenCalledTimes(1)
})

it('reports profile load failure with a recovery action',async()=>{
  m.get.mockRejectedValue(new Error('offline'))
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load your contact details.')
  expect(screen.getByRole('button',{name:'Retry loading profile'})).toBeInTheDocument()
})

it('preserves edited fields while refreshing untouched contact details',async()=>{
  const {client}=mount()
  const name=await screen.findByLabelText('First name')
  fireEvent.change(name,{target:{value:'Changed'}})
  act(()=>client.setQueryData(['customer','c1'],{...customer,last_name:'Refreshed'}))
  expect(name).toHaveValue('Changed')
  await waitFor(()=>expect(screen.getByLabelText('Last name')).toHaveValue('Refreshed'))
  expect(name).toHaveValue('Changed')
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
})

it('does not claim a changed checkout preference when browser storage fails',async()=>{
  mount();await screen.findByText('Preferred checkout method')
  const storage=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('storage blocked')})
  fireEvent.click(screen.getByRole('button',{name:'card',exact:true}))
  expect(screen.getByRole('button',{name:'zelle',exact:true})).toHaveAttribute('aria-pressed','true')
  storage.mockRestore()
})

it('dismisses a pending sign-out when the authenticated session changes',async()=>{
  const view=mount()
  fireEvent.change(await screen.findByLabelText('First name'),{target:{value:'Changed'}})
  await click(screen.getByRole('button',{name:'Sign out',exact:true}))
  expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
  m.epoch=2
  view.rerender(<MemoryRouter><QueryClientProvider client={view.client}><ProfileSettingsPage /></QueryClientProvider></MemoryRouter>)
  await waitFor(()=>expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  expect(m.logout).not.toHaveBeenCalled()
})

it.each([
  ['2025550123','(202) 555-0123'],
  ['12025550123','(202) 555-0123'],
  ['(202) 555-0123','(202) 555-0123'],
  [null,''],
])('formats the saved phone %s without making the profile dirty',async(phone,expected)=>{
  m.get.mockImplementation(async(path:string)=>({data:path.startsWith('/customers/')?{...customer,phone}:path.endsWith('/config')?config:[]}))
  mount()
  await waitFor(()=>expect(screen.getByLabelText('Phone')).toHaveValue(expected))
  expect(screen.getByRole('button',{name:'Save changes'})).toBeDisabled()
  expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument()
  expect(m.put).not.toHaveBeenCalled()
})
it('restores the formatted saved phone on Cancel',async()=>{
  m.get.mockImplementation(async(path:string)=>({data:path.startsWith('/customers/')?{...customer,phone:'2025550123'}:path.endsWith('/config')?config:[]}))
  mount()
  const phone=await screen.findByLabelText('Phone')
  fireEvent.change(phone,{target:{value:'2025550199'}})
  expect(phone).toHaveValue('(202) 555-0199')
  fireEvent.click(screen.getByRole('button',{name:'Cancel',exact:true}))
  expect(phone).toHaveValue('(202) 555-0123')
  expect(screen.getByRole('button',{name:'Save changes'})).toBeDisabled()
  expect(m.put).not.toHaveBeenCalled()
})

it('signs out directly from a pristine form with explicit login feedback state',async()=>{
  mount(); await screen.findByLabelText('First name')
  const button=screen.getByRole('button',{name:'Sign out',exact:true})
  expect(button).toHaveClass('text-[var(--semantic-danger-500)]')
  await click(button)
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  expect(m.logout).toHaveBeenCalledTimes(1)
  expect(screen.getByLabelText('Destination')).toHaveTextContent('"path":"/login","state":{"signedOut":true}')
})
it('keeps the draft and session when sign-out discard is cancelled',async()=>{
  mount();const name=await screen.findByLabelText('First name')
  fireEvent.change(name,{target:{value:'Unsaved'}})
  await click(screen.getByRole('button',{name:'Sign out',exact:true}))
  await click(within(await screen.findByRole('alertdialog')).getByRole('button',{name:'Keep editing'}))
  expect(name).toHaveValue('Unsaved')
  expect(m.logout).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Destination')).toHaveTextContent('"path":"/portal/settings"')
})
