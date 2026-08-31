import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  BadgeDollarSign,
  BookOpenCheck,
  CircleAlert,
  Copy,
  CreditCard,
  ExternalLink,
  RefreshCw,
  ShieldCheck,
  Webhook,
  X,
} from 'lucide-react'
import { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import api from '@/lib/api'
import { createPaymentStepUpGrant, paymentStepUpError, paymentStepUpHeaders } from '@/lib/paymentStepUp'
import { Spinner } from '@/components/ui'
import { GlassNoirButton, GlassNoirCard, GlassNoirHeader } from '@/components/ui/GlassNoirCard'

type Provider = 'stripe' | 'quickbooks'
type StripeMerchantStatus = 'active' | 'not_started' | 'incomplete' | 'under_review' | 'restricted' | 'unreachable'
type QuickBooksMerchantStatus = 'active' | 'not_connected' | 'accounting_only' | 'refresh_required' | 'reconnect_required' | 'attention'

interface StripeMerchant {
  tenant_id: string
  tenant_name: string
  owner_email: string | null
  account_id: string | null
  status: StripeMerchantStatus
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

interface StripeOverview {
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
  merchant_summary: Record<StripeMerchantStatus, number>
  merchants: StripeMerchant[]
  alerts: ProviderAlert[]
}

interface StripeLedgerEntry {
  payment_id: string
  created_at: string
  tenant_name: string
  invoice_number: string
  amount: string
  status: string
  stripe_dashboard_url: string | null
  platform_fee_amount: string | null
  platform_fee_percent: string | null
}

interface StripeLedger {
  entries: StripeLedgerEntry[]
  totals: { volume: string; platform_fees: string }
}

interface QuickBooksMerchant {
  tenant_id: string
  tenant_name: string
  owner_email: string | null
  connection_id: string | null
  company_id_label: string | null
  status: QuickBooksMerchantStatus
  is_connected: boolean
  accounting_enabled: boolean
  payments_scope_enabled: boolean
  payments_enabled: boolean
  token_health: string
  requirements: string[]
  connected_at: string | null
  access_token_expires_at: string | null
  refresh_token_expires_at: string | null
  last_token_refresh_at: string | null
  last_token_refresh_error: string | null
  last_webhook_at: string | null
  last_webhook_event: string | null
  last_webhook_error: string | null
  last_cdc_at: string | null
  last_cdc_error: string | null
}

interface QuickBooksOverview {
  configuration: {
    client_id_configured: boolean
    client_secret_configured: boolean
    redirect_uri_configured: boolean
    token_encryption_configured: boolean
    webhook_verifier_configured: boolean
    accounting_environment: string
    payments_environment: string
    accounting_environment_valid: boolean
    payments_environment_valid: boolean
    webhook_url: string
  }
  merchant_summary: Record<QuickBooksMerchantStatus, number>
  webhook_health: {
    merchants_with_recent_delivery: number
    merchants_with_delivery_error: number
    merchants_with_cdc_error: number
  }
  merchants: QuickBooksMerchant[]
  alerts: ProviderAlert[]
}

interface QuickBooksLedgerEntry {
  payment_id: string
  created_at: string
  tenant_name: string
  invoice_number: string
  amount: string
  status: string
  charge_id: string | null
  charge_status: string | null
  quickbooks_payment_id: string | null
  refunded_amount: string | null
  reconciled_at: string | null
  sync_error: string | null
}

interface QuickBooksLedger {
  entries: QuickBooksLedgerEntry[]
  totals: { volume: string; refunded: string; unreconciled: number }
}

interface ProviderAlert {
  kind: string
  severity: string
  tenant_id: string | null
  tenant_name: string | null
  message: string
  created_at?: string
}

interface ResetTarget {
  provider: Provider
  tenantId: string
  tenantName: string
}

const statusStyles: Record<StripeMerchantStatus | QuickBooksMerchantStatus, string> = {
  active: 'border-emerald-700/50 bg-emerald-950/30 text-emerald-300',
  not_started: 'border-zinc-700 bg-zinc-800 text-zinc-300',
  not_connected: 'border-zinc-700 bg-zinc-800 text-zinc-300',
  incomplete: 'border-amber-700/50 bg-amber-950/30 text-amber-300',
  under_review: 'border-sky-700/50 bg-sky-950/30 text-sky-300',
  accounting_only: 'border-sky-700/50 bg-sky-950/30 text-sky-300',
  refresh_required: 'border-emerald-700/50 bg-emerald-950/30 text-emerald-300',
  restricted: 'border-red-700/50 bg-red-950/30 text-red-300',
  reconnect_required: 'border-red-700/50 bg-red-950/30 text-red-300',
  attention: 'border-red-700/50 bg-red-950/30 text-red-300',
  unreachable: 'border-red-700/50 bg-red-950/30 text-red-300',
}

function money(value: string | null) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value || 0))
}

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'None recorded'
}

function apiErrorDetail(error: unknown, fallback: string) {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    return typeof detail === 'string' ? detail : fallback
  }
  return fallback
}

function StatusBadge({ status }: { status: StripeMerchantStatus | QuickBooksMerchantStatus }) {
  const label = status === 'refresh_required' ? 'active' : status.replace(/_/g, ' ')
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${statusStyles[status]}`}>
      {label}
    </span>
  )
}

function CapabilityBadge({ enabled, children }: { enabled: boolean; children: string }) {
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${
      enabled
        ? 'border-emerald-700/50 bg-emerald-950/30 text-emerald-300'
        : 'border-zinc-700 bg-zinc-900 text-zinc-500'
    }`}>
      {children}: {enabled ? 'on' : 'off'}
    </span>
  )
}

function AlertsCard({ title, description, alerts }: { title: string; description: string; alerts: ProviderAlert[] }) {
  return (
    <GlassNoirCard>
      <div className="mb-5 flex items-center gap-3">
        <CircleAlert className="h-5 w-5 text-amber-400" />
        <div><h2 className="font-semibold text-white">{title}</h2><p className="mt-1 text-sm text-zinc-400">{description}</p></div>
      </div>
      {alerts.length ? (
        <div className="divide-y divide-zinc-800">
          {alerts.slice(0, 10).map((alert, index) => (
            <div key={`${alert.kind}-${index}`} className="flex items-start gap-3 py-3">
              <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}`} />
              <div>
                <p className="text-sm text-zinc-200">{alert.tenant_name ? `${alert.tenant_name}: ` : ''}{alert.message}</p>
                {alert.created_at && <p className="mt-1 text-xs text-zinc-500">{dateTime(alert.created_at)}</p>}
              </div>
            </div>
          ))}
        </div>
      ) : <p className="text-sm text-emerald-300">No open provider exceptions.</p>}
    </GlassNoirCard>
  )
}

function ProviderTabs({ active, onChange }: { active: Provider; onChange: (provider: Provider) => void }) {
  return (
    <div className="grid gap-2 rounded-xl border border-zinc-800 bg-zinc-950/45 p-2 sm:grid-cols-2">
      {([
        ['stripe', 'Stripe', 'Connect merchants, fees and card settlements', CreditCard],
        ['quickbooks', 'QuickBooks', 'Accounting authorization and QuickBooks Payments', BookOpenCheck],
      ] as const).map(([provider, title, description, Icon]) => (
        <button
          key={provider}
          type="button"
          onClick={() => onChange(provider)}
          className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-left transition ${
            active === provider
              ? 'border-gold-500/50 bg-gold-500/10 text-white'
              : 'border-transparent text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900/70 hover:text-zinc-200'
          }`}
        >
          <Icon className={`h-5 w-5 shrink-0 ${active === provider ? 'text-gold-400' : 'text-zinc-500'}`} />
          <span><span className="block font-semibold">{title}</span><span className="mt-0.5 block text-xs text-zinc-500">{description}</span></span>
        </button>
      ))}
    </div>
  )
}

function StripeControls({
  overview,
  ledger,
  feeDrafts,
  savingTenantId,
  resettingTenantId,
  onFeeChange,
  onSaveFee,
  onCopyWebhook,
  onReset,
}: {
  overview: StripeOverview
  ledger: StripeLedger
  feeDrafts: Record<string, string>
  savingTenantId: string | null
  resettingTenantId: string | null
  onFeeChange: (tenantId: string, value: string) => void
  onSaveFee: (merchant: StripeMerchant, explicitPercent?: number | null) => void
  onCopyWebhook: (url: string) => void
  onReset: (merchant: StripeMerchant) => void
}) {
  const activeMerchants = overview.merchant_summary.active || 0
  const needsAttention = (overview.merchant_summary.incomplete || 0) + (overview.merchant_summary.restricted || 0)
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Active merchants</p><p className="mt-2 text-3xl font-semibold text-emerald-300">{activeMerchants}</p><p className="mt-1 text-sm text-zinc-400">Can charge and receive payouts</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Needs attention</p><p className="mt-2 text-3xl font-semibold text-amber-300">{needsAttention}</p><p className="mt-1 text-sm text-zinc-400">Incomplete or restricted accounts</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Recent Stripe volume</p><p className="mt-2 text-3xl font-semibold text-zinc-100">{money(ledger.totals.volume)}</p><p className="mt-1 text-sm text-zinc-400">Latest {ledger.entries.length} payments</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Platform fees</p><p className="mt-2 text-3xl font-semibold text-gold-400">{money(ledger.totals.platform_fees)}</p><p className="mt-1 text-sm text-zinc-400">Recorded on recent charges</p></GlassNoirCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <GlassNoirCard>
          <div className="mb-5 flex items-center gap-3"><ShieldCheck className="h-5 w-5 text-gold-400" /><div><h2 className="font-semibold text-white">Stripe configuration</h2><p className="mt-1 text-sm text-zinc-400">Credentials remain masked.</p></div></div>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ['Secret key', overview.configuration.secret_key_configured],
              ['Publishable key', overview.configuration.publishable_key_configured],
              ['Platform webhook', overview.configuration.platform_webhook_configured],
              ['Connect webhook', overview.configuration.connect_webhook_configured],
            ].map(([label, ready]) => (
              <div key={String(label)} className="flex items-center justify-between rounded-lg border border-zinc-700/60 bg-zinc-950/40 px-3 py-2 text-sm">
                <span className="text-zinc-300">{label}</span><span className={ready ? 'text-emerald-300' : 'text-red-300'}>{ready ? 'Configured' : 'Missing'}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-zinc-400">Stripe mode: <span className="font-medium capitalize text-zinc-200">{overview.configuration.mode}</span></p>
        </GlassNoirCard>
        <GlassNoirCard>
          <div className="mb-5 flex items-center gap-3"><Webhook className="h-5 w-5 text-sky-400" /><div><h2 className="font-semibold text-white">Stripe webhooks</h2><p className="mt-1 text-sm text-zinc-400">Connected-account delivery and endpoints.</p></div></div>
          <p className="text-sm text-zinc-300">{overview.webhook_health.merchants_with_recent_delivery} delivered · {overview.webhook_health.merchants_with_delivery_error} with errors</p>
          <div className="mt-4 space-y-2">
            {[overview.configuration.connect_webhook_url, overview.configuration.platform_webhook_url].map((url) => (
              <div key={url} className="flex items-center gap-2 rounded-lg border border-zinc-700/60 bg-zinc-950/40 p-2">
                <code className="min-w-0 flex-1 truncate text-xs text-zinc-300">{url}</code>
                <button onClick={() => onCopyWebhook(url)} className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white" aria-label="Copy Stripe webhook URL"><Copy className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
        </GlassNoirCard>
      </div>

      <AlertsCard title="Stripe exception alerts" description="Merchant restrictions and unresolved payment errors." alerts={overview.alerts} />

      <GlassNoirCard padding="none" className="overflow-hidden">
        <div className="p-6"><div className="flex items-center gap-3"><BadgeDollarSign className="h-5 w-5 text-gold-400" /><div><h2 className="font-semibold text-white">Stripe merchant readiness</h2><p className="mt-1 text-sm text-zinc-400">Default fee: {overview.platform_fee_default_percent}%. Overrides affect new PaymentIntents only.</p></div></div></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-left text-sm">
            <thead className="border-y border-zinc-800 bg-zinc-950/45 text-xs uppercase tracking-[0.12em] text-zinc-500"><tr><th className="px-6 py-3">Merchant</th><th className="px-4 py-3">Readiness</th><th className="px-4 py-3">Requirements</th><th className="px-4 py-3">Fee override</th><th className="px-4 py-3">Webhook</th><th className="px-4 py-3">Recovery</th></tr></thead>
            <tbody className="divide-y divide-zinc-800">
              {overview.merchants.map((merchant) => (
                <tr key={merchant.tenant_id} className="align-top">
                  <td className="px-6 py-4"><p className="font-medium text-zinc-100">{merchant.tenant_name}</p><p className="mt-1 text-xs text-zinc-500">{merchant.owner_email || 'No owner email'}</p></td>
                  <td className="px-4 py-4"><StatusBadge status={merchant.status} /><p className="mt-2 text-xs text-zinc-500">Charges: {merchant.charges_enabled ? 'on' : 'off'} · Payouts: {merchant.payouts_enabled ? 'on' : 'off'}</p></td>
                  <td className="max-w-xs px-4 py-4 text-xs text-zinc-400">{merchant.requirements.length ? merchant.requirements.join(', ') : merchant.disabled_reason || 'None reported'}</td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-2">
                      <input aria-label={`Platform fee for ${merchant.tenant_name}`} value={feeDrafts[merchant.tenant_id] ?? ''} onChange={(event) => onFeeChange(merchant.tenant_id, event.target.value)} placeholder={`${overview.platform_fee_default_percent}% default`} inputMode="decimal" className="w-28 rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-2 text-sm text-white outline-none focus:border-gold-500" />
                      <GlassNoirButton size="sm" onClick={() => onSaveFee(merchant)} disabled={savingTenantId === merchant.tenant_id}>{savingTenantId === merchant.tenant_id ? 'Saving' : 'Save'}</GlassNoirButton>
                    </div>
                    <button onClick={() => onSaveFee(merchant, null)} className="mt-2 text-xs text-zinc-500 hover:text-gold-300">Use platform default</button>
                  </td>
                  <td className="px-4 py-4"><p className="text-xs text-zinc-300">{dateTime(merchant.last_webhook_at)}</p><p className="mt-1 text-xs text-zinc-500">{merchant.last_webhook_event || 'No event'}{merchant.last_webhook_error ? ` · ${merchant.last_webhook_error}` : ''}</p></td>
                  <td className="px-4 py-4">{merchant.account_id ? <GlassNoirButton variant="danger" size="sm" onClick={() => onReset(merchant)} disabled={resettingTenantId === merchant.tenant_id}>{resettingTenantId === merchant.tenant_id ? 'Resetting' : 'Reset Stripe'}</GlassNoirButton> : <span className="text-xs text-zinc-500">No connection</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassNoirCard>

      <GlassNoirCard padding="none" className="overflow-hidden">
        <div className="p-6"><h2 className="font-semibold text-white">Recent Stripe ledger</h2><p className="mt-1 text-sm text-zinc-400">Finalized connected-account card payments.</p></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-y border-zinc-800 bg-zinc-950/45 text-xs uppercase tracking-[0.12em] text-zinc-500"><tr><th className="px-6 py-3">Date</th><th className="px-4 py-3">Merchant</th><th className="px-4 py-3">Invoice</th><th className="px-4 py-3">Amount</th><th className="px-4 py-3">Platform fee</th><th className="px-4 py-3">Stripe</th></tr></thead>
            <tbody className="divide-y divide-zinc-800">
              {ledger.entries.map((entry) => (
                <tr key={entry.payment_id}><td className="px-6 py-3 text-xs text-zinc-400">{dateTime(entry.created_at)}</td><td className="px-4 py-3 text-zinc-200">{entry.tenant_name}</td><td className="px-4 py-3 text-zinc-300">{entry.invoice_number}</td><td className="px-4 py-3 font-medium text-zinc-100">{money(entry.amount)}</td><td className="px-4 py-3">{entry.platform_fee_amount ? <span className="text-gold-400">{money(entry.platform_fee_amount)} ({entry.platform_fee_percent}%)</span> : <span className="text-zinc-500">Not recorded</span>}</td><td className="px-4 py-3">{entry.stripe_dashboard_url ? <a href={entry.stripe_dashboard_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-sky-300 hover:text-sky-200">Open payments <ExternalLink className="h-3 w-3" /></a> : <span className="text-xs text-zinc-500">Unavailable</span>}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassNoirCard>
    </>
  )
}

function QuickBooksControls({
  overview,
  ledger,
  resettingTenantId,
  onCopyWebhook,
  onReset,
}: {
  overview: QuickBooksOverview
  ledger: QuickBooksLedger
  resettingTenantId: string | null
  onCopyWebhook: (url: string) => void
  onReset: (merchant: QuickBooksMerchant) => void
}) {
  const active = (overview.merchant_summary.active || 0) + (overview.merchant_summary.refresh_required || 0)
  const needsAttention = (overview.merchant_summary.accounting_only || 0)
    + (overview.merchant_summary.reconnect_required || 0)
    + (overview.merchant_summary.attention || 0)
  const configurationItems: Array<[string, boolean]> = [
    ['Client ID', overview.configuration.client_id_configured],
    ['Client secret', overview.configuration.client_secret_configured],
    ['Redirect URI', overview.configuration.redirect_uri_configured],
    ['Token encryption', overview.configuration.token_encryption_configured],
    ['Webhook verifier', overview.configuration.webhook_verifier_configured],
  ]
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Payment ready</p><p className="mt-2 text-3xl font-semibold text-emerald-300">{active}</p><p className="mt-1 text-sm text-zinc-400">Accounting and Payments authorized</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Needs attention</p><p className="mt-2 text-3xl font-semibold text-amber-300">{needsAttention}</p><p className="mt-1 text-sm text-zinc-400">Scope, token or sync recovery</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">QuickBooks volume</p><p className="mt-2 text-3xl font-semibold text-zinc-100">{money(ledger.totals.volume)}</p><p className="mt-1 text-sm text-zinc-400">Latest {ledger.entries.length} payments</p></GlassNoirCard>
        <GlassNoirCard><p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Unreconciled</p><p className="mt-2 text-3xl font-semibold text-gold-400">{ledger.totals.unreconciled}</p><p className="mt-1 text-sm text-zinc-400">{money(ledger.totals.refunded)} refunded</p></GlassNoirCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <GlassNoirCard>
          <div className="mb-5 flex items-center gap-3"><ShieldCheck className="h-5 w-5 text-emerald-400" /><div><h2 className="font-semibold text-white">QuickBooks configuration</h2><p className="mt-1 text-sm text-zinc-400">Secret values remain masked.</p></div></div>
          <div className="grid gap-3 sm:grid-cols-2">
            {configurationItems.map(([label, ready]) => (
              <div key={label} className="flex items-center justify-between rounded-lg border border-zinc-700/60 bg-zinc-950/40 px-3 py-2 text-sm"><span className="text-zinc-300">{label}</span><span className={ready ? 'text-emerald-300' : 'text-red-300'}>{ready ? 'Configured' : 'Missing'}</span></div>
            ))}
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-zinc-700/60 bg-zinc-950/40 px-3 py-2"><p className="text-xs text-zinc-500">Accounting mode</p><p className="mt-1 text-sm font-medium capitalize text-zinc-200">{overview.configuration.accounting_environment}</p></div>
            <div className="rounded-lg border border-zinc-700/60 bg-zinc-950/40 px-3 py-2"><p className="text-xs text-zinc-500">Payments mode</p><p className="mt-1 text-sm font-medium capitalize text-zinc-200">{overview.configuration.payments_environment}</p></div>
          </div>
        </GlassNoirCard>
        <GlassNoirCard>
          <div className="mb-5 flex items-center gap-3"><Webhook className="h-5 w-5 text-sky-400" /><div><h2 className="font-semibold text-white">QuickBooks delivery health</h2><p className="mt-1 text-sm text-zinc-400">Webhook delivery and CDC accounting recovery.</p></div></div>
          <p className="text-sm text-zinc-300">{overview.webhook_health.merchants_with_recent_delivery} delivered · {overview.webhook_health.merchants_with_delivery_error} webhook errors · {overview.webhook_health.merchants_with_cdc_error} CDC errors</p>
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-zinc-700/60 bg-zinc-950/40 p-2">
            <code className="min-w-0 flex-1 truncate text-xs text-zinc-300">{overview.configuration.webhook_url}</code>
            <button onClick={() => onCopyWebhook(overview.configuration.webhook_url)} className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white" aria-label="Copy QuickBooks webhook URL"><Copy className="h-4 w-4" /></button>
          </div>
        </GlassNoirCard>
      </div>

      <AlertsCard title="QuickBooks exception alerts" description="Authorization, scope, webhook and sync issues." alerts={overview.alerts} />

      <GlassNoirCard padding="none" className="overflow-hidden">
        <div className="p-6"><div className="flex items-center gap-3"><BookOpenCheck className="h-5 w-5 text-emerald-400" /><div><h2 className="font-semibold text-white">QuickBooks merchant readiness</h2><p className="mt-1 text-sm text-zinc-400">Accounting and Payments are tracked separately for every shop.</p></div></div></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1180px] text-left text-sm">
            <thead className="border-y border-zinc-800 bg-zinc-950/45 text-xs uppercase tracking-[0.12em] text-zinc-500"><tr><th className="px-6 py-3">Merchant</th><th className="px-4 py-3">Connection</th><th className="px-4 py-3">Capabilities</th><th className="px-4 py-3">Requirements</th><th className="px-4 py-3">Token health</th><th className="px-4 py-3">Delivery / sync</th><th className="px-4 py-3">Recovery</th></tr></thead>
            <tbody className="divide-y divide-zinc-800">
              {overview.merchants.map((merchant) => (
                <tr key={merchant.tenant_id} className="align-top">
                  <td className="px-6 py-4"><p className="font-medium text-zinc-100">{merchant.tenant_name}</p><p className="mt-1 text-xs text-zinc-500">{merchant.owner_email || 'No owner email'}</p>{merchant.company_id_label && <p className="mt-1 font-mono text-xs text-zinc-600">Company {merchant.company_id_label}</p>}</td>
                  <td className="px-4 py-4"><StatusBadge status={merchant.status} /><p className="mt-2 text-xs text-zinc-500">Connected {dateTime(merchant.connected_at)}</p></td>
                  <td className="px-4 py-4"><div className="flex max-w-[220px] flex-wrap gap-1.5"><CapabilityBadge enabled={merchant.accounting_enabled}>Accounting</CapabilityBadge><CapabilityBadge enabled={merchant.payments_scope_enabled}>Payments scope</CapabilityBadge><CapabilityBadge enabled={merchant.payments_enabled}>Customer pay</CapabilityBadge></div></td>
                  <td className="max-w-xs px-4 py-4 text-xs text-zinc-400">{merchant.requirements.length ? merchant.requirements.join(', ') : 'No action required'}</td>
                  <td className="px-4 py-4"><p className={`text-xs ${merchant.status === 'active' || merchant.status === 'refresh_required' ? 'text-emerald-300' : 'capitalize text-zinc-300'}`}>{merchant.token_health === 'refresh_required' && !merchant.last_token_refresh_error ? 'Ready · automatic renewal' : merchant.token_health.replace(/_/g, ' ')}</p><p className="mt-1 text-xs text-zinc-500">Last token update: {dateTime(merchant.last_token_refresh_at || merchant.connected_at)}</p>{merchant.last_token_refresh_error && <p className="mt-1 max-w-xs text-xs text-red-300">{merchant.last_token_refresh_error}</p>}</td>
                  <td className="px-4 py-4"><p className="text-xs text-zinc-300">Webhook: {dateTime(merchant.last_webhook_at)}</p><p className="mt-1 text-xs text-zinc-500">CDC: {dateTime(merchant.last_cdc_at)}</p>{(merchant.last_webhook_error || merchant.last_cdc_error) && <p className="mt-1 max-w-xs text-xs text-red-300">{merchant.last_webhook_error || merchant.last_cdc_error}</p>}</td>
                  <td className="px-4 py-4">{merchant.is_connected ? <GlassNoirButton variant="danger" size="sm" onClick={() => onReset(merchant)} disabled={resettingTenantId === merchant.tenant_id}>{resettingTenantId === merchant.tenant_id ? 'Resetting' : 'Reset QuickBooks'}</GlassNoirButton> : <span className="text-xs text-zinc-500">No connection</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassNoirCard>

      <GlassNoirCard padding="none" className="overflow-hidden">
        <div className="p-6"><h2 className="font-semibold text-white">Recent QuickBooks ledger</h2><p className="mt-1 text-sm text-zinc-400">Provider charge status, refunds and QBO reconciliation.</p></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="border-y border-zinc-800 bg-zinc-950/45 text-xs uppercase tracking-[0.12em] text-zinc-500"><tr><th className="px-6 py-3">Date</th><th className="px-4 py-3">Merchant</th><th className="px-4 py-3">Invoice</th><th className="px-4 py-3">Amount</th><th className="px-4 py-3">Charge</th><th className="px-4 py-3">Refunded</th><th className="px-4 py-3">Reconciliation</th></tr></thead>
            <tbody className="divide-y divide-zinc-800">
              {ledger.entries.map((entry) => (
                <tr key={entry.payment_id}><td className="px-6 py-3 text-xs text-zinc-400">{dateTime(entry.created_at)}</td><td className="px-4 py-3 text-zinc-200">{entry.tenant_name}</td><td className="px-4 py-3 text-zinc-300">{entry.invoice_number}</td><td className="px-4 py-3 font-medium text-zinc-100">{money(entry.amount)}</td><td className="px-4 py-3"><p className="text-xs capitalize text-zinc-300">{entry.charge_status?.toLowerCase() || entry.status}</p><p className="mt-1 font-mono text-xs text-zinc-600">{entry.charge_id || 'No charge ID'}</p></td><td className="px-4 py-3 text-zinc-300">{entry.refunded_amount ? money(entry.refunded_amount) : '—'}</td><td className="px-4 py-3">{entry.reconciled_at ? <span className="text-xs text-emerald-300">{dateTime(entry.reconciled_at)}</span> : entry.sync_error ? <span className="text-xs text-red-300">{entry.sync_error}</span> : <span className="text-xs text-amber-300">Pending</span>}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassNoirCard>
    </>
  )
}

function ResetProviderDialog({
  target,
  pending,
  onCancel,
  onConfirm,
}: {
  target: ResetTarget
  pending: boolean
  onCancel: () => void
  onConfirm: (password: string) => void
}) {
  const label = target.provider === 'stripe' ? 'Stripe' : 'QuickBooks'
  const [password, setPassword] = useState('')
  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={(event) => event.target === event.currentTarget && !pending && onCancel()}>
      <div role="alertdialog" aria-modal="true" aria-labelledby="reset-provider-title" aria-describedby="reset-provider-description" className="w-full max-w-md rounded-lg border border-red-800/50 bg-zinc-950 p-6 shadow-2xl shadow-black/60">
        <div className="flex items-start justify-between gap-4">
          <div><h3 id="reset-provider-title" className="text-lg font-semibold text-zinc-100">Reset {label} connection?</h3><p id="reset-provider-description" className="mt-3 text-sm leading-6 text-zinc-400">This removes the local {label} authorization for <span className="font-medium text-zinc-200">{target.tenantName}</span>. Provider accounts and prior accounting or payment history are preserved.</p></div>
          <button type="button" onClick={onCancel} disabled={pending} aria-label="Close confirmation" className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-50"><X className="h-5 w-5" /></button>
        </div>
        <div className="mt-5"><label htmlFor="platform-payment-reset-password" className="mb-2 block text-xs font-medium text-zinc-400">Your current password</label><input id="platform-payment-reset-password" autoFocus type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-sm text-zinc-100 outline-none focus:border-gold-500 focus:ring-2 focus:ring-gold-500/20" /></div>
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><GlassNoirButton variant="secondary" onClick={onCancel} disabled={pending}>Cancel</GlassNoirButton><GlassNoirButton variant="danger" onClick={() => onConfirm(password)} disabled={pending || !password}>{pending ? 'Resetting...' : `Verify and reset ${label}`}</GlassNoirButton></div>
      </div>
    </div>
  )
}

export default function PaymentControlCenter() {
  const [activeProvider, setActiveProvider] = useState<Provider>('stripe')
  const [stripeOverview, setStripeOverview] = useState<StripeOverview | null>(null)
  const [stripeLedger, setStripeLedger] = useState<StripeLedger | null>(null)
  const [quickBooksOverview, setQuickBooksOverview] = useState<QuickBooksOverview | null>(null)
  const [quickBooksLedger, setQuickBooksLedger] = useState<QuickBooksLedger | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [feeDrafts, setFeeDrafts] = useState<Record<string, string>>({})
  const [savingTenantId, setSavingTenantId] = useState<string | null>(null)
  const [resetTarget, setResetTarget] = useState<ResetTarget | null>(null)
  const [resettingTenantId, setResettingTenantId] = useState<string | null>(null)

  const load = async (refresh = false) => {
    try {
      refresh ? setRefreshing(true) : setLoading(true)
      const [stripeOverviewResponse, stripeLedgerResponse, quickBooksOverviewResponse, quickBooksLedgerResponse] = await Promise.all([
        api.get<StripeOverview>('/admin/payments-control/overview'),
        api.get<StripeLedger>('/admin/payments-control/ledger'),
        api.get<QuickBooksOverview>('/admin/payments-control/quickbooks/overview'),
        api.get<QuickBooksLedger>('/admin/payments-control/quickbooks/ledger'),
      ])
      setStripeOverview(stripeOverviewResponse.data)
      setStripeLedger(stripeLedgerResponse.data)
      setQuickBooksOverview(quickBooksOverviewResponse.data)
      setQuickBooksLedger(quickBooksLedgerResponse.data)
      setFeeDrafts(Object.fromEntries(stripeOverviewResponse.data.merchants.map((merchant) => [merchant.tenant_id, merchant.platform_fee_percent || ''])))
    } catch (error: unknown) {
      toast.error(apiErrorDetail(error, 'Unable to load payment controls'))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { load() }, [])

  const saveFee = async (merchant: StripeMerchant, explicitPercent?: number | null) => {
    const raw = feeDrafts[merchant.tenant_id]?.trim() || ''
    const percent = explicitPercent === undefined ? (raw === '' ? null : Number(raw)) : explicitPercent
    if (percent !== null && (!Number.isFinite(percent) || percent < 0 || percent > 20)) {
      toast.error('Platform fee must be between 0% and 20%')
      return
    }
    try {
      setSavingTenantId(merchant.tenant_id)
      await api.patch(`/admin/payments-control/tenants/${merchant.tenant_id}/fee`, { percent })
      toast.success(percent === null ? `Restored the ${stripeOverview?.platform_fee_default_percent}% platform default` : `Fee set to ${percent}% for ${merchant.tenant_name}`)
      await load(true)
    } catch (error: unknown) {
      toast.error(apiErrorDetail(error, 'Unable to update platform fee'))
    } finally {
      setSavingTenantId(null)
    }
  }

  const resetConnection = async (password: string) => {
    if (!resetTarget) return
    try {
      setResettingTenantId(resetTarget.tenantId)
      const endpoint = resetTarget.provider === 'stripe' ? 'reset-stripe-connection' : 'reset-quickbooks-connection'
      const scope = resetTarget.provider === 'stripe'
        ? 'platform.payment_sources.stripe.reset'
        : 'platform.payment_sources.quickbooks.reset'
      const grant = await createPaymentStepUpGrant(password, scope, resetTarget.tenantId)
      await api.post(
        `/admin/payments-control/tenants/${resetTarget.tenantId}/${endpoint}`,
        undefined,
        { headers: paymentStepUpHeaders(grant.grant_token) },
      )
      toast.success(`Reset ${resetTarget.provider === 'stripe' ? 'Stripe' : 'QuickBooks'} connection for ${resetTarget.tenantName}`)
      setResetTarget(null)
      await load(true)
    } catch (error: unknown) {
      toast.error(paymentStepUpError(error, 'Unable to reset provider connection'))
    } finally {
      setResettingTenantId(null)
    }
  }

  const copyWebhook = async (url: string) => {
    await navigator.clipboard.writeText(url)
    toast.success('Webhook URL copied')
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner size="xl" /></div>
  if (!stripeOverview || !stripeLedger || !quickBooksOverview || !quickBooksLedger) return null

  return (
    <div className="space-y-6">
      <GlassNoirHeader
        title="Payments Control Center"
        subtitle="Provider-specific readiness, authorization, recovery and settlement operations"
        icon={<CreditCard className="h-6 w-6 text-gold-400" />}
        actions={<GlassNoirButton variant="secondary" size="sm" onClick={() => load(true)} disabled={refreshing}>{refreshing ? 'Refreshing...' : <span className="inline-flex items-center gap-2"><RefreshCw className="h-4 w-4" />Refresh</span>}</GlassNoirButton>}
      />
      <ProviderTabs active={activeProvider} onChange={setActiveProvider} />
      {activeProvider === 'stripe' ? (
        <StripeControls
          overview={stripeOverview}
          ledger={stripeLedger}
          feeDrafts={feeDrafts}
          savingTenantId={savingTenantId}
          resettingTenantId={resettingTenantId}
          onFeeChange={(tenantId, value) => setFeeDrafts((current) => ({ ...current, [tenantId]: value }))}
          onSaveFee={saveFee}
          onCopyWebhook={copyWebhook}
          onReset={(merchant) => setResetTarget({ provider: 'stripe', tenantId: merchant.tenant_id, tenantName: merchant.tenant_name })}
        />
      ) : (
        <QuickBooksControls
          overview={quickBooksOverview}
          ledger={quickBooksLedger}
          resettingTenantId={resettingTenantId}
          onCopyWebhook={copyWebhook}
          onReset={(merchant) => setResetTarget({ provider: 'quickbooks', tenantId: merchant.tenant_id, tenantName: merchant.tenant_name })}
        />
      )}
      {resetTarget && <ResetProviderDialog target={resetTarget} pending={Boolean(resettingTenantId)} onCancel={() => setResetTarget(null)} onConfirm={resetConnection} />}
    </div>
  )
}
