import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { useAuthStore } from '/private/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/stores/authStore'
import { DB048_PROVIDER_READINESS } from '/private/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/test-fixtures/db048/settlements'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))

vi.mock('/private/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
    put: apiMocks.put,
    defaults: { headers: { common: {} } },
  },
}))

vi.mock('react-hot-toast', () => ({default: Object.assign(vi.fn(), {success: vi.fn(), error: vi.fn()})}))

import UnifiedSettingsPage from '/private/tmp/dbn-pr760-fleet-current-main-20261104/frontend/src/features/dashboard/UnifiedSettingsPage'

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
  return <><output data-testid="settings-url">{useLocation().search}</output><button onClick={() => navigate(-1)}>Browser Back</button><button onClick={() => navigate(1)}>Browser Forward</button></>
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

const settings={sales_tax_rate:7.25,shop_supplies_rate:5,service_fee_rate:2,labor_rate:145,internal_labor_rate:65,fleet_company_name:'Independent fleet',default_fleet_authority_customer_id:null};
let client: QueryClient;
function mounted(url:string){
 client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
 return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}><UnifiedSettingsPage/><HistoryProbe/></MemoryRouter></QueryClientProvider>);
}
function reads(path:string){
 if(path==='/admin/tax-fee-settings')return Promise.resolve({data:settings});
 if(path==='/fleet/companies')return Promise.resolve({data:[]});
 if(path==='/fleet/settings')return Promise.resolve({data:{fleet_managers:[]}});
 if(path==='/fleet/board')return Promise.resolve({data:{trucks:[]}});
 if(path==='/stripe/connect/status')return Promise.resolve({data:stripeConnection});
 if(path==='/quickbooks/status')return Promise.resolve({data:quickBooksConnection});
 return Promise.resolve({data:garageProfile});
}
beforeEach(()=>{
 apiMocks.get.mockReset();apiMocks.put.mockReset();apiMocks.post.mockReset();apiMocks.get.mockImplementation(reads);
 useAuthStore.setState({user:{id:'qa-owner',email:'qa@example.com',first_name:'QA',last_name:'Owner',phone:null,role:'garage_owner',is_active:true,tenant_id:'qa-tenant',customer_id:null},token:'local',refreshToken:'local',isAuthenticated:true});
});
it('pushes sections, preserves ordinary params, handles Back/Forward and fresh mount',async()=>{
 const u=userEvent.setup();const view=mounted('/dashboard/settings?section=security&context=qa');
 const side=()=>within(document.querySelector<HTMLElement>('.db-settings-sidebar')!);
 await u.click(side().getByRole('button',{name:'Fleet'}));
 expect(screen.getByTestId('settings-url')).toHaveTextContent('section=fleet&context=qa');
 await u.click(side().getByRole('button',{name:'Profile',exact:true}));
 expect(screen.getByTestId('settings-url')).toHaveTextContent('?context=qa');
 await u.click(screen.getByRole('button',{name:'Browser Back'}));
 expect(side().getByRole('button',{name:'Fleet'})).toHaveAttribute('data-active','true');
 await u.click(screen.getByRole('button',{name:'Browser Back'}));
 expect(side().getByRole('button',{name:'Security'})).toHaveAttribute('data-active','true');
 await u.click(screen.getByRole('button',{name:'Browser Forward'}));
 expect(side().getByRole('button',{name:'Fleet'})).toHaveAttribute('data-active','true');
 const url=screen.getByTestId('settings-url').textContent;view.unmount();mounted('/dashboard/settings'+url);
 expect(side().getByRole('button',{name:'Fleet'})).toHaveAttribute('data-active','true');
});
it.each(['section=payments','section=fees','section=integrations','section=unknown','stripe=return','stripe=refresh','stripe=error','quickbooks=connected','quickbooks=error'])('filters restricted %s before reads',async(search)=>{
 useAuthStore.setState({user:{...useAuthStore.getState().user!,role:'garage_admin',permissions:{}}});
 mounted('/dashboard/settings?'+search);
 expect(await screen.findByRole('button',{name:'Edit Profile'})).toBeVisible();await act(async()=>{});
 for(const path of ['/stripe/connect/status','/quickbooks/status','/admin/zelle-settings','/admin/tax-fee-settings'])expect(apiMocks.get).not.toHaveBeenCalledWith(path);
 expect(apiMocks.put).not.toHaveBeenCalled();expect(apiMocks.post).not.toHaveBeenCalled();
});
it.each(['section=fees','stripe=return','stripe=refresh','stripe=error','quickbooks=connected','quickbooks=not-connected','quickbooks=error'])('authorized alias %s selects Payments',async(search)=>{
 mounted('/dashboard/settings?'+search);
 expect(await screen.findByRole('button',{name:'Settings section: Payments & Accounting'})).toBeInTheDocument();
 if(search!=='section=fees') await waitFor(()=>expect(screen.getByTestId('settings-url')).toHaveTextContent('?section=payments'));
 expect(apiMocks.put).not.toHaveBeenCalled();expect(apiMocks.post).not.toHaveBeenCalled();
});
it('hides cached configuration on refetch 403',async()=>{
 mounted('/dashboard/settings?section=fleet');expect(await screen.findByText('Independent fleet')).toBeVisible();
 apiMocks.get.mockImplementation((p:string)=>p==='/admin/tax-fee-settings'?Promise.reject({isAxiosError:true,response:{status:403}}):reads(p));
 await act(async()=>{await client.invalidateQueries({queryKey:['tax-fee-settings']});});
 expect(await screen.findByText(/Fleet configuration requires Taxes & Fees access/)).toBeVisible();
 expect(screen.queryByText('Independent fleet')).not.toBeInTheDocument();
 const cfg=within(document.querySelector<HTMLElement>('.db-settings-fleet-config')!);
 expect(cfg.queryByRole('button',{name:'Unlock'})).not.toBeInTheDocument();expect(cfg.queryByRole('button',{name:'Retry'})).not.toBeInTheDocument();
});
it('late read cannot expose values after permission revocation',async()=>{
 let resolve!:(r:unknown)=>void;
 apiMocks.get.mockImplementation((p:string)=>p==='/admin/tax-fee-settings'?new Promise(r=>{resolve=r}):reads(p));
 mounted('/dashboard/settings?section=fleet');expect(await screen.findByText('Loading fleet configuration…')).toBeVisible();
 act(()=>useAuthStore.setState({user:{...useAuthStore.getState().user!,role:'garage_admin',permissions:{}}}));
 await act(async()=>resolve({data:settings}));
 expect(screen.getByText(/Fleet configuration requires Taxes & Fees access/)).toBeVisible();expect(screen.queryByText('Independent fleet')).not.toBeInTheDocument();expect(apiMocks.put).not.toHaveBeenCalled();
});

