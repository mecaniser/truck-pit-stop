import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff } from 'lucide-react'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useAuthStore } from '@/stores/authStore'
import { createIdempotencyKey } from './api'
import { efsError, submitEfsCode, type EfsSubmissionCommand } from './efsApi'
import type { InvoiceSettlementSummary, SettlementAccess } from './types'
import { formatMoney, isValidPrincipalAmount, normalizeMoney } from './money'
import { refreshPaymentViews } from './refreshPaymentViews'
import './attemptResolution.css'

type Props = { access: SettlementAccess; summary: InvoiceSettlementSummary; amount: string; tone: 'dark' | 'light'; onUpdated: (next: InvoiceSettlementSummary) => void; onBusyChange?: (busy: boolean) => void }

function principalIdentity() {
  const state = useAuthStore.getState(), user = state.user
  return JSON.stringify([state.authSessionEpoch, user?.id, user?.tenant_id, user?.customer_id, user?.role, user?.is_active])
}

function EfsSubmissionDraft({ access, summary, amount, tone, onUpdated, onBusyChange }: Props) {
  const client = useQueryClient()
  const [code, setCode] = useState('')
  const [showCode, setShowCode] = useState(false)
  const [review, setReview] = useState<EfsSubmissionCommand | null>(null)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<{ body: EfsSubmissionCommand; key: string } | null>(null)
  const sending = useRef(false)
  const mounted = useRef(true)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const startedIdentity = useRef(epoch)
  const boundPrincipal = useRef(principalIdentity())
  const latest = useRef(summary)
  latest.current = summary
  const heading = useRef<HTMLHeadingElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const normalized = normalizeMoney(amount)
  const valid = Boolean(!summary.payment_verification_required && summary.allowed_actions?.submit_efs === true && normalized && isValidPrincipalAmount(normalized, summary.allocatable_balance) && /^\d{10}$/.test(code.trim()))
  const quiet = tone === 'dark' ? 'text-[#99a4b7]' : 'text-slate-600'
  const field = tone === 'dark' ? 'border-[#3a465e] bg-[#182234] text-white' : 'border-slate-300 bg-white text-slate-950'
  const current = () => mounted.current && useAuthStore.getState().authSessionEpoch === startedIdentity.current && principalIdentity() === boundPrincipal.current
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; pending.current = null } }, [])
  useEffect(() => { onBusyChange?.(busy || uncertain); return () => onBusyChange?.(false) }, [busy, uncertain, onBusyChange])
  useEffect(() => { if (review) heading.current?.focus() }, [review])
  const refresh = () => {
    const scope = access.kind === 'guest' ? ['guest', access.token] : ['authenticated', access.invoiceId]
    void client.invalidateQueries({ queryKey: ['invoice-settlement', ...scope], exact: true })
    void client.invalidateQueries({ queryKey: ['invoice-settlement-allocations', ...scope], exact: true })
    void client.invalidateQueries({ queryKey: ['zelle-review-queue'] })
    refreshPaymentViews(client)
  }
  const submit = async () => {
    if (sending.current || !review) return
    if (!pending.current && (review.expected_settlement_version !== latest.current.version || review.amount !== normalized || latest.current.payment_verification_required || latest.current.allowed_actions?.submit_efs !== true)) {
      setError('Your balance or amount changed. Review this payment again.'); setReview(null); refresh(); return
    }
    sending.current = true; setBusy(true); setError('')
    if (!pending.current) pending.current = { body: review, key: createIdempotencyKey() }
    try {
      const request = pending.current
      const result = await submitEfsCode(access, request.body, request.key)
      if (!current()) return
      if (result.invoice_id !== latest.current.invoice_id || result.settlement.invoice_id !== latest.current.invoice_id || result.rail !== 'fleet_payment' || result.principal_amount !== request.body.amount || result.efs?.provider !== 'EFS' || result.efs.code_last4 !== request.body.code.slice(-4) || result.settlement.version < latest.current.version) {
        setError('The result needs checking. Refresh payment activity before starting another request.'); setUncertain(true); refresh(); return
      }
      // Never retain the raw code in a cache or after an accepted submission.
      pending.current = null; setCode(''); setReview(null); setShowCode(false); setUncertain(false)
      onUpdated(result.settlement); refresh()
    } catch (cause) {
      if (!current()) return
      const parsed = efsError(cause)
      setError(parsed.message); setUncertain(parsed.uncertain)
      if (!parsed.uncertain) pending.current = null
      if (parsed.stale) { refresh(); setReview(null) }
    } finally { if (current()) { sending.current = false; setBusy(false) } }
  }
  const back = () => { if (busy || uncertain) return; setReview(null); setShowCode(false); setError(''); requestAnimationFrame(() => input.current?.focus()) }

  return <div className="mt-4 min-w-0">
    {review ? <div role="group" aria-labelledby={`efs-review-${summary.invoice_id}`}>
      <h3 ref={heading} tabIndex={-1} id={`efs-review-${summary.invoice_id}`} className="font-bold">Review EFS payment</h3>
      <dl className="mt-3 space-y-2 text-sm"><div className="flex justify-between gap-3"><dt>Amount</dt><dd className="font-bold">{formatMoney(review.amount)}</dd></div><div className="flex justify-between gap-3"><dt>EFS code</dt><dd className="tabular-nums">Ending in {review.code.slice(-4)}</dd></div></dl>
      <p className={`mt-3 text-sm ${quiet}`}>The shop will verify your code before recording payment.</p>
      <div className="mt-3 flex flex-wrap justify-end gap-2"><ControlButton type="button" disabled={busy || uncertain} onClick={back} className="db-attempt-secondary">Edit details</ControlButton><ControlButton type="button" disabled={busy} onClick={() => { void submit() }} className="db-attempt-primary">{busy ? 'Submitting…' : uncertain ? 'Check submission' : 'Submit for verification'}</ControlButton></div>
    </div> : <>
      <label className="block text-sm font-semibold" htmlFor={`efs-code-${summary.invoice_id}`}>EFS MoneyCode</label>
      <div className="relative mt-1"><ControlInput ref={input} id={`efs-code-${summary.invoice_id}`} type={showCode ? 'text' : 'password'} inputMode="numeric" autoComplete="off" spellCheck={false} maxLength={32} value={code} onBlur={() => setCode(value => value.trim())} onChange={event => { setCode(event.target.value); setError('') }} aria-describedby={`efs-help-${summary.invoice_id}`} className={`min-h-11 w-full rounded-xl border py-2 pl-3 pr-12 text-base ${field}`} /><ControlButton type="button" controlKind="icon" aria-label={showCode ? 'Hide EFS code' : 'Show EFS code'} aria-pressed={showCode} onClick={() => setShowCode(value => !value)} className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center rounded-xl">{showCode ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}</ControlButton></div>
      <p id={`efs-help-${summary.invoice_id}`} className={`mt-2 text-sm ${quiet}`}>10 digits. Use a code for {formatMoney(normalized || '0.00')}.</p>
      <ControlButton type="button" disabled={!valid || busy} onClick={() => { if (valid && normalized) { setReview({ code: code.trim(), amount: normalized, expected_settlement_version: summary.version, submitted_for_verification: true }); setShowCode(false); setError('') } }} className="db-attempt-primary mt-3 w-full">Review EFS payment</ControlButton>
    </>}
    {error && <p role="alert" className={`mt-2 text-sm ${tone === 'dark' ? 'text-red-300' : 'text-red-700'}`}>{error}</p>}
  </div>
}

export default function EfsSubmissionForm(props: Props) {
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const principal = useAuthStore(state => JSON.stringify([state.user?.id, state.user?.tenant_id, state.user?.customer_id, state.user?.role]))
  return <EfsSubmissionDraft key={`${epoch}:${principal}:${props.access.kind}:${props.access.kind === 'guest' ? props.access.token : props.access.invoiceId}`} {...props} />
}
