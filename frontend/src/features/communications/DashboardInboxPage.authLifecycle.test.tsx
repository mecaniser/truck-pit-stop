import { act,cleanup,render } from '@testing-library/react'
import { QueryClient,QueryClientProvider } from '@tanstack/react-query'
import { afterEach,beforeEach,expect,it,vi } from 'vitest'
import DashboardInboxPage from './DashboardInboxPage'
import { getAuthenticatedSessionIdentity,useAuthStore } from '../../stores/authStore'
import { garageOwnerSession } from '../../test-fixtures/db035/staffSession'
const callbacks=vi.hoisted(()=>[] as ((count:number)=>void)[])
vi.mock('./ConnectedInbox',()=>({default:({onUnreadCountChange}:{onUnreadCountChange:(count:number)=>void})=>{callbacks.push(onUnreadCountChange);return null}}))
let client:QueryClient
beforeEach(()=>{callbacks.length=0;client=new QueryClient();useAuthStore.setState({user:{...garageOwnerSession},isAuthenticated:true,logoutInProgress:false,authSessionEpoch:1,authProvider:'legacy'})})
afterEach(()=>{cleanup();client.clear();useAuthStore.getState().clearSession()})
it('writes unread counts only under the authenticated session key',()=>{
 render(<QueryClientProvider client={client}><DashboardInboxPage/></QueryClientProvider>)
 const identity=getAuthenticatedSessionIdentity(useAuthStore.getState())
 act(()=>callbacks[0](7))
 expect(client.getQueryData(['messages-unread-summary',identity])).toEqual({unread_count_staff:7})
 expect(client.getQueryData(['messages-unread-summary'])).toBeUndefined()
})
it('ignores stale unread callbacks after logout or a tenant change',()=>{
 render(<QueryClientProvider client={client}><DashboardInboxPage/></QueryClientProvider>)
 const old=callbacks[0]
 act(()=>useAuthStore.setState({logoutInProgress:true}))
 act(()=>old(7));expect(client.getQueryCache().getAll()).toHaveLength(0)
 act(()=>useAuthStore.getState().establishCookieSession({...garageOwnerSession,id:'owner-b',tenant_id:'tenant-b'}))
 act(()=>old(7));expect(client.getQueryCache().getAll()).toHaveLength(0)
})
