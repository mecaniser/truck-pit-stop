import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { useAuthStore } from '/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/stores/authStore'
import { DB048_PROVIDER_READINESS } from '/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/test-fixtures/db048/settlements'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))

vi.mock('/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
    put: apiMocks.put,
    defaults: { headers: { common: {} } },
  },
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(), remove: vi.fn(),
    error: vi.fn(),
  },
}))

import { SessionQueryProvider } from '/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/components/SessionQueryProvider'
import UnifiedSettingsPage from '/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/features/dashboard/UnifiedSettingsPage'

const garageProfile = {
  name: 'Truck Pit Stop',
  slug: 'truck-pit-stop',
  address: '123 Service Rd',
  phone: '5551234567',
  email: 'garage@example.com',
  website: 'https://garage.example.com',
  logo_url: null,
}

const importedGarageProfile = {
  ...garageProfile,
  logo_url: 'https://cdn.example.com/imported-logo.png',
}

const stripeConnection = {
  configured: true,
  is_connected: true,
  onboarding_complete: true,
  charges_enabled: true,
  payouts_enabled: true,
  account_id: 'acct_123456789',
  connection_type: 'stripe_hosted',
  verification_status: 'active',
  requirements: [],
  mode: 'test',
  account_dashboard_url: 'https://dashboard.stripe.example.com',
  available_balance: '125.00',
  pending_balance: '0.00',
  last_payout_amount: null,
  last_payout_status: null,
  last_payout_at: null,
  recent_payments: [],
}

const quickBooksConnection = {
  configured: true,
  is_connected: false,
  realm_id: null,
  scopes: [],
  connected_at: null,
  token_health: 'not_connected',
  last_token_refresh_at: null,
  last_token_refresh_error: null,
  last_webhook_at: null,
  last_webhook_event: null,
  last_webhook_error: null,
}

function HistoryProbe() {
  const navigate = useNavigate()
  return <><output data-testid="settings-url">{useLocation().search}</output><button onClick={() => navigate(-1)}>Browser Back</button></>
}

function renderPage(initialEntry = '/dashboard/settings', withHistory = false) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <UnifiedSettingsPage />
        {withHistory && <HistoryProbe />}
      </MemoryRouter>
    </QueryClientProvider>
  )
}

async function verifyPaymentChange(user: ReturnType<typeof userEvent.setup>) {
  const dialog = await screen.findByRole('alertdialog', { name: /^Verify / })
  await user.type(within(dialog).getByLabelText('Your current password'), 'local-password')
  await user.click(within(dialog).getByRole('button', { name: 'Verify and continue' }))
}


describe('Independent security adversarial checks', () => {
 const settings = {sales_tax_rate:7, shop_supplies_rate:5, service_fee_rate:2, labor_rate:145, internal_labor_rate:65, fleet_company_name:'PRIVATE-CACHED-FLEET', default_fleet_authority_customer_id:'private-customer', default_fleet_authority_company_name:'PRIVATE-AUTHORITY'}
 const reads=(path:string) => Promise.resolve({data:path==='/admin/tax-fee-settings'?settings:path==='/fleet/settings'?{fleet_managers:[]}:path==='/fleet/board'?{trucks:[]}:path==='/fleet/companies'?[]:garageProfile})
 beforeEach(()=>{
  apiMocks.get.mockReset(); apiMocks.post.mockReset();apiMocks.put.mockReset();apiMocks.get.mockImplementation(reads)
  useAuthStore.setState({user:{id:'sec-user',email:'sec@example.com',first_name:'Sec',last_name:'User',phone:null,role:'garage_owner',is_active:true,tenant_id:'sec-tenant',customer_id:null},token:'token',refreshToken:'refresh',isAuthenticated:true})
 })
 it.each(['?section=payments','?section=fees','?stripe=return','?stripe=refresh','?stripe=error','?quickbooks=connected','?quickbooks=error','?section=workforce','?section=integrations'])('restricted URL %s cannot mount privileged reads',async suffix=>{
  useAuthStore.setState({user:{...useAuthStore.getState().user!,role:'garage_admin',permissions:{}}})
  renderPage('/dashboard/settings'+suffix)
  expect(screen.getByRole('button',{name:'Settings section: Profile'})).toBeVisible()
  await act(async()=>{await Promise.resolve()})
  for(const path of ['/stripe/connect/status','/quickbooks/status','/admin/tax-fee-settings','/admin/platform/stripe-status','/admin/platform/quickbooks-status','/admin/workforce-settings']) expect(apiMocks.get).not.toHaveBeenCalledWith(path)
  expect(apiMocks.post).not.toHaveBeenCalled();expect(apiMocks.put).not.toHaveBeenCalled()
 })
 it('late authorized tax response after local revocation stays hidden',async()=>{
  let resolveRead!:(v:any)=>void
  apiMocks.get.mockImplementation((path:string)=>path==='/admin/tax-fee-settings'?new Promise(resolve=>{resolveRead=resolve}):reads(path))
  renderPage('/dashboard/settings?section=fleet')
  expect(await screen.findByText('Loading fleet configuration…')).toBeVisible()
  act(()=>useAuthStore.setState({user:{...useAuthStore.getState().user!,role:'garage_admin',permissions:{}}}))
  await act(async()=>{resolveRead({data:settings})})
  expect(screen.getByText(/Fleet configuration requires Taxes & Fees access/)).toBeVisible()
  expect(screen.queryByText('PRIVATE-CACHED-FLEET')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Unlock'})).not.toBeInTheDocument()
 })
 it('cached successful read followed by server403 hides cached configuration',async()=>{
  const q=new QueryClient({defaultOptions:{queries:{retry:false}}})
  q.setQueryData(['tax-fee-settings'],settings)
  apiMocks.get.mockImplementation((path:string)=>path==='/admin/tax-fee-settings'?Promise.reject({isAxiosError:true,response:{status:403}}):reads(path))
  render(<QueryClientProvider client={q}><MemoryRouter initialEntries={['/dashboard/settings?section=fleet']}><UnifiedSettingsPage/></MemoryRouter></QueryClientProvider>)
  expect(await screen.findByText(/Fleet configuration requires Taxes & Fees access/)).toBeVisible()
  expect(screen.queryByText('PRIVATE-CACHED-FLEET')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Unlock'})).not.toBeInTheDocument()
 })
 it('already unlocked editor disappears immediately after permission removal',async()=>{
  apiMocks.post.mockResolvedValue({data:{valid:true}})
  renderPage('/dashboard/settings?section=fleet')
  const user=userEvent.setup()
  await user.type(await screen.findByLabelText('Password'),'disposable-password')
  await user.click(screen.getByRole('button',{name:'Unlock'}))
  await user.type(await screen.findByDisplayValue('PRIVATE-CACHED-FLEET'),'-edited')
  expect(await screen.findByRole('button',{name:'Save Changes'})).toBeVisible()
  act(()=>useAuthStore.setState({user:{...useAuthStore.getState().user!,role:'garage_admin',permissions:{}}}))
  expect(screen.queryByRole('button',{name:'Save Changes'})).not.toBeInTheDocument()
  expect(screen.queryByDisplayValue('PRIVATE-CACHED-FLEET-edited')).not.toBeInTheDocument()
  expect(apiMocks.put).not.toHaveBeenCalled()
 })
 it('actual session provider drops cached Fleet configuration across tenant replacement',async()=>{
  render(<SessionQueryProvider><MemoryRouter initialEntries={['/dashboard/settings?section=fleet']}><UnifiedSettingsPage/></MemoryRouter></SessionQueryProvider>)
  expect(await screen.findByText('PRIVATE-CACHED-FLEET')).toBeVisible()
  apiMocks.get.mockImplementation((path:string)=>path==='/admin/tax-fee-settings'?new Promise(()=>{}):reads(path))
  act(()=>useAuthStore.setState({user:{...useAuthStore.getState().user!,id:'replacement-owner',tenant_id:'replacement-tenant'}}))
  expect(screen.getByText('Loading fleet configuration…')).toBeVisible()
  expect(screen.queryByText('PRIVATE-CACHED-FLEET')).not.toBeInTheDocument()
 })
 it('actual session provider isolates a late old-tenant response from replacement tenant',async()=>{
  let resolveOld!:(v:any)=>void; let requests=0
  apiMocks.get.mockImplementation((path:string)=>path==='/admin/tax-fee-settings'?new Promise(resolve=>{if(++requests===1)resolveOld=resolve}):reads(path))
  render(<SessionQueryProvider><MemoryRouter initialEntries={['/dashboard/settings?section=fleet']}><UnifiedSettingsPage/></MemoryRouter></SessionQueryProvider>)
  expect(await screen.findByText('Loading fleet configuration…')).toBeVisible()
  act(()=>useAuthStore.setState({user:{...useAuthStore.getState().user!,id:'replacement-owner',tenant_id:'replacement-tenant'}}))
  await act(async()=>{resolveOld({data:settings})})
  expect(requests).toBe(2)
  expect(screen.getByText('Loading fleet configuration…')).toBeVisible()
  expect(screen.queryByText('PRIVATE-CACHED-FLEET')).not.toBeInTheDocument()
 })

})
