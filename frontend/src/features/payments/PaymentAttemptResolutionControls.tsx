import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { createPaymentStepUpGrant, paymentStepUpError } from '@/lib/paymentStepUp'
import { useAuthStore } from '@/stores/authStore'
import { createIdempotencyKey } from './api'
import { fetchAttemptResolutionDetail, resolutionError, resolvePaymentAttempt } from './attemptResolutionApi'
import type { AttemptResolutionCommand, AttemptResolutionDetail, ResolutionAction, ResolutionProjection } from './attemptResolutionTypes'
import type { InvoiceSettlementSummary, PaymentAllocation, PaymentAllocationPage, SettlementAccess } from './types'
import { formatMoney, isPositiveMoney } from './money'
import PendingManualPaymentPanel from './PendingManualPaymentPanel'
import { refreshPaymentViews } from './refreshPaymentViews'
import './attemptResolution.css'

function localDateTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function focusPaymentOptions(invoiceId: string) {
  requestAnimationFrame(() => {
    const heading = document.getElementById(`settlement-payment-${invoiceId}`)
    heading?.focus({ preventScroll: true })
    heading?.scrollIntoView({ block: 'center' })
  })
}

type Props = {
  access: SettlementAccess
  summary: InvoiceSettlementSummary
  allocation: PaymentAllocation
  audience: 'customer' | 'guest' | 'staff'
  tone?: 'dark' | 'light'
  onUpdated: (next: InvoiceSettlementSummary) => void
}

function ResolutionControls({ access, summary, allocation, audience, tone = 'dark', onUpdated }: Props) {
  const client = useQueryClient()
  const [observed, setObserved] = useState<ResolutionProjection | null>(null)
  const projection = observed && observed.attempt_version >= (allocation.resolution?.attempt_version ?? 0) ? observed : allocation.resolution
  const [panel, setPanel] = useState<'cancel' | 'evidence' | 'late' | null>(null)
  const [notSent, setNotSent] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<AttemptResolutionDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [caseReference, setCaseReference] = useState('')
  const [evidenceReference, setEvidenceReference] = useState('')
  const [statement, setStatement] = useState('')
  const [password, setPassword] = useState('')
  const [outcome, setOutcome] = useState<'no_charge' | 'cancelled' | null>(null)
  const [windowStart, setWindowStart] = useState('')
  const [windowEnd, setWindowEnd] = useState('')
  const [contextOpen, setContextOpen] = useState(false)
  const alive = useRef(true)
  const busyRef = useRef(false)
  const latest = useRef(summary)
  latest.current = summary
  const pending = useRef<{ command: AttemptResolutionCommand; key: string; grant?: string } | null>(null)
  const [uncertain, setUncertain] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const cancelTrigger = useRef<HTMLButtonElement>(null)
  const panelWasOpen = useRef(false)
  const feedback = useRef<HTMLParagraphElement>(null)
  const staff = audience === 'staff'
  const zelle = allocation.rail === 'zelle'
  const efs = Boolean(allocation.efs)
  const identityEpoch = useAuthStore(state => state.authSessionEpoch)
  const epoch = useRef(identityEpoch)
  epoch.current = identityEpoch
  const quiet = tone === 'dark' ? 'text-[#99a4b7]' : 'text-slate-600'
  const fieldClass = tone === 'dark' ? 'rounded-lg border border-[#3a465e] bg-[#182234] px-3 text-white' : 'rounded-lg border border-slate-300 bg-white px-3 text-slate-950'
  const locked = busy || uncertain
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    if (panel) heading.current?.focus()
    else if (panelWasOpen.current) (cancelTrigger.current ?? feedback.current)?.focus()
    panelWasOpen.current = Boolean(panel)
  }, [panel])

  const current = (startedEpoch: number) => alive.current && epoch.current === startedEpoch && useAuthStore.getState().authSessionEpoch === startedEpoch
  const scope = access.kind === 'guest' ? ['guest', access.token] : ['authenticated', access.invoiceId]
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['invoice-settlement', ...scope], exact: true })
    void client.invalidateQueries({ queryKey: ['invoice-settlement-allocations', ...scope], exact: true })
    void client.invalidateQueries({ queryKey: ['zelle-review-queue'] })
    void client.invalidateQueries({ queryKey: ['attempt-review-queue'] })
    refreshPaymentViews(client)
  }

  if (!projection) return null
  if (projection.attempt_id !== allocation.attempt_id || projection.invoice_id !== summary.invoice_id || (access.kind === 'authenticated' && access.invoiceId !== summary.invoice_id)) return <p role="alert">Payment details changed. Refresh before continuing.</p>
  const actions = projection.actions
  const canRetry = projection.can_retry && isPositiveMoney(summary.allocatable_balance) && summary.allowed_actions?.create_attempt !== false && !summary.payment_verification_required

  const close = () => { if (locked) return; setPanel(null); setError(''); setNotSent(false); setPassword('') }
  const run = async (action: ResolutionAction, evidence?: AttemptResolutionCommand['evidence']) => {
    if (busyRef.current) return
    if (!pending.current && (!actions[action] || projection.settlement_version !== latest.current.version)) { setError('Payment details changed. Refresh before continuing.'); refresh(); return }
    const startedEpoch = epoch.current
    busyRef.current = true; setBusy(true); setError(''); setMessage('')
    try {
      if (!pending.current) {
        let grant: string | undefined
        if (action === 'release_with_terminal_evidence') {
          grant = (await createPaymentStepUpGrant(password, 'payments.attempts.resolve')).grant_token
          if (!current(startedEpoch)) return
          setPassword('')
        }
        const command: AttemptResolutionCommand = {
          action, expected_attempt_version: projection.attempt_version,
          expected_settlement_version: latest.current.version,
          reason_code: action === 'cancel_unsent' ? 'payment_not_sent' : action === 'request_review' ? 'review_requested' : action === 'check_provider_status' ? 'status_check_requested' : 'provider_terminal_confirmation',
          reason: reason.trim() || (action === 'cancel_unsent' ? zelle ? 'Transfer not sent.' : efs ? 'Customer canceled the EFS request.' : 'Checkout abandoned.' : action === 'request_review' ? 'Please review this payment request.' : 'Check the current provider outcome.'),
          ...(action === 'cancel_unsent' && zelle ? { transfer_not_sent_confirmed: notSent } : {}),
          ...(evidence ? { evidence } : {}),
        }
        pending.current = { command, key: createIdempotencyKey(), grant }
      }
      const request = pending.current
      const result = await resolvePaymentAttempt(access, allocation.attempt_id, request.command, request.key, request.grant)
      if (!current(startedEpoch)) return
      if (result.attempt_id !== allocation.attempt_id || result.invoice_id !== latest.current.invoice_id || result.rail !== allocation.rail || result.resolution.attempt_id !== allocation.attempt_id || result.resolution.rail !== allocation.rail || result.resolution.invoice_id !== latest.current.invoice_id || result.settlement.invoice_id !== latest.current.invoice_id || result.settlement.version < latest.current.version || (latest.current.payment_verification_required && !result.settlement.payment_verification_required && result.settlement.version <= latest.current.version)) { setError('A newer payment update is already shown. Refresh its status.'); pending.current = null; setUncertain(false); refresh(); return }
      setObserved(result.resolution)
      client.setQueryData(['invoice-settlement', ...scope], result.settlement)
      if (result.resolution.checkout_status === 'cancelled') client.setQueryData<PaymentAllocationPage>(['invoice-settlement-allocations', ...scope], previous => previous && ({
        ...previous, items: previous.items.map(row => row.attempt_id === allocation.attempt_id ? { ...row, state: result.state, attempt_version: result.resolution.attempt_version, resolution: result.resolution } : row),
      }))
      onUpdated(result.settlement)
      refresh()
      setMessage(result.resolution.checkout_status === 'cancelled' ? 'Request canceled. No payment was recorded.' : action === 'request_review' ? 'Shop review requested.' : result.resolution.checkout_status === 'received' ? 'Payment received.' : 'Status checked. This request still needs review.')
      setPanel(null); setNotSent(false); setReason(''); setPassword(''); pending.current = null; setUncertain(false)
    } catch (caught) {
      if (!current(startedEpoch)) return
      const parsed = resolutionError(caught)
      setError(parsed.message)
      const mayHaveCommitted = Boolean(pending.current) && parsed.uncertain
      setUncertain(mayHaveCommitted)
      if (!mayHaveCommitted) pending.current = null
      if (parsed.stale) refresh()
      if (!pending.current && action === 'release_with_terminal_evidence') setError(paymentStepUpError(caught, parsed.message))
    } finally { if (current(startedEpoch)) { busyRef.current = false; setBusy(false) } }
  }

  const openEvidence = async () => {
    if (busyRef.current || loadingDetail) return
    const startedEpoch = epoch.current
    setLoadingDetail(true); setError(''); setMessage('')
    try {
      const next = await fetchAttemptResolutionDetail(allocation.attempt_id)
      if (!current(startedEpoch)) return
      if (next.resolution.attempt_id !== allocation.attempt_id || next.resolution.invoice_id !== summary.invoice_id) throw new Error('Payment details changed.')
      setDetail(next); setWindowStart(localDateTime(next.binding.attempted_at)); setWindowEnd(localDateTime(new Date().toISOString())); setPanel('evidence')
    } catch { if (current(startedEpoch)) setError('Couldn’t load the review details. Refresh and try again.') }
    finally { if (current(startedEpoch)) setLoadingDetail(false) }
  }

  const evidenceReady = detail?.evidence_requirements.can_submit_terminal_evidence && outcome && caseReference.trim().length >= 3 && evidenceReference.trim().length >= 3 && statement.trim().length >= 30 && reason.trim() && password && windowStart && windowEnd && !detail.evidence_requirements.requires_document
  const submitEvidence = () => {
    if (!detail || !evidenceReady || !outcome) return
    const start = new Date(windowStart), end = new Date(windowEnd)
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end < start) { setError('Choose a valid review period.'); return }
    const binding = detail.binding
    void run('release_with_terminal_evidence', {
      provider: binding.provider, provider_account_id: binding.provider_account_id, environment: binding.environment,
      configuration_version: binding.configuration_version, provider_request_id: binding.provider_request_id,
      provider_reference: binding.provider_reference, attempted_at: binding.attempted_at, evidence_context_sha256: binding.evidence_context_sha256,
      kind: outcome === 'cancelled' ? 'provider_cancelled' : 'provider_terminal_no_charge',
      review_window_start: start.toISOString(), review_window_end: end.toISOString(),
      provider_case_reference: caseReference.trim(), evidence_reference: evidenceReference.trim(),
      terminal_outcome: outcome, reviewer_statement: statement.trim(),
    })
  }

  return <div className={`db-attempt-resolution ${tone === 'dark' ? 'db-attempt-resolution--dark' : ''}`}>
    {projection.resolution_notice && <p ref={feedback} tabIndex={-1} role="status" className={`mt-2 text-sm ${quiet}`}>{!staff && !projection.block_reason && projection.resolution_notice.kind === 'request_cancelled' ? 'Canceled. No payment recorded.' : projection.resolution_notice.message}</p>}
    {!panel && <div className="mt-2 flex flex-wrap items-center gap-2">
      {actions.cancel_unsent && (!efs || allocation.efs?.can_cancel) && !(staff && efs) && <ControlButton type="button" ref={cancelTrigger} disabled={locked} onClick={() => { setNotSent(false); setError(''); setPanel('cancel') }} className={`db-attempt-secondary ${!staff && !zelle && !efs ? 'cp-payment-cancel-link' : ''}`}>{zelle ? 'Payment not sent?' : efs ? 'Cancel EFS request' : 'Cancel checkout'}</ControlButton>}
      {actions.check_provider_status && <ControlButton type="button" disabled={locked} onClick={() => { void run('check_provider_status') }} className="db-attempt-secondary">Check card status</ControlButton>}
      {!staff && !zelle && !efs && actions.request_review && projection.review_status !== 'requested' && !(projection.checkout_status === 'checkout_started' && actions.cancel_unsent) && <ControlButton type="button" disabled={locked} onClick={() => { void run('request_review') }} className="db-attempt-secondary">Ask shop to review</ControlButton>}
      {staff && allocation.rail === 'card' && (actions.release_with_terminal_evidence || actions.request_review) && !(projection.checkout_status === 'checkout_started' && actions.cancel_unsent) && <ControlButton type="button" ref={actions.cancel_unsent ? undefined : cancelTrigger} disabled={locked || loadingDetail} onClick={() => { void openEvidence() }} className="db-attempt-secondary">{loadingDetail ? 'Loading review…' : 'Review payment outcome'}</ControlButton>}
      {staff && actions.record_late_receipt && <ControlButton type="button" ref={cancelTrigger} disabled={locked} onClick={() => setPanel('late')} className="db-attempt-secondary">Record late receipt</ControlButton>}
      {canRetry && <ControlButton type="button" disabled={locked} onClick={() => focusPaymentOptions(summary.invoice_id)} className="db-attempt-primary">Pay remaining</ControlButton>}
    </div>}
    {staff && !panel && !message && !projection.resolution_notice && projection.review_status === 'requested' && <p className={`mt-2 text-xs ${quiet}`}>Shop review requested.</p>}
    {!panel && !message && projection.block_reason && !projection.resolution_notice && <p className={`mt-2 text-xs ${quiet}`}>{staff ? projection.block_reason.message : projection.checkout_status === 'review_required' ? 'The shop needs to check this payment before you try again.' : projection.block_reason.message}</p>}

    {panel === 'cancel' && <div className="db-attempt-form" role="group" aria-labelledby={`cancel-request-${allocation.attempt_id}`}>
      <h3 ref={heading} tabIndex={-1} id={`cancel-request-${allocation.attempt_id}`} className="font-bold">{zelle ? 'Cancel Zelle request?' : efs ? 'Cancel EFS request?' : 'Cancel this checkout?'}</h3>
      <p className={`mt-2 text-sm ${quiet}`}>{zelle ? 'This cancels the request here. It does not cancel a bank transfer.' : efs ? 'This cancels the request here, not the EFS code. Use a different code for a new request, or contact the shop.' : 'You can try another payment once cancellation is confirmed.'}</p>
      <fieldset disabled={locked} className="mt-3 min-w-0 space-y-3 border-0 p-0">
        {zelle && <label className="db-attempt-check"><input type="checkbox" checked={notSent} onChange={event => setNotSent(event.target.checked)} /><span>{staff ? 'The customer confirmed this transfer was not sent.' : 'I have not sent this transfer.'}</span></label>}
        {staff && <label className="block text-sm font-semibold">Reason<ControlInput className={`mt-1 w-full ${fieldClass}`} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /></label>}
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end"><ControlButton type="button" className="db-attempt-secondary w-full sm:w-auto" onClick={close}>{staff ? 'Keep request' : 'Go back'}</ControlButton><ControlButton type="button" className="db-attempt-primary w-full sm:w-auto" disabled={(zelle && !notSent) || (staff && !reason.trim())} onClick={() => { void run('cancel_unsent') }}>{!staff && !zelle && !efs ? 'Cancel checkout' : 'Cancel request'}</ControlButton></div>
      </fieldset>
    </div>}

    {panel === 'evidence' && detail && <div className="db-attempt-form" role="group" aria-labelledby={`review-request-${allocation.attempt_id}`}>
      <h3 ref={heading} tabIndex={-1} id={`review-request-${allocation.attempt_id}`} className="font-bold">Review card payment outcome</h3>
      <p className={`mt-2 text-sm ${quiet}`}>Release only after the provider confirms this payment cannot complete. An empty transaction list is not enough.</p>
      <ControlButton type="button" className="db-attempt-secondary mt-2 flex items-center gap-2" aria-expanded={contextOpen} onClick={() => setContextOpen(value => !value)}>Provider and review history<ChevronDown aria-hidden="true" size={15} className={contextOpen ? 'rotate-180' : ''} /></ControlButton>
      {contextOpen && <div className="mt-2 break-words text-xs"><dl className="space-y-1"><div>Provider: {detail.binding.provider === 'quickbooks_payments' ? 'QuickBooks Payments' : 'Stripe'}</div><div>Account: {detail.binding.provider_account_id || 'Needs verification'}</div><div>Environment: {detail.binding.environment || 'Needs verification'}</div><div>Request: {detail.binding.provider_request_id || 'Needs verification'}</div><div>Amount: {formatMoney(detail.binding.provider_charge_amount)}</div></dl>{detail.history.map(event => <p key={event.event_id} className="mt-2">{new Date(event.occurred_at).toLocaleString()} · {event.actor_display}<br />{event.reason}</p>)}</div>}
      {!detail.evidence_requirements.can_submit_terminal_evidence ? <p role="status" className="mt-3 text-sm">{detail.evidence_requirements.message}</p> : <fieldset disabled={locked} className="mt-3 min-w-0 space-y-3 border-0 p-0">
        <div role="group" aria-label="Verified provider outcome" className="flex flex-wrap gap-2"><ControlButton type="button" className="db-attempt-secondary" aria-pressed={outcome === 'no_charge'} onClick={() => setOutcome('no_charge')}>No charge can complete</ControlButton><ControlButton type="button" className="db-attempt-secondary" aria-pressed={outcome === 'cancelled'} onClick={() => setOutcome('cancelled')}>Provider canceled</ControlButton></div>
        <label className="block text-sm font-semibold">Provider case reference<ControlInput className={`mt-1 w-full ${fieldClass}`} maxLength={255} value={caseReference} onChange={event => setCaseReference(event.target.value)} /></label>
        <label className="block text-sm font-semibold">Evidence reference<ControlInput className={`mt-1 w-full ${fieldClass}`} maxLength={1000} value={evidenceReference} onChange={event => setEvidenceReference(event.target.value)} /></label>
        {detail.evidence_requirements.requires_document && <p role="status">Contact payment support to verify the supporting document before releasing this request.</p>}
        <div className="grid gap-3 sm:grid-cols-2"><label className="block text-sm font-semibold">Review period starts<ControlInput type="datetime-local" className={`mt-1 w-full ${fieldClass}`} value={windowStart} onChange={event => setWindowStart(event.target.value)} /></label><label className="block text-sm font-semibold">Review period ends<ControlInput type="datetime-local" className={`mt-1 w-full ${fieldClass}`} value={windowEnd} onChange={event => setWindowEnd(event.target.value)} /></label></div>
        <label className="block text-sm font-semibold">Provider confirmation<textarea className={`mt-1 min-h-24 w-full rounded-xl border px-3 py-2 text-base ${fieldClass}`} maxLength={1000} value={statement} onChange={event => setStatement(event.target.value)} /></label>
        <label className="block text-sm font-semibold">Reason for release<ControlInput className={`mt-1 w-full ${fieldClass}`} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /></label>
        <label className="block text-sm font-semibold">Your password<ControlInput type="password" autoComplete="current-password" className={`mt-1 w-full ${fieldClass}`} value={password} onChange={event => setPassword(event.target.value)} /></label>
        <p className={`text-xs ${quiet}`}>Use the provider’s terminal confirmation. Do not enter card numbers or bank credentials.</p>
        <ControlButton type="button" disabled={!evidenceReady} onClick={submitEvidence} className="db-attempt-primary">Verify and release request</ControlButton>
      </fieldset>}
      <ControlButton type="button" disabled={locked} className="db-attempt-secondary mt-3" onClick={close}>Back to request</ControlButton>
    </div>}

    {panel === 'late' && <div className="db-attempt-form"><h3 ref={heading} tabIndex={-1} className="font-bold">Record a verified late receipt</h3><PendingManualPaymentPanel invoiceId={summary.invoice_id} summary={summary} allocations={[allocation]} includeLate tone={tone} onUpdated={next => { onUpdated(next); refresh(); setPanel(null) }} /><ControlButton type="button" className="db-attempt-secondary mt-2" onClick={close}>Back to request</ControlButton></div>}
    {busy && <p role="status" className={`mt-2 text-sm ${quiet}`}>Checking and updating request…</p>}
    {message && !projection.resolution_notice && <p ref={feedback} tabIndex={-1} role="status" className={`mt-2 text-sm ${quiet}`}>{message}</p>}
    {error && <p role="alert" className={`mt-2 text-sm ${tone === 'dark' ? 'text-red-300' : 'text-red-700'}`}>{error}</p>}
    {uncertain && <div className="mt-2"><p className={`text-xs ${quiet}`}>The result is not confirmed. Retry this same request; don’t start another payment.</p><ControlButton type="button" disabled={busy} className="db-attempt-secondary mt-2" onClick={() => { if (pending.current) void run(pending.current.command.action) }}>Retry status update</ControlButton></div>}
  </div>
}

export default function PaymentAttemptResolutionControls(props: Props) {
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const identity = props.access.kind === 'guest' ? props.access.token : props.access.invoiceId
  return <ResolutionControls key={`${epoch}:${props.audience}:${identity}:${props.allocation.attempt_id}`} {...props} />
}
