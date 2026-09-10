import { useState } from 'react'
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

export default function CardProviderSettingsCard({ requestVerification }: {
  requestVerification: (onGranted: (grantToken: string) => void) => void
}) {
  const queryClient = useQueryClient()
  const readiness = useQuery({
    queryKey: ['invoice-card-provider-readiness'],
    queryFn: fetchCardProviderReadiness,
    retry: false,
  })
  const [pendingProvider, setPendingProvider] = useState<CardProvider | null>(null)

  const updateMutation = useMutation({
    mutationFn: ({ provider, grantToken }: { provider: CardProvider; grantToken: string }) => updateCardProvider(provider, readiness.data!, createIdempotencyKey(), grantToken),
    onSuccess: data => {
      queryClient.setQueryData(['invoice-card-provider-readiness'], data)
      setPendingProvider(null)
      toast.success('Card provider saved for new payment attempts.')
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to change the card provider.').message),
  })

  if (readiness.isLoading) return <div className="flex justify-center rounded-xl border border-zinc-800 py-8"><Spinner size="lg" /></div>
  if (readiness.error && isSettlementUnavailable(readiness.error)) return null
  if (readiness.error || !readiness.data) {
    return <div className="rounded-xl border border-red-800/40 bg-red-950/20 p-4 text-sm text-red-200">Invoice provider readiness could not be loaded. Existing provider connections were not changed.</div>
  }

  const data = readiness.data
  const selected = pendingProvider ?? data.selected_provider
  const canConfigure = data.allowed_actions?.configure_provider === true

  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-950/40 p-4 sm:p-5" aria-labelledby="invoice-card-provider-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-zinc-500">Invoice card routing</p>
          <h3 id="invoice-card-provider-heading" className="mt-1 flex items-center gap-2 font-extrabold text-zinc-100"><CreditCard className="h-4 w-4" />One provider for every customer</h3>
          <p className="mt-1 max-w-2xl text-sm text-zinc-400">Customer portal, guest links, and staff checkout use the same server-selected provider. Switching affects new attempts only.</p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${data.feature_enabled ? 'border-emerald-700/50 bg-emerald-950/30 text-emerald-300' : 'border-amber-700/50 bg-amber-950/30 text-amber-300'}`}>
          {data.feature_enabled ? 'Partial payments enabled' : 'Feature gate off'}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Invoice card provider">
        <button
          type="button"
          role="radio"
          aria-checked={selected === 'stripe_connect'}
          disabled={!canConfigure}
          onClick={() => setPendingProvider('stripe_connect')}
          className={`min-h-[72px] rounded-xl border p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#d25d43] disabled:cursor-not-allowed disabled:opacity-70 ${selected === 'stripe_connect' ? 'border-[#d25d43] bg-[#d25d43]/10' : 'border-zinc-800 bg-zinc-950/30'}`}
        >
          <span className="flex items-center justify-between gap-2"><span className="font-bold text-zinc-100">Stripe Connect</span>{data.stripe_connect.status === 'ready' ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <AlertTriangle className="h-4 w-4 text-amber-400" />}</span>
          <span className="mt-1 block text-xs text-zinc-400">{STATUS_LABELS[data.stripe_connect.status]}</span>
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={selected === 'quickbooks_payments'}
          disabled={!canConfigure || !data.quickbooks_payments.approved || !data.quickbooks_payments.tenant_ready}
          onClick={() => setPendingProvider('quickbooks_payments')}
          className={`min-h-[72px] rounded-xl border p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#d25d43] disabled:cursor-not-allowed disabled:opacity-70 ${selected === 'quickbooks_payments' ? 'border-[#d25d43] bg-[#d25d43]/10' : 'border-zinc-800 bg-zinc-950/30'}`}
        >
          <span className="flex items-center justify-between gap-2"><span className="font-bold text-zinc-100">QuickBooks Payments</span>{data.quickbooks_payments.status === 'ready' ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <AlertTriangle className="h-4 w-4 text-amber-400" />}</span>
          <span className="mt-1 block text-xs text-zinc-400">{STATUS_LABELS[data.quickbooks_payments.status]}</span>
        </button>
      </div>

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
    </section>
  )
}

export { CardProviderSettingsCard }
