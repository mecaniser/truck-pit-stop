import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, CreditCard } from 'lucide-react'
import toast from 'react-hot-toast'

import { Spinner } from '@/components/ui'

import {
  createIdempotencyKey,
  fetchCardProviderReadiness,
  isSettlementUnavailable,
  paymentApiError,
  updateCardProvider,
} from './api'
import type { CardProvider } from './types'

const STATUS_LABELS = {
  ready: 'Ready',
  not_ready: 'Not ready',
  not_configured: 'Not configured',
  onboarding_incomplete: 'Onboarding incomplete',
  accounting_mapping_incomplete: 'Accounting mapping required',
  accounting_unavailable: 'QuickBooks Accounting unavailable',
  unavailable_external_approval: 'External Intuit approval pending',
  feature_disabled: 'Partial payments disabled',
} as const

export default function CardProviderSettingsCard({ requestVerification, children }: {
  requestVerification: (onGranted: (grantToken: string) => void) => void
  children?: ReactNode
}) {
  const queryClient = useQueryClient()
  const readiness = useQuery({
    queryKey: ['invoice-card-provider-readiness'],
    queryFn: fetchCardProviderReadiness,
    retry: false,
  })
  const [pendingProvider, setPendingProvider] = useState<CardProvider | null>(null)
  const [choosingProvider, setChoosingProvider] = useState(false)

  const updateMutation = useMutation({
    mutationFn: ({ provider, grantToken }: { provider: CardProvider; grantToken: string }) => updateCardProvider(provider, readiness.data!, createIdempotencyKey(), grantToken),
    onSuccess: data => {
      queryClient.setQueryData(['invoice-card-provider-readiness'], data)
      setPendingProvider(null)
      setChoosingProvider(false)
      toast.success('Card provider saved for new payment attempts.')
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to change the card provider.').message),
  })

  if (readiness.isLoading) return <><div className="flex justify-center rounded-xl border border-zinc-800 py-8"><Spinner size="lg" /></div>{children}</>
  if (readiness.error && isSettlementUnavailable(readiness.error)) return <>{children}</>
  if (readiness.error || !readiness.data) {
    return <><div className="rounded-xl border border-red-800/40 bg-red-950/20 p-4 text-sm text-red-200">Invoice provider readiness could not be loaded. Existing provider connections were not changed.</div>{children}</>
  }

  const data = readiness.data
  const selected = pendingProvider ?? data.selected_provider
  const canConfigure = data.allowed_actions?.configure_provider === true
  const providers = [
    { id: 'stripe_connect' as const, name: 'Stripe Connect', status: data.stripe_connect.status, ready: data.stripe_connect.status === 'ready' },
    { id: 'quickbooks_payments' as const, name: 'QuickBooks Payments', status: data.quickbooks_payments.status, ready: data.quickbooks_payments.status === 'ready' && data.quickbooks_payments.approved && data.quickbooks_payments.tenant_ready },
  ].filter(provider => provider.ready || provider.id === data.selected_provider)
    .sort((a, b) => Number(b.id === data.selected_provider) - Number(a.id === data.selected_provider))

  return (
    <section className={children ? 'space-y-5' : 'rounded-2xl border border-zinc-800 bg-zinc-950/40 p-4 sm:p-5'} aria-labelledby="invoice-card-provider-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="invoice-card-provider-heading" className="flex items-center gap-2 font-extrabold text-zinc-100"><CreditCard className="h-4 w-4" />{children ? 'Payment methods' : 'Your invoice card processor'}</h3>
          <p className="mt-1 max-w-2xl text-sm text-zinc-400">{children ? 'Manage how customers pay and where payments are recorded.' : 'Your shop chooses the processor. Customers pay by card without choosing a provider. Changes apply to new payment attempts only.'}</p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${data.feature_enabled ? 'db-card-provider-enabled' : 'border-amber-700/50 bg-amber-950/30 text-amber-300'}`}>
          {data.feature_enabled ? 'Partial payments enabled' : 'Feature gate off'}
        </span>
      </div>

      {children && providers.some(provider => provider.ready && provider.id !== data.selected_provider) && canConfigure && <button type="button" onClick={() => { setChoosingProvider(!choosingProvider); setPendingProvider(null) }} className="min-h-11 text-sm font-semibold text-[var(--accent-400)]">{choosingProvider ? 'Cancel processor change' : 'Change card processor'}</button>}
      {(!children || choosingProvider) && <div className={`mt-4 grid gap-3 ${providers.length > 1 ? 'sm:grid-cols-2' : ''}`} role="radiogroup" aria-label="Invoice card provider">
        {providers.map(provider => {
          const active = provider.id === data.selected_provider && provider.ready && data.feature_enabled && data.accounting_ready
          const pending = provider.id === pendingProvider && provider.id !== data.selected_provider
          return <button
            key={provider.id}
            type="button"
            role="radio"
            aria-checked={selected === provider.id}
            disabled={!canConfigure || !provider.ready}
            onClick={() => setPendingProvider(provider.id)}
            data-state={active ? 'active' : pending ? 'pending' : !provider.ready ? 'unavailable' : 'available'}
            className="db-card-provider-option min-h-[72px] rounded-xl border p-3 text-left disabled:cursor-not-allowed"
          >
            <span className="flex items-center justify-between gap-2"><span className="font-bold">{provider.name}</span>{active ? <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> : !provider.ready ? <AlertTriangle className="h-4 w-4" aria-hidden="true" /> : null}</span>
            <span className="mt-1 block text-xs">{active ? 'Active for invoice payments' : pending ? 'Selected — save to activate' : provider.id === data.selected_provider ? `Selected · ${!data.feature_enabled ? 'Partial payments disabled' : !data.accounting_ready ? 'Accounting setup required' : STATUS_LABELS[provider.status]}` : 'Ready to use'}</span>
          </button>
        })}
      </div>}
      {children && providers.some(provider => provider.id === data.selected_provider && !provider.ready) && <p role="status" className="text-sm text-amber-300">The selected card processor needs attention. Check its connection below.</p>}
      {providers.length === 0 && <p className="mt-3 text-sm text-zinc-400">No card processor is ready. Complete a connection below to accept card payments.</p>}

      {!data.accounting_ready && (
        <p className="mt-3 rounded-xl border border-amber-800/40 bg-amber-950/20 p-3 text-sm text-amber-200">
          {data.accounting_message || 'Complete QuickBooks Accounting and clearing-account mappings before enabling partial payments.'}
        </p>
      )}

      {pendingProvider && pendingProvider !== data.selected_provider && (
        <div className="mt-4 flex flex-wrap items-center justify-end gap-3 border-t border-zinc-800 pt-4">
          <button type="button" onClick={() => setPendingProvider(null)} className="min-h-[44px] px-3 text-sm font-bold text-zinc-400 hover:text-white">Cancel</button>
          <button type="button" disabled={updateMutation.isPending || (pendingProvider === 'stripe_connect' ? data.stripe_connect.status !== 'ready' : data.quickbooks_payments.status !== 'ready')} onClick={() => requestVerification((grantToken) => updateMutation.mutate({ provider: pendingProvider, grantToken }))} className="min-h-[44px] rounded-xl bg-[#b9472f] px-4 text-sm font-extrabold text-white hover:brightness-110 disabled:opacity-50">
            {updateMutation.isPending ? 'Saving…' : `Use ${pendingProvider === 'stripe_connect' ? 'Stripe' : 'QuickBooks'} for new attempts`}
          </button>
        </div>
      )}
      {children}
    </section>
  )
}

export { CardProviderSettingsCard }
