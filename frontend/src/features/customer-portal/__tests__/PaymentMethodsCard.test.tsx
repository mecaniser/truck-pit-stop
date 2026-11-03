import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PaymentMethodsCard from '../PaymentMethodsCard'

const m = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), loader: vi.fn(), confirm: vi.fn(), user: { id: 'u1', tenant_id: 't1', customer_id: 'c1' } }))
vi.mock('@/lib/api', () => ({ default: { get: m.get, post: m.post, delete: m.delete } }))
vi.mock('@/lib/stripe', () => ({ getStripeForAccount: m.loader }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (s: unknown) => unknown) => selector({ user: m.user }) }))
vi.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div data-testid="elements">{children}</div>,
  CardElement: () => <div>Secure card input</div>,
  useStripe: () => ({ confirmCardSetup: m.confirm }),
  useElements: () => ({ getElement: () => ({ synthetic: true }) }),
}))
const card = { id: 'pm_1', brand: 'visa', last4: '4242', exp_month: 10, exp_year: 2030, is_default: false }
const error = (detail: string) => ({ response: { data: { detail } } })
const mount = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { ...render(<QueryClientProvider client={client}><PaymentMethodsCard /></QueryClientProvider>), client }
}
const openForm = async () => {
  const button = await screen.findByRole('button', { name: 'Add Payment Method' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
}
beforeEach(() => {
  vi.resetAllMocks()
  m.user = { id: 'u1', tenant_id: 't1', customer_id: 'c1' }
  m.get.mockImplementation(async (path: string) => ({ data: path.endsWith('/config') ? { stripe_account_id: 'acct_shop' } : [] }))
  m.loader.mockResolvedValue({})
  m.post.mockResolvedValue({ data: { client_secret: 'synthetic_secret', stripe_account_id: 'acct_shop' } })
  m.confirm.mockResolvedValue({ setupIntent: { status: 'succeeded' } })
})
describe('saved cards', () => {
  it('shows empty only after successful empty response and loads the selected account', async () => {
    mount()
    expect(await screen.findByText('No payment methods on file.')).toBeInTheDocument()
    await waitFor(() => expect(m.loader).toHaveBeenCalledWith('acct_shop'))
  })
  it('shows list failure instead of empty, and retries loading', async () => {
    let fail = true
    m.get.mockImplementation(async (path: string) => {
      if (path.endsWith('/config')) return { data: { stripe_account_id: 'acct_shop' } }
      if (fail) throw error('Saved cards could not be loaded. Add a card to reconnect your payment profile.')
      return { data: [card] }
    })
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('Saved cards could not be loaded')
    expect(screen.queryByText('No payment methods on file.')).not.toBeInTheDocument()
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading cards' }))
    expect(await screen.findByText(/4242/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('recovers on explicit Add Card despite failed list, then refreshes it', async () => {
    let added = false
    m.get.mockImplementation(async (path: string) => {
      if (path.endsWith('/config')) return { data: { stripe_account_id: 'acct_shop' } }
      if (!added) throw error('Add a card to reconnect your payment profile.')
      return { data: [card] }
    })
    m.confirm.mockImplementation(async () => { added = true; return { setupIntent: { status: 'succeeded' } } })
    mount()
    await openForm()
    expect(m.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Add Card' }))
    expect(await screen.findByText(/4242/)).toBeInTheDocument()
    expect(m.post).toHaveBeenCalledWith('/payments/setup-intent')
    expect(m.confirm).toHaveBeenCalledWith('synthetic_secret', { payment_method: { card: { synthetic: true } } })
    expect(screen.queryByTestId('elements')).not.toBeInTheDocument()
  })
  it('preserves form and displays setup failures without confirming', async () => {
    m.post.mockRejectedValue(error('Payment service temporarily unavailable.'))
    mount(); await openForm()
    fireEvent.click(screen.getByRole('button', { name: 'Add Card' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Payment service temporarily unavailable.')
    expect(m.confirm).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Add Card' })).toBeEnabled()
  })
  it('refuses confirmation against a changed account', async () => {
    m.post.mockResolvedValue({ data: { client_secret: 'synthetic_secret', stripe_account_id: 'acct_other' } })
    mount(); await openForm()
    fireEvent.click(screen.getByRole('button', { name: 'Add Card' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Refresh and try again')
    expect(m.confirm).not.toHaveBeenCalled()
  })
  it('displays Stripe confirmation errors and keeps the form', async () => {
    m.confirm.mockResolvedValue({ error: { message: 'Your card was declined.' } })
    mount(); await openForm()
    fireEvent.click(screen.getByRole('button', { name: 'Add Card' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your card was declined.')
    expect(screen.getByRole('button', { name: 'Add Card' })).toBeEnabled()
  })
  it('retries secure form initialization failures', async () => {
    m.loader.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({})
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load the secure card form')
    expect(screen.getByRole('button', { name: 'Add Payment Method' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry card form' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Add Payment Method' })).toBeEnabled())
  })
  it('shows shop readiness errors and prevents opening a form', async () => {
    m.get.mockRejectedValue(error('This shop has not finished setting up Stripe payments.'))
    mount()
    expect((await screen.findAllByRole('alert'))[0]).toHaveTextContent('This shop has not finished')
    expect(screen.queryByText('No payment methods on file.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add Payment Method' })).toBeDisabled()
    expect(m.loader).not.toHaveBeenCalled()
  })
  it('clears form and scopes cached lists on selected shop/customer change', async () => {
    const view = mount(); await openForm()
    m.user = { id: 'u1', tenant_id: 't2', customer_id: 'c2' }
    await act(async () => view.rerender(<QueryClientProvider client={view.client}><PaymentMethodsCard /></QueryClientProvider>))
    expect(screen.queryByTestId('elements')).not.toBeInTheDocument()
    await waitFor(() => expect(view.client.getQueryCache().getAll().filter(q => q.queryKey[0] === 'payment-methods')).toHaveLength(2))
  })
  it('surfaces mutation failures', async () => {
    m.get.mockImplementation(async (path: string) => ({ data: path.endsWith('/config') ? { stripe_account_id: 'acct_shop' } : [card] }))
    m.post.mockRejectedValue(error('Unable to set this default card.'))
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Set default' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to set this default card.')
  })
})
