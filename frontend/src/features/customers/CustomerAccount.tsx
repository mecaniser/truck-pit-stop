import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, ExternalLink, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import api from '@/lib/api'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import './customer-account.css'

const moneySchema = z.string().regex(/^-?\d+\.\d{2}$/)
const accountSchema = z.object({
  as_of_date: z.string(),
  generated_at: z.string(),
  currency: z.literal('USD'),
  customer: z.object({ id: z.string(), name: z.string() }),
  native: z.object({
    collectible: moneySchema,
    collectible_complete: z.boolean(),
    unverified_invoice_count: z.number().int().nonnegative(),
    reviewed_attestation_count: z.number().int().nonnegative().optional(),
    current: moneySchema,
    days_1_30: moneySchema,
    days_31_60: moneySchema,
    days_61_90: moneySchema,
    days_90_plus: moneySchema,
    undated_due: moneySchema,
    unapplied_credit: moneySchema,
    review_required_count: z.number().int().nonnegative(),
  }),
  ets_history: z.object({
    observed_open_balance: z.null(),
    balance_basis: z.literal('unavailable'),
    review_required_count: z.number().int().nonnegative(),
    collectible: z.literal(false),
  }),
  transactions: z.array(z.object({
    id: z.string(),
    kind: z.enum(['invoice', 'payment', 'credit', 'refund']),
    source_owner: z.enum(['native', 'ets_history', 'review_required']),
    occurred_at: z.string().nullable(),
    source_date: z.string().nullable().optional(),
    date_basis: z.string(),
    invoice_id: z.string().nullable(),
    amount: moneySchema.nullable(),
    remaining_principal: moneySchema.nullable(),
    principal_total: moneySchema.nullable().optional(),
    settled_principal: moneySchema.nullable().optional(),
    reconciliation_basis: z.enum(['native_settlement', 'reviewed_attestation']).nullable().optional(),
    drilldown_route: z.string().nullable(),
    review_reason: z.string().nullable().optional(),
    payment_status: z.string().optional(),
    credit_action: z.enum(['issued', 'applied', 'refunded', 'reversed']).optional(),
    credit_effect: z.enum(['increase', 'decrease', 'audit']).optional(),
  })),
  next_cursor: z.string().nullable(),
})

type Account = z.infer<typeof accountSchema>
type Transaction = Account['transactions'][number]

function money(value: string | null): string {
  if (value === null) return '—'
  const negative = value.startsWith('-')
  const [whole, cents] = (negative ? value.slice(1) : value).split('.')
  return `${negative ? '−' : ''}$${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${cents}`
}

function localDate(value: string): string {
  const date = new Date(`${value}T12:00:00Z`)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(date)
}

function transactionDate(value: string | null): string {
  if (!value) return 'Date unavailable'
  // Source dates may be date-only. Never shift them across time zones.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return localDate(value)
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(date)
}

function safeRoute(route: string | null): string | null {
  if (!route) return null
  try {
    const url = new URL(route, window.location.origin)
    return url.origin === window.location.origin
      && url.pathname === '/dashboard/repair-orders'
      && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(url.searchParams.get('selected') ?? '')
      ? `${url.pathname}${url.search}` : null
  } catch { return null }
}

const KIND_LABEL: Record<Transaction['kind'], string> = {
  invoice: 'Invoice', payment: 'Payment', credit: 'Credit', refund: 'Refund',
}

function Activity({ row }: { row: Transaction }) {
  const route = row.source_owner === 'review_required' ? null : safeRoute(row.drilldown_route)
  const paymentUnconfirmed = row.kind === 'payment' && Boolean(row.review_reason?.startsWith('payment_'))
  const paymentState = paymentUnconfirmed && row.payment_status === 'pending' ? 'Pending payment'
    : paymentUnconfirmed && row.payment_status === 'failed' ? 'Failed payment'
      : paymentUnconfirmed && row.payment_status === 'refunded' ? 'Refunded payment'
        : paymentUnconfirmed ? 'Unconfirmed payment' : null
  const source = paymentState ?? (row.source_owner === 'native' ? 'DieselBridge' : row.source_owner === 'ets_history' ? 'ETS history' : 'Needs review')
  const basisLabel = row.kind === 'invoice' && row.reconciliation_basis === 'reviewed_attestation'
    ? 'Reviewed historical receivable' : source
  const creditLabel = row.credit_action === 'issued' ? 'Credit issued'
    : row.credit_action === 'applied' ? 'Credit applied'
      : row.credit_action === 'refunded' ? 'Credit refunded'
        : row.credit_action === 'reversed' ? 'Credit reversal' : null
  const activityAmount = row.amount === null ? null
    : `${row.credit_effect === 'increase' ? '+' : row.credit_effect === 'decrease' ? '−' : ''}${money(row.amount)}`
  return <li className="db-customer-account__transaction">
    <div className="db-customer-account__transaction-main">
      <strong>{creditLabel ?? KIND_LABEL[row.kind]}</strong>
      <span className={`db-customer-account__source db-customer-account__source--${row.source_owner}`}>{basisLabel}</span>
      <span className="db-customer-account__date">{transactionDate(row.source_date ?? row.occurred_at)}</span>
    </div>
    {paymentUnconfirmed ? <p>Payment not confirmed; does not reduce the collectible balance.</p>
      : row.source_owner === 'review_required' ? <p>Identity or settlement needs review. Excluded from totals.</p>
      : row.source_owner === 'ets_history' ? <p>Imported activity; outstanding balance unavailable.</p>
        : row.credit_effect === 'audit' ? <p>Audit activity; no separate change to available credit.</p>
        : null}
    <div className="db-customer-account__transaction-side">
      {activityAmount !== null && <span>{activityAmount}</span>}
      {row.kind === 'invoice' && row.remaining_principal !== null && row.source_owner === 'native'
        && <small>Principal {money(row.principal_total ?? null)} · Settled {money(row.settled_principal ?? null)} · {money(row.remaining_principal)} remaining</small>}
      {route && <Link to={route}>Open order <ExternalLink aria-hidden="true" /></Link>}
    </div>
  </li>
}

export default function CustomerAccount({ customerId }: { customerId: string }) {
  const session = useAuthStore(getAuthenticatedSessionIdentity)
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState(false)
  const downloadController = useRef<AbortController | null>(null)
  const cursor = cursors[cursors.length - 1]
  const query = useQuery({
    queryKey: ['customer-account', session, customerId, cursor],
    enabled: Boolean(session && customerId),
    queryFn: async ({ signal }) => {
      const response = await api.get(`/customers/${customerId}/account`, {
        signal, params: { limit: 50, ...(cursor ? { cursor } : {}) },
      })
      const account = accountSchema.parse(response.data)
      if (account.customer.id !== customerId) throw new Error('Customer account identity changed')
      return account
    },
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  })
  useEffect(() => {
    setCursors([null])
    setDownloadError(false)
    return () => { downloadController.current?.abort(); downloadController.current = null }
  }, [customerId, session])

  const download = async () => {
    if (!query.data || !session || downloadController.current) return
    const controller = new AbortController()
    downloadController.current = controller
    setDownloadError(false)
    setDownloading(true)
    try {
      const response = await api.get<Blob>(`/customers/${customerId}/account/statement.pdf`, {
        responseType: 'blob', signal: controller.signal,
      })
      if (controller.signal.aborted || getAuthenticatedSessionIdentity(useAuthStore.getState()) !== session) return
      const contentType = String(response.headers?.['content-type'] ?? '').split(';')[0].trim().toLowerCase()
      if (!(response.data instanceof Blob) || response.data.size === 0 || response.data.size > 5 * 1024 * 1024 || contentType !== 'application/pdf') {
        throw new Error('Invalid statement response')
      }
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = `customer-account-${customerId}-${query.data.as_of_date}.pdf`
      document.body.appendChild(link)
      try { link.click() } finally { link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000) }
    } catch {
      if (!controller.signal.aborted) setDownloadError(true)
    } finally {
      if (downloadController.current === controller) { downloadController.current = null; setDownloading(false) }
    }
  }

  if (query.isPending) return <div className="db-customer-account" role="status">Loading account…</div>
  if (query.isError || !query.data) return <div className="db-customer-account" role="alert">Account unavailable. <button type="button" onClick={() => void query.refetch()}>Retry account</button></div>
  const account = query.data
  const buckets = [
    ['Current', account.native.current], ['1–30 days', account.native.days_1_30],
    ['31–60 days', account.native.days_31_60], ['61–90 days', account.native.days_61_90],
    ['90+ days', account.native.days_90_plus],
  ] as const
  return <section className="db-customer-account" aria-label="Customer account">
    <div className="db-customer-account__head">
      <div><h3>Customer account</h3><p>As of {localDate(account.as_of_date)} · USD</p></div>
      <div className="db-customer-account__actions">
        <button type="button" onClick={() => void query.refetch()} aria-label="Refresh account" disabled={query.isFetching}><RefreshCw aria-hidden="true" /> Refresh</button>
        <button type="button" onClick={() => void download()} disabled={downloading}><Download aria-hidden="true" />{downloading ? 'Preparing…' : 'Download statement'}</button>
      </div>
    </div>
    {downloadError && <p role="alert">Statement unavailable. Try the download again.</p>}
    <div className="db-customer-account__summary">
      <div className="db-customer-account__collectible"><span>{account.native.collectible_complete ? 'DieselBridge collectible' : 'Verified native subtotal'}</span><strong>{money(account.native.collectible)}</strong><small>{account.native.collectible_complete ? 'Verified native invoice principal' : 'Balance incomplete · do not collect from this subtotal'}</small></div>
      <div><span>Unapplied credit</span><strong>{money(account.native.unapplied_credit)}</strong><small>Not deducted from aging</small></div>
    </div>
    <section className="db-customer-account__section" aria-label="Native aging">
      <h4>{account.native.collectible_complete ? 'Overdue aging' : 'Verified overdue aging only'}</h4>
      {!account.native.collectible_complete && <p role="alert">Native balance incomplete: {account.native.unverified_invoice_count} {account.native.unverified_invoice_count === 1 ? 'invoice is' : 'invoices are'} unverified and excluded from this subtotal and aging.</p>}
      {Boolean(account.native.reviewed_attestation_count) && <p>{account.native.reviewed_attestation_count} {account.native.reviewed_attestation_count === 1 ? 'invoice uses' : 'invoices use'} time-limited reviewed historical receivable evidence, not a payment-provider receipt.</p>}
      <div className="db-customer-account__buckets">{buckets.map(([label, amount]) => <div key={label}><span>{label}</span><strong>{money(amount)}</strong></div>)}</div>
      <div className="db-customer-account__exceptions"><span>Due date unavailable</span><strong>{money(account.native.undated_due)}</strong></div>
      {account.native.review_required_count > 0 && <p>{account.native.review_required_count} native {account.native.review_required_count === 1 ? 'item needs' : 'items need'} review and {account.native.review_required_count === 1 ? 'is' : 'are'} excluded from these totals.</p>}
    </section>
    <section className="db-customer-account__section db-customer-account__ets" aria-label="ETS historical account">
      <h4>ETS historical · not a DieselBridge collection balance</h4>
      <p>Imported activity is kept separate. Outstanding ETS balance is unavailable from the imported records.</p>
      {account.ets_history.review_required_count > 0 && <p>{account.ets_history.review_required_count} imported {account.ets_history.review_required_count === 1 ? 'item needs' : 'items need'} review.</p>}
    </section>
    <section className="db-customer-account__section" aria-label="Account activity">
      <h4>Activity</h4>
      {!account.transactions.length ? <p>No account activity in this view.</p> : <ul>{account.transactions.map(row => <Activity key={`${row.source_owner}:${row.kind}:${row.id}`} row={row} />)}</ul>}
      {(cursors.length > 1 || account.next_cursor) && <div className="db-customer-account__pages">
        <button type="button" disabled={cursors.length === 1} onClick={() => setCursors(previous => previous.slice(0, -1))}>Newer</button>
        <span>Page {cursors.length}</span>
        <button type="button" disabled={!account.next_cursor} onClick={() => account.next_cursor && setCursors(previous => [...previous, account.next_cursor])}>Older</button>
      </div>}
    </section>
  </section>
}
