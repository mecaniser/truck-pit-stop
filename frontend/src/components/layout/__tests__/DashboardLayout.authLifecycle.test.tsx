import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import DashboardLayout from '../DashboardLayout'
import { useAuthStore } from '../../../stores/authStore'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'

const shellState = vi.hoisted(() => ({
  presentationVariant: 'new' as 'new' | 'legacy',
  unreadCount: 0,
  appearance: {
    accent: 'cyan',
    font_family: 'geist',
    font_size: 'small',
    density: 'default',
    notification_position: 'bottom_right',
    mode: 'light',
  },
}))

vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    presentationVariant: shellState.presentationVariant,
    accentColors: { 400: '#22d3ee', 500: '#06b6d4', 600: '#0891b2' },
    appearance: shellState.appearance,
  }),
}))
vi.mock('../../../hooks/useTenantBranding', () => ({
  default: () => ({ data: { name: 'Truck Pit Stop Wisconsin', logo_url: null, state: 'WI' } }),
}))
const inboxMock = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('../../../features/communications/api', () => ({ inboxApi: inboxMock }))
vi.mock('../../../features/customers/CustomersPage', () => ({ default: () => <h1>Customers surface</h1> }))
vi.mock('../../../features/repair-orders/RepairOrdersPage', () => ({ default: () => <h1>Repair Orders surface</h1> }))
vi.mock('../../../features/garage/MyGaragePage', () => ({ default: () => <h1>My Shop surface</h1> }))
vi.mock('../../../features/dashboard/DashboardHome', () => ({ default: () => <h1>Dashboard surface</h1> }))
vi.mock('../../../features/dashboard/UnifiedSettingsPage', () => ({ default: () => <h1>Settings surface</h1> }))
vi.mock('../../../features/platform-admin/PlatformDashboard', () => ({ default: () => <h1>Platform surface</h1> }))
vi.mock('../../../features/platform-admin/GaragesPage', () => ({ default: () => null }))
vi.mock('../../../features/platform-admin/GarageAnalyticsPage', () => ({ default: () => null }))
vi.mock('../../../features/platform-admin/PlatformAnalyticsPage', () => ({ default: () => null }))
vi.mock('../../../features/platform-admin/PendingEnrollmentsPage', () => ({ default: () => null }))
vi.mock('../../../features/platform-admin/PaymentControlCenter', () => ({ default: () => null }))
vi.mock('../../../features/communications/DashboardInboxPage', () => ({ default: () => <h1>Messages surface</h1> }))
vi.mock('../../../features/dashboard/MechanicsBoardPage', () => ({ default: () => null }))
vi.mock('../../../features/dashboard/MechanicBoardDetailPage', () => ({ default: () => null }))


let client: QueryClient
beforeEach(() => {
 window.localStorage.clear()
 Object.defineProperty(window,'matchMedia',{configurable:true,value:vi.fn(() => ({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()}))})
 inboxMock.list.mockReset()
 useAuthStore.setState({user:{...garageOwnerSession},isAuthenticated:true,logoutInProgress:false,authProvider:'legacy',authSessionEpoch:1})
 client=new QueryClient({defaultOptions:{queries:{retry:false}}})
})
afterEach(() => {cleanup();client.clear();useAuthStore.getState().clearSession()})
function view(){return <QueryClientProvider client={client}><MemoryRouter initialEntries={['/dashboard']}><Routes><Route path="/dashboard/*" element={<DashboardLayout/>}/></Routes></MemoryRouter></QueryClientProvider>}
it('does not display a previous tenant unread count while the new tenant loads',async()=>{
 let finish!: (rows:{unreadCount:number}[])=>void
 inboxMock.list.mockResolvedValueOnce([{unreadCount:7}]).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 render(view());await screen.findByRole('link',{name:'Open Messages, 7 unread'})
 act(()=>useAuthStore.getState().establishCookieSession({...garageOwnerSession,id:'owner-b',tenant_id:'tenant-b'}))
 expect(screen.queryByRole('link',{name:'Open Messages, 7 unread'})).not.toBeInTheDocument()
 await waitFor(()=>expect(inboxMock.list).toHaveBeenCalledTimes(2))
 await act(async()=>{finish([{unreadCount:1}])})
 expect(await screen.findByRole('link',{name:'Open Messages, 1 unread'})).toBeInTheDocument()
})
it.each(['pending','inactive','signed-out'] as const)('starts no shell unread query for %s retained actor',state=>{
 useAuthStore.setState({logoutInProgress:state==='pending',isAuthenticated:state!=='signed-out',user:{...garageOwnerSession,is_active:state!=='inactive'}})
 render(view());expect(inboxMock.list).not.toHaveBeenCalled()
})
it('cancels an old unread read and ignores its late result after tenant change',async()=>{
 let finish!: (rows:{unreadCount:number}[])=>void
 inboxMock.list.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve})).mockResolvedValueOnce([{unreadCount:1}])
 render(view());await waitFor(()=>expect(inboxMock.list).toHaveBeenCalledTimes(1))
 const signal=inboxMock.list.mock.calls[0][1] as AbortSignal
 act(()=>useAuthStore.getState().establishCookieSession({...garageOwnerSession,id:'owner-b',tenant_id:'tenant-b'}))
 expect(signal?.aborted).toBe(true)
 expect(await screen.findByRole('link',{name:'Open Messages, 1 unread'})).toBeInTheDocument()
 await act(async()=>{finish([{unreadCount:7}])})
 expect(screen.queryByRole('link',{name:'Open Messages, 7 unread'})).not.toBeInTheDocument()
})
