import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { ControlButton } from '@/components/ui/Controls'
import { fetchAllocations, fetchSettlement } from './api'
import type { InvoiceSettlementSummary, SettlementAccess } from './types'

export default function PaymentStatusRefresh({ access, summary, onUpdated, tone = 'dark' }: {
  access: SettlementAccess
  summary: InvoiceSettlementSummary
  onUpdated: (next: InvoiceSettlementSummary) => void
  tone?: 'dark' | 'light'
}) {
  const client = useQueryClient()
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useState('')
  const [failed, setFailed] = useState(false)
  const alive = useRef(true)
  const latest = useRef(summary)
  latest.current = summary
  const identity = access.kind === 'guest' ? `guest:${access.token}` : `authenticated:${access.invoiceId}`
  const currentIdentity = useRef({ value: identity, epoch: 0 })
  if (currentIdentity.current.value !== identity) currentIdentity.current = { value: identity, epoch: currentIdentity.current.epoch + 1 }
  const busy = useRef(false)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => { setMessage(''); setFailed(false); setChecking(false); busy.current = false }, [identity])

  const refresh = async () => {
    if (busy.current) return
    busy.current = true
    setChecking(true)
    setMessage('')
    setFailed(false)
    const requestedIdentity = currentIdentity.current
    const before = latest.current
    const stillCurrent = () => alive.current && currentIdentity.current === requestedIdentity
    try {
      const [next, allocations] = await Promise.all([fetchSettlement(access), fetchAllocations(access)])
      if (!stillCurrent()) return
      const key = access.kind === 'guest' ? ['guest', access.token] : ['authenticated', access.invoiceId]
      const cached = client.getQueryData<InvoiceSettlementSummary>(['invoice-settlement', ...key])
      const current = cached?.invoice_id === before.invoice_id && (cached.version > latest.current.version || (cached.version === latest.current.version && cached.payment_verification_required)) ? cached : latest.current
      if (next.invoice_id !== before.invoice_id || next.version < current.version
        || (current.payment_verification_required && !next.payment_verification_required && next.version <= current.version)) {
        setMessage('A newer payment update is already shown.')
        return
      }
      client.setQueryData(['invoice-settlement', ...key], next)
      client.setQueryData(['invoice-settlement-allocations', ...key], allocations)
      onUpdated(next)
      const changed = ['state', 'confirmed_principal', 'active_pending_principal', 'outstanding_balance', 'allocatable_balance']
        .some(field => next[field as keyof InvoiceSettlementSummary] !== before[field as keyof InvoiceSettlementSummary])
      setMessage(changed ? 'Payment status updated.' : 'Checked just now. No change yet.')
    } catch {
      if (stillCurrent()) { setFailed(true); setMessage('Couldn’t check payment status. Try again.') }
    } finally {
      if (stillCurrent()) { busy.current = false; setChecking(false) }
    }
  }

  return <div>
    <ControlButton type="button" onClick={() => { void refresh() }} disabled={checking} aria-busy={checking}
      className="inline-flex items-center gap-2 rounded-xl border border-current px-3 text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-500,#d25d43)] disabled:opacity-60">
      <RefreshCw size={15} aria-hidden="true" className={checking ? 'animate-spin motion-reduce:animate-none' : undefined} />
      {checking ? 'Checking payment status…' : 'Refresh payment status'}
    </ControlButton>
    <p role={failed ? 'alert' : 'status'} aria-live="polite" className={`mt-2 min-h-5 text-xs ${failed ? tone === 'dark' ? 'text-red-300' : 'text-red-700' : tone === 'dark' ? 'text-[#99a4b7]' : 'text-slate-500'}`}>
      {checking ? 'Checking for updates…' : message}
    </p>
  </div>
}
