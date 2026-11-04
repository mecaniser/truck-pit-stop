import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PaymentMethodsCard from '../PaymentMethodsCard'

const m = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), loader: vi.fn(), confirm: vi.fn(), fetch: vi.fn(), epoch: 1, user: { id: 'u1', tenant_id: 't1', customer_id: 'c1', role:'customer',is_active:true } }))
vi.mock('@/lib/api', () => ({ default: { get: m.get, post: m.post, delete: m.delete } }))
vi.mock('@/lib/stripe', () => ({ getStripeForAccount: m.loader }))
vi.mock('@/stores/authStore', async importOriginal => ({ ...await importOriginal<typeof import('@/stores/authStore')>(), useAuthStore: (selector: (s: unknown) => unknown) => selector({ user:m.user, authSessionEpoch:m.epoch, authProvider:'legacy',isAuthenticated:true,logoutInProgress:false }) }))
vi.mock('react-hot-toast', () => ({ default: { success:vi.fn() } }))
vi.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div data-testid="elements">{children}</div>,
  CardElement: () => <div>Secure card input</div>,
  useStripe: () => ({ confirmCardSetup: m.confirm }),
  useElements: () => ({ getElement: () => ({ synthetic: true }) }),
}))
const card = { id: 'pm_1', brand: 'visa', last4: '4242', exp_month: 10, exp_year: 2030, is_default: false }
const stripeConfig = { provider:'stripe_connect', context_key:'context-one', available:true, save_pending:false, stripe_account_id:'acct_shop' }
const qbpConfig = { provider:'quickbooks_payments', context_key:'context-two', available:true, save_pending:false, token_url:'https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens' }
const error = (detail: string) => ({ response: { data: { detail } } })
const mount = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { ...render(<QueryClientProvider client={client}><PaymentMethodsCard /></QueryClientProvider>), client }
}
const openForm = async () => {
  const button = await screen.findByRole('button', { name: 'Add Card' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
}
const fillCard = () => {
  fireEvent.change(screen.getByLabelText('Name on card'), {target:{value:'Test Driver'}})
  fireEvent.change(screen.getByLabelText('Card number'), {target:{value:'4111111111111111'}})
  fireEvent.change(screen.getByLabelText('Expiry'), {target:{value:'122034'}})
  fireEvent.change(screen.getByLabelText('Security code'), {target:{value:'123'}})
  fireEvent.change(screen.getByLabelText('Billing ZIP code'), {target:{value:'28201'}})
}
beforeEach(() => {
  vi.resetAllMocks()
  m.user = { id:'u1', tenant_id:'t1', customer_id:'c1',role:'customer',is_active:true };m.epoch=1
  m.get.mockImplementation(async (path: string) => ({ data: path.endsWith('/config') ? stripeConfig : [] }))
  m.loader.mockResolvedValue({})
  m.post.mockResolvedValue({ data: { client_secret:'synthetic_secret', stripe_account_id:'acct_shop' } })
  m.confirm.mockResolvedValue({ setupIntent: { status:'succeeded' } })
  m.fetch.mockResolvedValue({ok:true,json:async()=>({value:'opaque-token'})})
  vi.stubGlobal('fetch',m.fetch)
})
describe('provider-neutral saved cards', () => {
  it('does not fetch or render a wallet for an inactive private session', () => {
    m.user={...m.user,is_active:false}
    mount()
    expect(screen.queryByText('Saved cards')).not.toBeInTheDocument()
    expect(m.get).not.toHaveBeenCalled()
    expect(m.loader).not.toHaveBeenCalled()
  })
  it('shows empty only after successful response and loads the selected account', async () => {
    mount()
    expect(await screen.findByText('No payment methods on file.')).toBeInTheDocument()
    await waitFor(() => expect(m.loader).toHaveBeenCalledWith('acct_shop'))
    expect(screen.queryByText(/stripe|quickbooks|intuit|square/i)).not.toBeInTheDocument()
  })
  it('shows list failure rather than empty, and retries loading', async () => {
    let fail=true
    m.get.mockImplementation(async path => {
      if(path.endsWith('/config')) return {data:stripeConfig}
      if(fail) throw error('Saved cards could not be loaded.')
      return {data:[card]}
    })
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('Saved cards could not be loaded')
    expect(screen.queryByText('No payment methods on file.')).not.toBeInTheDocument()
    fail=false;fireEvent.click(screen.getByRole('button',{name:'Retry loading cards'}))
    expect(await screen.findByText(/4242/)).toBeInTheDocument()
  })
  it('prepares only on explicit submit and keeps its request key stable on retry', async () => {
    m.post.mockRejectedValueOnce(error('Temporarily unavailable')).mockResolvedValueOnce({data:{client_secret:'secret',stripe_account_id:'acct_shop'}})
    mount();await openForm()
    expect(m.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button',{name:'Add Card'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Temporarily unavailable')
    fireEvent.click(screen.getByRole('button',{name:'Add Card'}))
    await waitFor(()=>expect(m.confirm).toHaveBeenCalled())
    expect(m.post.mock.calls[0][0]).toBe('/payments/cards/prepare')
    expect(m.post.mock.calls[0][1]).toEqual(m.post.mock.calls[1][1])
    expect(m.post.mock.calls[0][1]).toMatchObject({expected_context:'context-one'})
  })
  it('refuses confirmation against a changed account', async () => {
    m.post.mockResolvedValue({data:{client_secret:'secret',stripe_account_id:'acct_other'}})
    mount();await openForm();fireEvent.click(screen.getByRole('button',{name:'Add Card'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Refresh and try again')
    expect(m.confirm).not.toHaveBeenCalled()
  })
  it('displays card validation errors and keeps the form', async () => {
    m.confirm.mockResolvedValue({error:{message:'Your card was declined.'}})
    mount();await openForm();fireEvent.click(screen.getByRole('button',{name:'Add Card'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your card was declined.')
    expect(screen.getByRole('button',{name:'Add Card'})).toBeEnabled()
  })
  it('retries secure form initialization failures', async () => {
    m.loader.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({})
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load the secure card form')
    fireEvent.click(screen.getByRole('button',{name:'Retry card form'}))
    await waitFor(()=>expect(screen.getByRole('button',{name:'Add Card'})).toBeEnabled())
  })
  it('does not fall back when the tenant has no activated card capability', async () => {
    m.get.mockResolvedValue({data:{provider:null,available:false,save_pending:false,context_key:'unavailable'}})
    mount()
    expect(await screen.findByText('Saved cards are unavailable for this shop. Please contact the shop for help.')).toBeInTheDocument()
    expect(m.loader).not.toHaveBeenCalled()
    expect(m.get.mock.calls.some(([path]) => path === '/payments/cards')).toBe(false)
    expect(screen.queryByText('No payment methods on file.')).not.toBeInTheDocument()
  })
  it('never loads Stripe for a QuickBooks tenant and sends only an opaque token to the backend', async () => {
    let added=false
    m.get.mockImplementation(async path=>({data:path.endsWith('/config')?qbpConfig:added?[card]:[]}))
    m.post.mockImplementation(async()=>{added=true;return {data:{status:'saved'}}})
    mount();await openForm();fillCard();fireEvent.click(screen.getByRole('button',{name:'Add Card'}))
    expect(await screen.findByText(/4242/)).toBeInTheDocument()
    expect(m.loader).not.toHaveBeenCalled();expect(m.confirm).not.toHaveBeenCalled()
    expect(m.post).toHaveBeenCalledWith('/payments/cards/save',expect.objectContaining({expected_context:'context-two',token:'opaque-token',idempotency_key:expect.any(String)}))
    expect(JSON.stringify(m.post.mock.calls)).not.toContain('4111111111111111')
    expect(Object.keys(m.post.mock.calls[0][1]).sort()).toEqual(['expected_context','idempotency_key','token'])
    expect(screen.queryByText(/quickbooks|intuit|stripe/i)).not.toBeInTheDocument()
  })
  it('keeps an unconfirmed save on hold without resubmitting or calling Stripe', async () => {
    let pending=false
    m.get.mockImplementation(async path=>({data:path.endsWith('/config')?{...qbpConfig,save_pending:pending}:[]}))
    m.post.mockImplementation(async()=>{pending=true;throw error('Card save is unconfirmed.')})
    mount();await openForm();fillCard();fireEvent.click(screen.getByRole('button',{name:'Add Card'}))
    expect(await screen.findByRole('status')).toHaveTextContent('We could not confirm whether your card was saved')
    expect(screen.getByRole('button',{name:'Add Card'})).toBeDisabled()
    expect(screen.queryByText('No payment methods on file.')).not.toBeInTheDocument()
    expect(m.post).toHaveBeenCalledTimes(1);expect(m.loader).not.toHaveBeenCalled()
  })
  it('clears the open form and list cache identity on customer/session change', async () => {
    const view=mount();await openForm();m.user={id:'u1',tenant_id:'t2',customer_id:'c2',role:'customer',is_active:true};m.epoch=2
    await act(async()=>view.rerender(<QueryClientProvider client={view.client}><PaymentMethodsCard /></QueryClientProvider>))
    expect(screen.queryByTestId('elements')).not.toBeInTheDocument()
    await waitFor(()=>expect(view.client.getQueryCache().getAll().filter(q=>q.queryKey[0]==='payment-methods').length).toBeGreaterThan(1))
  })
  it('clears the form on provider-context changes and does not show the prior context cards', async () => {
    let config=stripeConfig as typeof stripeConfig|typeof qbpConfig
    m.get.mockImplementation(async path=>({data:path.endsWith('/config')?config:config.provider==='stripe_connect'?[card]:[]}))
    const view=mount();await openForm();config=qbpConfig
    await act(async()=>{await view.client.invalidateQueries({queryKey:['payment-methods-config']})})
    await waitFor(()=>expect(screen.queryByTestId('elements')).not.toBeInTheDocument())
    await waitFor(()=>expect(screen.queryByText(/4242/)).not.toBeInTheDocument())
  })
  it('attaches the expected context to default and remove requests', async () => {
    m.get.mockImplementation(async path=>({data:path.endsWith('/config')?qbpConfig:[card]}))
    m.post.mockResolvedValue({data:{}});m.delete.mockResolvedValue({data:{}})
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(true)
    mount();fireEvent.click(await screen.findByRole('button',{name:'Set default'}))
    await waitFor(()=>expect(m.post).toHaveBeenCalledWith('/payments/cards/pm_1/default',{expected_context:'context-two'}))
    fireEvent.click(screen.getByRole('button',{name:'Remove card'}))
    await waitFor(()=>expect(m.delete).toHaveBeenCalledWith('/payments/cards/pm_1',{params:{expected_context:'context-two'}}))
    confirm.mockRestore()
  })
})
