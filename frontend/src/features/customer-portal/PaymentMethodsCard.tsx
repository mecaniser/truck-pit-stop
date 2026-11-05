import AccountConfirmationDialog from './AccountConfirmationDialog'
import { ControlButton } from '@/components/ui/Controls'
import { useState, useEffect } from 'react'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import { Spinner } from '@/components/ui'
import type { Stripe } from '@stripe/stripe-js'
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { getStripeForAccount } from '../../lib/stripe'
import QuickBooksPaymentPanel from './QuickBooksPaymentPanel'

export interface SavedCardConfig {
  provider: 'stripe_connect' | 'quickbooks_payments' | null
  context_key: string
  available: boolean
  save_pending: boolean
  message?: string
  stripe_account_id?: string | null
  token_url?: string | null
}

interface PaymentMethod {
  id: string
  brand: string
  last4: string
  exp_month: number
  exp_year: number
  is_default: boolean
}

const UNCONFIRMED = 'We could not confirm whether your card was saved. Please contact the shop before trying again.'
const UNAVAILABLE = 'Saved cards are unavailable for this shop. Please contact the shop for help.'
const CARD_BRANDS: Record<string, string> = {
  visa: 'Visa', mastercard: 'Mastercard', amex: 'Amex', discover: 'Discover',
  diners: 'Diners', jcb: 'JCB', unionpay: 'UnionPay',
}

function cardError(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' && !/stripe|quickbooks|intuit|square/i.test(detail) ? detail : fallback
}

function StripeCardForm({ config, onSuccess, onCancel, onRefresh }: {
  config: SavedCardConfig; onSuccess: () => void; onCancel: () => void; onRefresh: () => void
}) {
  const stripe = useStripe()
  const elements = useElements()
  const [requestKey] = useState(() => crypto.randomUUID())
  const [error, setError] = useState<string | null>(null)
  const [processing, setProcessing] = useState(false)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!stripe || !elements || processing) return
    setProcessing(true)
    setError(null)
    try {
      const { data } = await api.post('/payments/cards/prepare', {
        expected_context: config.context_key,
        idempotency_key: requestKey,
      })
      if (data.stripe_account_id !== config.stripe_account_id) throw new Error('Card context changed')
      const card = elements.getElement(CardElement)
      if (!card) throw new Error('Secure card input unavailable')
      const result = await stripe.confirmCardSetup(data.client_secret, { payment_method: { card } })
      if (result.error) {
        setError(result.error.message && !/stripe|quickbooks|intuit|square/i.test(result.error.message)
          ? result.error.message : 'Unable to save your card. Please try again.')
      } else if (result.setupIntent?.status === 'succeeded') onSuccess()
      else setError(UNCONFIRMED)
    } catch (cause: unknown) {
      setError(cardError(cause, 'Unable to save your card. Refresh and try again.'))
      onRefresh()
    } finally { setProcessing(false) }
  }
  return <form onSubmit={submit} className="space-y-4">
    <div className="rounded-xl border border-[#30384b] bg-[#0d1118] p-4">
      <CardElement options={{ style: { base: { fontSize: '16px', color: '#ffffff', '::placeholder': { color: '#9ca3af' } }, invalid: { color: '#ef4444' } } }} />
    </div>
    {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
    <div className="flex gap-3">
      <ControlButton type="submit" disabled={!stripe || processing} className="flex-1 rounded-xl bg-violet-600 px-4 font-medium text-white disabled:bg-gray-600">{processing ? 'Adding...' : 'Add Card'}</ControlButton>
      <ControlButton type="button" disabled={processing} onClick={onCancel} className="rounded-lg bg-white/10 px-4 text-white">Cancel</ControlButton>
    </div>
  </form>
}

function TokenCardForm({ config, onSuccess, onCancel, onRefresh }: {
  config: SavedCardConfig; onSuccess: () => void; onCancel: () => void; onRefresh: () => void
}) {
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID())
  const [processing, setProcessing] = useState(false)
  return <div className="space-y-3">
    <QuickBooksPaymentPanel tokenUrl={config.token_url || ''} submitLabel="Add Card" processingLabel="Adding..."
      successMessage="Card saved" failureMessage="Unable to save your card. Please try again."
      onProcessingChange={setProcessing} onSuccess={onSuccess}
      onToken={async token => {
        try {
          const { data } = await api.post('/payments/cards/save', {
            expected_context: config.context_key, idempotency_key: requestKey, token,
          })
          if (data.status !== 'saved') throw new Error('Card save unconfirmed')
        } catch (cause: unknown) {
          const status = (cause as { response?: { status?: number } })?.response?.status
          // Corrected card details start a new operation after a definitive rejection.
          // Uncertain outcomes must retain their key.
          if (status === 400) setRequestKey(crypto.randomUUID())
          onRefresh()
          throw cause
        }
      }} />
    <ControlButton type="button" disabled={processing} onClick={onCancel} className="rounded-lg bg-white/10 px-4 text-white">Cancel</ControlButton>
  </div>
}

function PaymentMethodsList({ scope, shopName }: { scope: string; shopName?: string | null }) {
  const queryClient = useQueryClient()
  const [cardToRemove, setCardToRemove] = useState<{ method: PaymentMethod; context: string | undefined } | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [stripePromise, setStripePromise] = useState<Promise<Stripe | null> | null>(null)
  const [stripeReady, setStripeReady] = useState(false)
  const [stripeLoadError, setStripeLoadError] = useState(false)
  const [stripeRetry, setStripeRetry] = useState(0)
  const configKey = ['payment-methods-config', scope]
  const configQuery = useQuery<SavedCardConfig>({
    queryKey: configKey, queryFn: async () => (await api.get('/payments/cards/config')).data, retry: false,
  })
  const config = configQuery.data
  const contextKey = config?.context_key
  const provider = config?.provider
  const accountId = config?.stripe_account_id
  const available = config?.available === true
  const methodsKey = ['payment-methods', scope, contextKey]
  useEffect(() => { setShowAddForm(false); setCardToRemove(null) }, [contextKey, available, config?.save_pending])
  useEffect(() => {
    let active = true
    setStripePromise(null)
    setStripeReady(false)
    setStripeLoadError(false)
    if (available && provider === 'stripe_connect' && accountId) {
      const promise = getStripeForAccount(accountId).then(stripe => {
        if (!stripe) throw new Error('Secure form unavailable')
        if (active) setStripeReady(true)
        return stripe
      }).catch(() => { if (active) setStripeLoadError(true); return null })
      setStripePromise(promise)
    }
    return () => { active = false }
  }, [available, provider, accountId, contextKey, stripeRetry])

  const methods = useQuery<PaymentMethod[]>({
    queryKey: methodsKey, enabled: available && Boolean(contextKey), retry: false,
    queryFn: async () => (await api.get('/payments/cards', { params: { expected_context: contextKey } })).data,
  })
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['payment-methods', scope] })
    void queryClient.invalidateQueries({ queryKey: configKey })
  }
  const remove = useMutation({
    mutationFn: async (id: string) => api.delete(`/payments/cards/${encodeURIComponent(id)}`, { params: { expected_context: contextKey } }),
    onSuccess: refresh,
    onError: () => { void queryClient.invalidateQueries({ queryKey: configKey }) },
  })
  const setDefault = useMutation({
    mutationFn: async (id: string) => api.post(`/payments/cards/${encodeURIComponent(id)}/default`, { expected_context: contextKey }),
    onSuccess: refresh,
    onError: () => { void queryClient.invalidateQueries({ queryKey: configKey }) },
  })
  const saved = () => { setShowAddForm(false); refresh() }
  const formReady = available && !config?.save_pending && (
    provider === 'stripe_connect' ? stripeReady : provider === 'quickbooks_payments' && Boolean(config?.token_url)
  )

  const heading = <div className="min-w-0">
    <h2 className="text-lg font-semibold text-white">Payment methods</h2>
    <p className="mt-1 break-words text-sm text-gray-400">{shopName ? 'Saved cards for ' + shopName + '.' : 'Saved cards for your current shop.'}</p>
  </div>

  if (configQuery.isLoading || methods.isLoading) return <div className="space-y-6">{heading}<div className="flex justify-center py-8"><Spinner size="lg" /></div></div>
  if (configQuery.isError) return <div className="space-y-6">{heading}<div role="alert" className="space-y-2 text-sm text-red-400">
    <p>{cardError(configQuery.error, 'Unable to load saved cards. Please try again.')}</p>
    <ControlButton type="button" onClick={() => { void configQuery.refetch() }} disabled={configQuery.isFetching} className="underline">Retry loading cards</ControlButton>
  </div></div>
  if (!available) return <div className="space-y-6">{heading}<p role="status" className="text-sm text-gray-400">{config?.message && !/stripe|quickbooks|intuit|square/i.test(config.message) ? config.message : UNAVAILABLE}</p></div>

  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4">{heading}{!showAddForm && <ControlButton type="button" onClick={() => setShowAddForm(true)} disabled={!formReady} className="shrink-0 rounded-lg bg-violet-600 px-4 font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"><span aria-hidden="true">+</span> Add Card</ControlButton>}</div>
    {methods.isError ? <div role="alert" className="space-y-2 text-sm text-red-400">
      <p>{cardError(methods.error, 'Unable to load saved cards. Please try again.')}</p>
      <ControlButton type="button" onClick={() => { void methods.refetch() }} disabled={methods.isFetching} className="underline">{methods.isFetching ? 'Retrying...' : 'Retry loading cards'}</ControlButton>
    </div> : methods.isSuccess && methods.data.length > 0 ? <div className="space-y-3">
      {methods.data.map(method => <div key={method.id} className="flex flex-col items-start justify-between gap-3 rounded-xl sm:flex-row sm:items-center border border-[#232939] bg-[#0d1118] p-3">
        <div>
          <p className="font-medium text-white">{CARD_BRANDS[method.brand] || 'Card'} •••• {method.last4}{method.is_default && <span className="ml-2 rounded-full border border-violet-400/30 bg-violet-500/10 px-2 py-0.5 text-xs text-violet-200">Default</span>}</p>
          <p className="text-sm text-gray-400">Expires {method.exp_month.toString().padStart(2, '0')}/{method.exp_year}</p>
        </div>
        <div className="flex items-center gap-2">
          {!method.is_default && <ControlButton type="button" onClick={() => setDefault.mutate(method.id)} disabled={setDefault.isPending || remove.isPending} className="text-xs text-gray-400 hover:text-white">Make default</ControlButton>}
          <ControlButton type="button" aria-label={'Remove ' + (CARD_BRANDS[method.brand] || 'card') + ' ending in ' + method.last4} disabled={remove.isPending || setDefault.isPending} onClick={() => setCardToRemove({ method, context: contextKey })} className="text-gray-400 hover:text-red-400">
            Remove
          </ControlButton>
        </div>
      </div>)}
    </div> : methods.isSuccess && !config?.save_pending ? <p className="text-sm text-gray-400">No payment methods on file.</p> : null}

    {config?.save_pending && <p role="status" className="text-sm text-amber-300">{UNCONFIRMED}</p>}
    {stripeLoadError && <div role="alert" className="space-y-2 text-sm text-red-400"><p>Unable to load the secure card form. Please try again.</p><ControlButton type="button" onClick={() => setStripeRetry(value => value + 1)} className="underline">Retry card form</ControlButton></div>}
    {(remove.isError || setDefault.isError) && <p role="alert" className="text-sm text-red-400">{cardError(remove.error || setDefault.error, 'Unable to update your saved card. Please try again.')}</p>}
    {showAddForm && formReady && config ? <div key={contextKey}>
      {provider === 'stripe_connect' && stripePromise ? <Elements stripe={stripePromise}><StripeCardForm config={config} onSuccess={saved} onCancel={() => setShowAddForm(false)} onRefresh={refresh} /></Elements>
        : provider === 'quickbooks_payments' ? <TokenCardForm config={config} onSuccess={saved} onCancel={() => setShowAddForm(false)} onRefresh={refresh} /> : null}
    </div> : null}
    <AccountConfirmationDialog
      open={cardToRemove !== null && cardToRemove.context === contextKey && available}
      title="Remove saved card?"
      description={cardToRemove ? 'Remove ' + (CARD_BRANDS[cardToRemove.method.brand] || 'card') + ' ending in ' + cardToRemove.method.last4 + ' from this shop’s saved cards?' : ''}
      confirmLabel="Remove card"
      cancelLabel="Keep card"
      onCancel={() => setCardToRemove(null)}
      onConfirm={() => {
        if (cardToRemove && cardToRemove.context === contextKey && available) {
          remove.mutate(cardToRemove.method.id)
          setCardToRemove(null)
        }
      }}
    />
  </div>
}

export default function PaymentMethodsCard() {
  const scope = useAuthStore(getAuthenticatedSessionIdentity)
  const shopName = useAuthStore(state => state.user?.tenant_name)
  if (!scope) return null
  return <PaymentMethodsList key={scope} scope={scope} shopName={shopName} />
}
