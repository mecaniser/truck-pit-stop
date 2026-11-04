import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useAuthStore } from '@/stores/authStore'
import { createPaymentStepUpGrant } from '@/lib/paymentStepUp'
import { createIdempotencyKey } from './api'
import { efsError, revealEfsCode, verifyEfsCode, type EfsVerificationCommand } from './efsApi'
import { formatMoney, isPositiveMoney, normalizeMoney } from './money'
import type { InvoiceSettlementSummary, PaymentAllocation } from './types'
import { refreshPaymentViews } from './refreshPaymentViews'
import './attemptResolution.css'

type Props = { summary: InvoiceSettlementSummary; allocation: PaymentAllocation; tone: 'dark' | 'light'; onUpdated: (next: InvoiceSettlementSummary) => void }

function staffIdentity() {
  const state = useAuthStore.getState(), user = state.user
  return user?.is_active && (user.role === 'garage_owner' || user.role === 'garage_admin' && user.permissions?.payments === true)
    ? JSON.stringify([state.authSessionEpoch, user.id, user.tenant_id, user.role, user.permissions?.payments]) : null
}

function Review({ summary, allocation, tone, onUpdated }: Props) {
  const client = useQueryClient()
  const [revealed, setRevealed] = useState<string | null>(null)
  const [revealing, setRevealing] = useState(false)
  const [authorization, setAuthorization] = useState('')
  const [received, setReceived] = useState(allocation.principal_amount)
  const [authorized, setAuthorized] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [noFunds, setNoFunds] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [password, setPassword] = useState('')
  const [resolveActual, setResolveActual] = useState(false)
  const pending = useRef<{ body: EfsVerificationCommand; key: string; grant?: string } | null>(null)
  const sending = useRef(false)
  const mounted = useRef(true)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const identity = useRef(epoch)
  const boundPrincipal = useRef(staffIdentity())
  const latest = useRef(summary)
  latest.current = summary
  const info = allocation.efs
  const normalized = normalizeMoney(received)
  const different = normalized !== allocation.principal_amount
  const locked = busy || uncertain || revealing
  const current = () => mounted.current && useAuthStore.getState().authSessionEpoch === identity.current && staffIdentity() !== null && staffIdentity() === boundPrincipal.current
  const quiet = tone === 'dark' ? 'text-[#99a4b7]' : 'text-slate-600'
  const field = `mt-1 min-h-11 w-full rounded-xl border px-3 text-base ${tone === 'dark' ? 'border-[#3a465e] bg-[#182234] text-white' : 'border-slate-300 bg-white text-slate-950'}`
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; pending.current = null } }, [])
  useEffect(() => { setRevealed(null) }, [allocation.attempt_version])
  if (!info || info.provider !== 'EFS' || (!info.can_reveal && !info.can_verify && !info.can_reject && !info.can_resolve_received_difference)) return null
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['invoice-settlement', 'authenticated', summary.invoice_id], exact: true })
    void client.invalidateQueries({ queryKey: ['invoice-settlement-allocations', 'authenticated', summary.invoice_id], exact: true })
    void client.invalidateQueries({ queryKey: ['zelle-review-queue'] })
    refreshPaymentViews(client)
  }
  const reveal = async () => {
    if (locked || !info.can_reveal || !allocation.attempt_version) return
    setRevealing(true); setError('')
    try {
      const result = await revealEfsCode(allocation.attempt_id, allocation.attempt_version)
      if (!current()) return
      if (!/^[0-9]{10}$/.test(result.code) || result.last4 !== info.code_last4 || !result.code.endsWith(info.code_last4)) { setError('The code details changed. Refresh this request.'); refresh(); return }
      setRevealed(result.code)
    } catch { if (current()) setError('Couldn’t reveal this code. Refresh the request and check your access.') }
    finally { if (current()) setRevealing(false) }
  }
  const update = async (action: 'confirm_received' | 'reject' | 'resolve_received_difference') => {
    if (sending.current || !allocation.attempt_version) return
    if (!pending.current && (summary.version !== latest.current.version || (action === 'reject' ? !info.can_reject || !noFunds || !reason.trim() : action === 'resolve_received_difference' ? !info.can_resolve_received_difference || !info.difference_review || !resolveActual || !reason.trim() || !password : !info.can_verify || !authorized || !normalized || !isPositiveMoney(normalized) || !authorization.trim()))) return
    if (!pending.current && revealed && (authorization.includes(revealed) || reason.includes(revealed))) { setError('Use the merchant authorization reference, not the MoneyCode.'); return }
    const reviewedVersion = summary.version
    sending.current = true; setBusy(true); setError(''); setMessage('')
    try {
      if (!pending.current) {
        const grant = action === 'resolve_received_difference'
          ? (await createPaymentStepUpGrant(password, 'payments.efs.resolve_received_difference')).grant_token : undefined
        if (!current()) return
        setPassword('')
        if (reviewedVersion !== latest.current.version) { setError('Payment details changed. Review the request again.'); refresh(); return }
        pending.current = { key: createIdempotencyKey(), grant, body: {
          action, expected_attempt_version: allocation.attempt_version, expected_settlement_version: reviewedVersion,
          reason: action === 'reject' ? `No funds received. ${reason.trim()}` : reason.trim() || 'Verified EFS merchant authorization and receipt.',
          ...(action === 'confirm_received' ? { merchant_authorized: true as const, authorization_reference: authorization.trim(), received_amount: normalized! } : {}),
          ...(action === 'resolve_received_difference' ? { observation_id: info.difference_review!.observation_id } : {}),
        } }
      }
      const request = pending.current
      const result = await verifyEfsCode(allocation.attempt_id, request.body, request.key, request.grant)
      if (!current()) return
      if (result.attempt_id !== allocation.attempt_id || result.invoice_id !== latest.current.invoice_id || result.settlement.invoice_id !== latest.current.invoice_id || result.rail !== 'fleet_payment' || result.efs?.code_last4 !== info.code_last4 || result.efs.provider !== 'EFS' || result.settlement.version < latest.current.version) {
        setError('A newer request update needs checking. Refresh before continuing.'); setUncertain(true); refresh(); return
      }
      pending.current = null; setRevealed(null); setAuthorized(false); setUncertain(false); setRejecting(false); setAuthorization(''); setReason(''); setNoFunds(false); setResolveActual(false)
      setMessage(result.efs.status === 'received' ? 'EFS payment received.' : result.efs.status === 'review_required' ? 'The received amount needs review. Further payment is paused.' : 'Request rejected. No payment was recorded.')
      client.setQueryData(['invoice-settlement', 'authenticated', summary.invoice_id], result.settlement)
      onUpdated(result.settlement); refresh()
      requestAnimationFrame(() => document.getElementById(`payment-request-${allocation.attempt_id}`)?.focus({ preventScroll: true }))
    } catch (cause) {
      if (!current()) return
      const parsed = efsError(cause)
      setError(action === 'resolve_received_difference' && !pending.current && !parsed.stepUpUnavailable ? 'Identity verification failed. Check your password and try again.' : parsed.message); setUncertain(Boolean(pending.current) && parsed.uncertain)
      if (!parsed.uncertain) pending.current = null
      if (parsed.stale) refresh()
    } finally { if (current()) { sending.current = false; setBusy(false) } }
  }

  return <div className="db-attempt-resolution mt-3 min-w-0 border-t border-current/15 pt-3">
    <h3 className="font-bold">{info.status === 'received' ? 'EFS details' : ['cancelled', 'rejected'].includes(info.status) ? 'Verify a late EFS receipt' : 'Verify EFS payment'}</h3>
    {info.can_resolve_received_difference && info.difference_review && <fieldset disabled={locked} className="mt-3 min-w-0 space-y-3 border-0 p-0">
      <h4 className="font-semibold">Review the received amount</h4>
      <dl className="space-y-2 text-sm"><div className="flex justify-between gap-3"><dt>Requested</dt><dd className="font-bold">{formatMoney(info.difference_review.requested_amount)}</dd></div><div className="flex justify-between gap-3"><dt>Verified received</dt><dd className="font-bold">{formatMoney(info.difference_review.actual_received_amount)}</dd></div><div><dt>Merchant authorization</dt><dd className="break-words font-semibold">{info.difference_review.authorization_reference}</dd></div></dl>
      <p className={`text-sm ${quiet}`}>Apply the verified receipt before collecting another payment. Any excess stays in credit or refund review.</p>
      <label className="block text-sm font-semibold">Reason for recording actual receipt<ControlInput maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} className={field} /></label>
      <label className="block text-sm font-semibold">Your password<ControlInput type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} className={field} /></label>
      <label className="db-attempt-check"><input type="checkbox" checked={resolveActual} onChange={event => setResolveActual(event.target.checked)} /><span>Record the verified actual receipt of {formatMoney(info.difference_review.actual_received_amount)}.</span></label>
      <ControlButton type="button" disabled={!allocation.attempt_version || !resolveActual || !reason.trim() || !password} className="db-attempt-primary" onClick={() => { void update('resolve_received_difference') }}>Record verified actual receipt</ControlButton>
    </fieldset>}
    {info.can_reveal && <div className="mt-2">{revealed ? <><p className="text-base font-bold tabular-nums" aria-label="EFS MoneyCode">{revealed}</p><ControlButton type="button" disabled={locked} className="db-attempt-secondary mt-2" onClick={() => setRevealed(null)}>Hide code</ControlButton></> : <ControlButton type="button" disabled={locked || !allocation.attempt_version} className="db-attempt-secondary" onClick={() => { void reveal() }}>{revealing ? 'Revealing…' : 'Reveal EFS code'}</ControlButton>}</div>}
    {info.can_verify && !rejecting && <fieldset disabled={locked} className="mt-3 min-w-0 space-y-3 border-0 p-0">
      <p className={`text-sm ${quiet}`}>Authorize the code with EFS and verify receipt before confirming.</p>
      <label className="block text-sm font-semibold">Amount received<ControlInput inputMode="decimal" autoComplete="off" value={received} onChange={event => setReceived(event.target.value)} className={field} /></label>
      <label className="block text-sm font-semibold">Merchant authorization reference<ControlInput autoComplete="off" maxLength={255} value={authorization} onChange={event => setAuthorization(event.target.value)} className={field} /></label>
      <label className="db-attempt-check"><input type="checkbox" checked={authorized} onChange={event => setAuthorized(event.target.checked)} /><span>I verified EFS authorization and receipt of {formatMoney(normalized || '0.00')}.</span></label>
      {normalized && different && <p className={`text-sm ${quiet}`}>Requested {formatMoney(allocation.principal_amount)}. This difference requires review before it can be applied.</p>}
      <ControlButton type="button" disabled={!allocation.attempt_version || !authorized || !normalized || !isPositiveMoney(normalized) || !authorization.trim()} className="db-attempt-primary" onClick={() => { void update('confirm_received') }}>{different ? 'Send difference for review' : 'Record verified receipt'}</ControlButton>
    </fieldset>}
    {info.can_reject && <div className="mt-3">{rejecting ? <fieldset disabled={locked} className="min-w-0 space-y-3 border-0 p-0">
      <label className="block text-sm font-semibold">Reason for rejection<ControlInput maxLength={960} value={reason} onChange={event => setReason(event.target.value)} className={field} /></label>
      <label className="db-attempt-check"><input type="checkbox" checked={noFunds} onChange={event => setNoFunds(event.target.checked)} /><span>No payment was received for this code.</span></label>
      <div className="flex flex-wrap gap-2"><ControlButton type="button" className="db-attempt-secondary" onClick={() => { setRejecting(false); setNoFunds(false); setReason('') }}>Keep request</ControlButton><ControlButton type="button" disabled={!allocation.attempt_version || !noFunds || !reason.trim()} className="db-attempt-primary" onClick={() => { void update('reject') }}>Reject request</ControlButton></div>
    </fieldset> : <ControlButton type="button" disabled={locked} className="db-attempt-secondary" onClick={() => { setRejecting(true); setRevealed(null) }}>Reject request</ControlButton>}</div>}
    {busy && <p role="status" className={`mt-2 text-sm ${quiet}`}>Updating EFS request…</p>}
    {message && <p role="status" className={`mt-2 text-sm ${quiet}`}>{message}</p>}
    {error && <p role="alert" className={`mt-2 text-sm ${tone === 'dark' ? 'text-red-300' : 'text-red-700'}`}>{error}</p>}
    {uncertain && <ControlButton type="button" disabled={busy} className="db-attempt-secondary mt-2" onClick={() => { if (pending.current) void update(pending.current.body.action) }}>Check verification result</ControlButton>}
  </div>
}

export default function EfsReviewControls(props: Props) {
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const user = useAuthStore(state => state.user)
  if (!user?.is_active || !(user.role === 'garage_owner' || user.role === 'garage_admin' && user.permissions?.payments === true)) return null
  const principal = JSON.stringify([user.id, user.tenant_id, user.role, user.permissions?.payments])
  return <Review key={`${epoch}:${principal}:${props.summary.invoice_id}:${props.allocation.attempt_id}`} {...props} />
}
