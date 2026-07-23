import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, BadgeDollarSign, CircleAlert, Copy, CreditCard, ExternalLink, RefreshCw, ShieldCheck, Webhook, X } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '@/lib/api'
import { Spinner } from '@/components/ui'
import { GlassNoirButton, GlassNoirCard, GlassNoirHeader } from '@/components/ui/GlassNoirCard'

type MerchantStatus = 'active' | 'not_started' | 'incomplete' | 'under_review' | 'restricted' | 'unreachable'

interface Merchant {
  tenant_id: string
  tenant_name: string
  owner_email: string | null
  account_id: string | null
  status: MerchantStatus
  charges_enabled: boolean
  payouts_enabled: boolean
  requirements: string[]
  disabled_reason?: string | null
  platform_fee_percent: string | null
  uses_default_fee: boolean
  last_webhook_at: string | null
  last_webhook_event: string | null
  last_webhook_error: string | null
}

interface Overview {
  platform_fee_default_percent: string
  configuration: {
    secret_key_configured: boolean
    publishable_key_configured: boolean
    platform_webhook_configured: boolean
    connect_webhook_configured: boolean
    mode: string
    connect_webhook_url: string
    platform_webhook_url: string
  }
  webhook_health: {
    merchants_with_recent_delivery: number
    merchants_with_delivery_error: number
    last_payment_error_at: string | null
  }
  merchant_summary: Record<MerchantStatus, number>
  merchants: Merchant[]
  alerts: Array<{ kind: string; severity: string; tenant_id: string | null; tenant_name: string | null; message: string; created_at?: string }>
}

interface LedgerEntry {
  payment_id: string
  created_at: string
  tenant_id: string
  tenant_name: string
  invoice_number: string
  amount: string
  status: string
  payment_intent_id: string | null
  connected_account_id: string | null
  stripe_dashboard_url: string | null
  platform_fee_amount: string | null
  platform_fee_percent: string | null
}

interface LedgerResponse {
  entries: LedgerEntry[]
  totals: { volume: string; platform_fees: string }
}

const statusStyles: Record<MerchantStatus, string> = {
  active: 'border-emerald-700/50 bg-emerald-950/30 text-emerald-300',
  not_started: 'border-zinc-700 bg-zinc-800 text-zinc-300',
  incomplete: 'border-amber-700/50 bg-amber-950/30 text-amber-300',
  under_review: 'border-sky-700/50 bg-sky-950/30 text-sky-300',
  restricted: 'border-red-700/50 bg-red-950/30 text-red-300',
  unreachable: 'border-red-700/50 bg-red-950/30 text-red-300',
}

function money(value: string | null) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value || 0))
}

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'No delivery recorded'
}

export default function PaymentControlCenter() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [ledger, setLedger] = useState<LedgerResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [feeDrafts, setFeeDrafts] = useState<Record<string, string>>({})
  const [savingTenantId, setSavingTenantId] = useState<string | null>(null)
  const [resetCandidate, setResetCandidate] = useState<Merchant | null>(null)
  const [resettingTenantId, setResettingTenantId] = useState<string | null>(null)

  const load = async (refresh = false) => {
    try {
      refresh ? setRefreshing(true) : setLoading(true)
      const [overviewResponse, ledgerResponse] = await Promise.all([
        api.get<Overview>('/admin/payments-control/overview'),
        api.get<LedgerResponse>('/admin/payments-control/ledger'),
      ])
      setOverview(overviewResponse.data)
      setLedger(ledgerResponse.data)
      setFeeDrafts(Object.fromEntries(overviewResponse.data.merchants.map((merchant) => [merchant.tenant_id, merchant.platform_fee_percent || ''])))
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Unable to load payment controls')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { load() }, [])

  const saveFee = async (merchant: Merchant, explicitPercent?: number | null) => {
    const raw = feeDrafts[merchant.tenant_id]?.trim() || ''
    const percent = explicitPercent === undefined ? (raw === '' ? null : Number(raw)) : explicitPercent
    if (percent !== null && (!Number.isFinite(percent) || percent < 0 || percent > 20)) {
      toast.error('Platform fee must be between 0% and 20%')
      return
    }
    try {
      setSavingTenantId(merchant.tenant_id)
      await api.patch(`/admin/payments-control/tenants/${merchant.tenant_id}/fee`, { percent })
      toast.success(percent === null ? `Restored the ${overview?.platform_fee_default_percent}% platform default` : `Fee set to ${percent}% for ${merchant.tenant_name}`)
      await load(true)
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Unable to update platform fee')
    } finally {
      setSavingTenantId(null)
    }
  }

  const resetStripeConnection = async () => {
    if (!resetCandidate) return
    try {
      setResettingTenantId(resetCandidate.tenant_id)
      await api.post(`/admin/payments-control/tenants/${resetCandidate.tenant_id}/reset-stripe-connection`)
      toast.success(`Reset Stripe connection for ${resetCandidate.tenant_name}`)
      setResetCandidate(null)
      await load(true)
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Unable to reset Stripe connection')
    } finally {
      setResettingTenantId(null)
    }
  }

  const copyWebhook = async (url: string) => {
    await navigator.clipboard.writeText(url)
    toast.success('Webhook URL copied')
  }

  const activeMerchants = useMemo(() => overview?.merchant_summary.active || 0, [overview])

  if (loading) return <div className="flex justify-center py-20"><Spinner size="xl" /></div>
  if (!overview || !ledger) return null

  return (
    <div className="space-y-6">
      <GlassNoirHeader
        title="Payments Control Center"
        subtitle="Merchant readiness, platform fees, webhooks, and payment operations"
        icon={<CreditCard className="h-6 w-6 text-gold-400" />}
        actions={<GlassNoirButton variant="secondary" size="sm" onClick={() => load(true)} disabled={refreshing}>{refreshing ? 'Refreshing...' : <span className="inline-flex items-center gap-2"><RefreshCw className="h-4 w-4" />Refresh</span>}</GlassNoirButton>}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Active merchants</p><p className="mt-2 text-3xl font-semibold text-emerald-300">{activeMerchants}</p><p className="mt-1 text-sm text-zinc-400">Can charge and receive payouts</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Needs attention</p><p className="mt-2 text-3xl font-semibold text-amber-300">{(overview.merchant_summary.incomplete || 0) + (overview.merchant_summary.restricted || 0)}</p><p className="mt-1 text-sm text-zinc-400">Incomplete or restricted Stripe accounts</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Recent Stripe volume</p><p className="mt-2 text-3xl font-semibold text-zinc-100">{money(ledger.totals.volume)}</p><p className="mt-1 text-sm text-zinc-400">Latest {ledger.entries.length} finalized payments</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Recorded platform fees</p><p className="mt-2 text-3xl font-semibold text-gold-400">{money(ledger.totals.platform_fees)}</p><p className="mt-1 text-sm text-zinc-400">New charges record fee details</p></GlassNoirCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <GlassNoirCard>
          <div className="mb-5 flex items-center gap-3"><ShieldCheck className="h-5 w-5 text-gold-400" /><div><h2 className="font-semibold text-white">Platform configuration health</h2><p className="mt-1 text-sm text-zinc-400">Credentials remain masked; only readiness is shown.</p></div></div>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ['Secret key', overview.configuration.secret_key_configured],
              ['Publishable key', overview.configuration.publishable_key_configured],
              ['Platform webhook secret', overview.configuration.platform_webhook_configured],
              ['Connect webhook secret', overview.configuration.connect_webhook_configured],
            ].map(([label, ready]) => <div key={String(label)} className="flex items-center justify-between rounded-lg border border-zinc-700/60 bg-zinc-950/40 px-3 py-2 text-sm"><span className="text-zinc-300">{label}</span><span className={ready ? 'text-emerald-300' : 'text-red-300'}>{ready ? 'Configured' : 'Missing'}</span></div>)}
          </div>
          <p className="mt-4 text-sm text-zinc-400">Stripe mode: <span className="font-medium text-zinc-200">{overview.configuration.mode}</span></p>
        </GlassNoirCard>
        <GlassNoirCard>
          <div className="mb-5 flex items-center gap-3"><Webhook className="h-5 w-5 text-sky-400" /><div><h2 className="font-semibold text-white">Webhook health</h2><p className="mt-1 text-sm text-zinc-400">Connected-account delivery activity and current endpoints.</p></div></div>
          <p className="text-sm text-zinc-300">{overview.webhook_health.merchants_with_recent_delivery} merchants have a recorded delivery. {overview.webhook_health.merchants_with_delivery_error} have a latest delivery error.</p>
          <div className="mt-4 space-y-2">
            {[overview.configuration.connect_webhook_url, overview.configuration.platform_webhook_url].map((url) => <div key={url} className="flex items-center gap-2 rounded-lg border border-zinc-700/60 bg-zinc-950/40 p-2"><code className="min-w-0 flex-1 truncate text-xs text-zinc-300">{url}</code><button onClick={() => copyWebhook(url)} className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white" aria-label="Copy webhook URL"><Copy className="h-4 w-4" /></button></div>)}
          </div>
        </GlassNoirCard>
      </div>

      <GlassNoirCard>
        <div className="mb-5 flex items-center gap-3"><CircleAlert className="h-5 w-5 text-amber-400" /><div><h2 className="font-semibold text-white">Exception alerts</h2><p className="mt-1 text-sm text-zinc-400">Open merchant restrictions, onboarding needs, and unresolved payment errors.</p></div></div>
        {overview.alerts.length ? <div className="divide-y divide-zinc-800">{overview.alerts.slice(0, 10).map((alert, index) => <div key={`${alert.kind}-${index}`} className="flex items-start gap-3 py-3"><AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}`} /><div><p className="text-sm text-zinc-200">{alert.tenant_name ? `${alert.tenant_name}: ` : ''}{alert.message}</p>{alert.created_at && <p className="mt-1 text-xs text-zinc-500">{dateTime(alert.created_at)}</p>}</div></div>)}</div> : <p className="text-sm text-emerald-300">No open payment exceptions.</p>}
      </GlassNoirCard>

      <GlassNoirCard padding="none" className="overflow-hidden">
        <div className="p-6"><div className="flex items-center gap-3"><BadgeDollarSign className="h-5 w-5 text-gold-400" /><div><h2 className="font-semibold text-white">Merchant readiness and platform fees</h2><p className="mt-1 text-sm text-zinc-400">Default fee: {overview.platform_fee_default_percent}%. Overrides affect new PaymentIntents only.</p></div></div></div>
        <div className="overflow-x-auto"><table className="w-full min-w-[1080px] text-left text-sm"><thead className="border-y border-zinc-800 bg-zinc-950/45 text-xs uppercase tracking-[0.12em] text-zinc-500"><tr><th className="px-6 py-3">Merchant</th><th className="px-4 py-3">Readiness</th><th className="px-4 py-3">Requirements</th><th className="px-4 py-3">Fee override</th><th className="px-4 py-3">Webhook delivery</th><th className="px-4 py-3">Recovery</th></tr></thead><tbody className="divide-y divide-zinc-800">{overview.merchants.map((merchant) => <tr key={merchant.tenant_id} className="align-top"><td className="px-6 py-4"><p className="font-medium text-zinc-100">{merchant.tenant_name}</p><p className="mt-1 text-xs text-zinc-500">{merchant.owner_email || 'No owner email'}</p></td><td className="px-4 py-4"><span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${statusStyles[merchant.status]}`}>{merchant.status.replace('_', ' ')}</span><p className="mt-2 text-xs text-zinc-500">Charges: {merchant.charges_enabled ? 'on' : 'off'} · Payouts: {merchant.payouts_enabled ? 'on' : 'off'}</p></td><td className="max-w-xs px-4 py-4 text-xs text-zinc-400">{merchant.requirements.length ? merchant.requirements.join(', ') : merchant.disabled_reason || 'None reported'}</td><td className="px-4 py-4"><div className="flex items-center gap-2"><input aria-label={`Platform fee for ${merchant.tenant_name}`} value={feeDrafts[merchant.tenant_id] ?? ''} onChange={(event) => setFeeDrafts((current) => ({ ...current, [merchant.tenant_id]: event.target.value }))} placeholder={`${overview.platform_fee_default_percent}% default`} inputMode="decimal" className="w-28 rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-2 text-sm text-white outline-none focus:border-gold-500" /><GlassNoirButton size="sm" onClick={() => saveFee(merchant)} disabled={savingTenantId === merchant.tenant_id}>{savingTenantId === merchant.tenant_id ? 'Saving' : 'Save'}</GlassNoirButton></div><button onClick={() => saveFee(merchant, null)} className="mt-2 text-xs text-zinc-500 hover:text-gold-300">Use platform default</button></td><td className="px-4 py-4"><p className="text-xs text-zinc-300">{dateTime(merchant.last_webhook_at)}</p><p className="mt-1 text-xs text-zinc-500">{merchant.last_webhook_event || 'No event'}{merchant.last_webhook_error ? ` · ${merchant.last_webhook_error}` : ''}</p></td><td className="px-4 py-4">{merchant.account_id ? <GlassNoirButton variant="danger" size="sm" onClick={() => setResetCandidate(merchant)} disabled={resettingTenantId === merchant.tenant_id}>{resettingTenantId === merchant.tenant_id ? 'Resetting' : 'Reset Stripe'}</GlassNoirButton> : <span className="text-xs text-zinc-500">No connection</span>}</td></tr>)}</tbody></table></div>
      </GlassNoirCard>

      <GlassNoirCard padding="none" className="overflow-hidden">
        <div className="p-6"><h2 className="font-semibold text-white">Recent Stripe payment ledger</h2><p className="mt-1 text-sm text-zinc-400">Fee data appears for PaymentIntents created after this control center is deployed.</p></div>
        <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-sm"><thead className="border-y border-zinc-800 bg-zinc-950/45 text-xs uppercase tracking-[0.12em] text-zinc-500"><tr><th className="px-6 py-3">Date</th><th className="px-4 py-3">Merchant</th><th className="px-4 py-3">Invoice</th><th className="px-4 py-3">Amount</th><th className="px-4 py-3">Platform fee</th><th className="px-4 py-3">Stripe</th></tr></thead><tbody className="divide-y divide-zinc-800">{ledger.entries.map((entry) => <tr key={entry.payment_id}><td className="px-6 py-3 text-xs text-zinc-400">{dateTime(entry.created_at)}</td><td className="px-4 py-3 text-zinc-200">{entry.tenant_name}</td><td className="px-4 py-3 text-zinc-300">{entry.invoice_number}</td><td className="px-4 py-3 font-medium text-zinc-100">{money(entry.amount)}</td><td className="px-4 py-3">{entry.platform_fee_amount ? <span className="text-gold-400">{money(entry.platform_fee_amount)} ({entry.platform_fee_percent}%)</span> : <span className="text-zinc-400">Not recorded</span>}</td><td className="px-4 py-3">{entry.stripe_dashboard_url ? <a href={entry.stripe_dashboard_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-sky-300 hover:text-sky-200">Open account payments <ExternalLink className="h-3 w-3" /></a> : <span className="text-xs text-zinc-500">Unavailable</span>}</td></tr>)}</tbody></table></div>
      </GlassNoirCard>

      {resetCandidate && <div className="fixed inset-0 z-[100] grid place-items-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={(event) => event.target === event.currentTarget && !resettingTenantId && setResetCandidate(null)}><div role="alertdialog" aria-modal="true" aria-labelledby="reset-stripe-title" aria-describedby="reset-stripe-description" className="w-full max-w-md rounded-lg border border-red-800/50 bg-zinc-950 p-6 shadow-2xl shadow-black/60"><div className="flex items-start justify-between gap-4"><div><h3 id="reset-stripe-title" className="text-lg font-semibold text-zinc-100">Reset Stripe connection?</h3><p id="reset-stripe-description" className="mt-3 text-sm leading-6 text-zinc-400">This clears the stale Stripe account link for <span className="font-medium text-zinc-200">{resetCandidate.tenant_name}</span>. It does not delete the Stripe account or prior payment history.</p></div><button type="button" onClick={() => setResetCandidate(null)} disabled={Boolean(resettingTenantId)} aria-label="Close confirmation" className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-50"><X className="h-5 w-5" /></button></div><div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><GlassNoirButton variant="secondary" onClick={() => setResetCandidate(null)} disabled={Boolean(resettingTenantId)}>Cancel</GlassNoirButton><GlassNoirButton variant="danger" onClick={resetStripeConnection} disabled={Boolean(resettingTenantId)}>{resettingTenantId ? 'Resetting...' : 'Reset connection'}</GlassNoirButton></div></div></div>}
    </div>
  )
}
