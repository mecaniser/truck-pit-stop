import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import NotificationPreferencesSection from '../NotificationPreferencesSection'
const m=vi.hoisted(()=>({get:vi.fn(),put:vi.fn()}))
vi.mock('@/lib/api',()=>({default:{get:m.get,put:m.put}}))
vi.mock('@/stores/authStore',()=>({getAuthenticatedSessionIdentity:()=> 'session',useAuthStore:Object.assign(()=>({}),{getState:()=>({})})}))
const initial={context_key:'a'.repeat(64),revision:0,invoice_email:true,invoice_sms:true,repair_email:true,repair_sms:true,has_email:true,has_phone:true,sms_opted_out:false}
function mount(){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><NotificationPreferencesSection onDirtyChange={vi.fn()}/></QueryClientProvider>)}
beforeEach(()=>{vi.resetAllMocks();m.get.mockResolvedValue({data:initial})})
it('loads, cancels a draft and saves a revision-bound policy',async()=>{
 m.put.mockResolvedValue({data:{...initial,invoice_email:false,revision:1}});mount()
 const toggle=await screen.findByRole('switch',{name:'Invoice updates: Email'})
 expect(screen.getByRole('button',{name:'Save preferences'})).toBeDisabled()
 fireEvent.click(toggle);expect(toggle).toHaveAttribute('aria-checked','false')
 fireEvent.click(screen.getByRole('button',{name:'Cancel',exact:true}));expect(toggle).toHaveAttribute('aria-checked','true')
 fireEvent.click(toggle);fireEvent.click(screen.getByRole('button',{name:'Save preferences'}))
 await screen.findByText('Preferences saved')
 expect(m.put).toHaveBeenCalledExactlyOnceWith('/auth/me/notification-preferences',{expected_context:initial.context_key,base_revision:0,invoice_email:false,invoice_sms:true,repair_email:true,repair_sms:true})
 expect(screen.getByRole('button',{name:'Save preferences'})).toBeDisabled()
})
it('never retries uncertain saves and confirms dirty reload in a proper modal',async()=>{
 m.put.mockRejectedValue(new Error('network'));mount()
 fireEvent.click(await screen.findByRole('switch',{name:'Repair updates: Email'}));fireEvent.click(screen.getByRole('button',{name:'Save preferences'}))
 await screen.findByText(/could not confirm whether/);expect(m.put).toHaveBeenCalledTimes(1)
 expect(screen.getByRole('button',{name:'Save preferences'})).toBeDisabled()
 fireEvent.click(screen.getByRole('button',{name:'Reload preferences',exact:true}))
 const dialog=screen.getByRole('alertdialog',{name:'Reload notification preferences?'})
 fireEvent.click(within(dialog).getByRole('button',{name:'Keep editing'}))
 expect(screen.getByRole('switch',{name:'Repair updates: Email'})).toHaveAttribute('aria-checked','false')
 await waitFor(()=>expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
 fireEvent.click(screen.getByRole('button',{name:'Reload preferences',exact:true}))
 fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button',{name:'Reload preferences'}))
 await waitFor(()=>expect(screen.getByRole('switch',{name:'Repair updates: Email'})).toHaveAttribute('aria-checked','true'))
 expect(m.put).toHaveBeenCalledTimes(1)
})
it('preserves SMS opt-out and exposes only supported switches',async()=>{
 m.get.mockResolvedValue({data:{...initial,sms_opted_out:true}});mount()
 expect(await screen.findByRole('switch',{name:'Invoice updates: Text messages'})).toBeDisabled()
 expect(screen.getByRole('switch',{name:'Repair updates: Text messages'})).toBeDisabled()
 expect(screen.getByRole('switch',{name:'Repair updates: Email'})).toBeEnabled()
 expect(screen.getAllByRole('switch')).toHaveLength(4)
})
it('shows load failure without switches and supports explicit retry',async()=>{
 m.get.mockRejectedValueOnce(new Error('offline'));mount()
 await screen.findByText('Unable to load notification preferences.');expect(screen.queryByRole('switch')).not.toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:'Retry loading preferences'}));await screen.findByRole('switch',{name:'Invoice updates: Email'})
})
